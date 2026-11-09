import time
import os
from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

import database
import kb_service
import ai_service

# Pydantic schemas

class AddDocumentRequest(BaseModel):
    title: str = Field(..., description="Document title")
    text: str = Field(..., description="Document text body")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("title cannot be empty")
        if len(s) > 500:
            raise ValueError("title is too long (max 500 characters)")
        return s

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("text cannot be empty")
        if len(s) > 500_000:
            raise ValueError("text is too long (max 500,000 characters)")
        return s

class AddDocumentResponse(BaseModel):
    status: str = "ok"
    document_id: str

class DocumentItem(BaseModel):
    id: str
    title: str
    created_at: str

class DocumentDetail(BaseModel):
    id: str
    title: str
    text: str
    created_at: str

class AskQuestionRequest(BaseModel):
    question: str = Field(..., description="Question to ask")

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("question cannot be empty")
        return s

class SourceCitation(BaseModel):
    document_id: str
    quote: str

class AskQuestionResponse(BaseModel):
    answer: str
    sources: List[SourceCitation]
    needs_review: bool

class AIQuote(BaseModel):
    quote: str

class AIAnswerRequest(BaseModel):
    question: str
    context: str

class AIAnswerResponse(BaseModel):
    answer: str
    sources: List[AIQuote]
    confidence: str
    needs_review: bool

class QARunItem(BaseModel):
    id: str
    created_at: str
    question: str
    answer: str
    sources: List[SourceCitation]
    needs_review: bool
    error: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables on startup
    database.init_db()
    yield

app = FastAPI(
    title="Team Knowledge Base & Memory System",
    description="Corporate knowledge base API with verifiable source citations and audit trails",
    version="1.0.0",
    lifespan=lifespan
)

# API Endpoints

@app.post("/kb/documents", response_model=AddDocumentResponse, status_code=status.HTTP_200_OK)
def add_document(payload: AddDocumentRequest):
    start = time.perf_counter()
    action = "add_document"
    input_data = {"title": payload.title, "text_length": len(payload.text)}
    try:
        snippets = kb_service.chunk_text(payload.text)
        doc_id = database.insert_document(title=payload.title, text=payload.text, snippets=snippets)
        resp = {"status": "ok", "document_id": doc_id}
        duration = (time.perf_counter() - start) * 1000
        database.log_audit(action, input_data, resp, "success", None, duration)
        return resp
    except Exception as e:
        duration = (time.perf_counter() - start) * 1000
        database.log_audit(action, input_data, None, "error", str(e), duration)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/kb/documents", response_model=List[DocumentItem])
def get_documents():
    start = time.perf_counter()
    action = "get_documents"
    try:
        docs = database.list_documents()
        duration = (time.perf_counter() - start) * 1000
        database.log_audit(action, {}, {"count": len(docs)}, "success", None, duration)
        return docs
    except Exception as e:
        duration = (time.perf_counter() - start) * 1000
        database.log_audit(action, {}, None, "error", str(e), duration)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/kb/documents/{document_id}", response_model=DocumentDetail)
def get_document(document_id: str):
    doc = database.get_document_by_id(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc

@app.delete("/kb/documents/{document_id}")
def delete_document_endpoint(document_id: str):
    start = time.perf_counter()
    action = "delete_document"
    input_data = {"document_id": document_id}
    try:
        deleted = database.delete_document(document_id)
        duration = (time.perf_counter() - start) * 1000
        if not deleted:
            database.log_audit(action, input_data, {"status": "not_found"}, "warning", "Document not found", duration)
            raise HTTPException(status_code=404, detail="Document not found")
        
        resp = {"status": "ok", "deleted_document_id": document_id}
        database.log_audit(action, input_data, resp, "success", None, duration)
        return resp
    except HTTPException:
        raise
    except Exception as e:
        duration = (time.perf_counter() - start) * 1000
        database.log_audit(action, input_data, None, "error", str(e), duration)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/kb/ask", response_model=AskQuestionResponse)
def ask_kb(payload: AskQuestionRequest):
    result = kb_service.ask_question(payload.question)
    return result

@app.post("/ai/answer_with_sources", response_model=AIAnswerResponse)
def answer_with_sources_endpoint(payload: AIAnswerRequest):
    start = time.perf_counter()
    action = "ai_answer_with_sources"
    input_data = {"question": payload.question, "context_length": len(payload.context)}
    try:
        result = ai_service.answer_with_sources(payload.question, payload.context)
        duration = (time.perf_counter() - start) * 1000
        status_str = "warning" if result.get("needs_review") else "success"
        database.log_audit(action, input_data, result, status_str, None, duration)
        return result
    except Exception as e:
        duration = (time.perf_counter() - start) * 1000
        database.log_audit(action, input_data, None, "error", str(e), duration)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/kb/history", response_model=List[QARunItem])
def get_history(
    limit: int = Query(default=100, ge=1, le=200),
    needs_review: Optional[bool] = Query(default=None)
):
    runs = database.list_qa_runs(limit=limit, only_needs_review=(needs_review is True))
    return runs

@app.get("/kb/history/{qa_id}", response_model=QARunItem)
def get_history_detail(qa_id: str):
    run = database.get_qa_run_by_id(qa_id)
    if not run:
        raise HTTPException(status_code=404, detail="QA run not found")
    return run

# Static frontend files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def serve_index():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Knowledge Base API is running. UI not found."}
