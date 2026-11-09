import re
import time
import json
from typing import List, Dict, Any, Tuple, Optional
import database
import ai_service

def chunk_text(text: str) -> List[str]:
    """
    Splits document text into paragraph snippets.
    Removes empty paragraphs and strips extra whitespace.
    """
    raw_paragraphs = re.split(r"\n\s*\n", text)
    snippets = []
    for p in raw_paragraphs:
        cleaned = p.strip()
        if cleaned:
            snippets.append(cleaned)
    if not snippets and text.strip():
        snippets = [text.strip()]
    return snippets

def search_snippets(question: str, db_path: Optional[str] = None, top_k: int = 3) -> List[Dict[str, Any]]:
    """
    Searches snippets using normalized keyword overlap and relevance scoring.
    """
    q_tokens = ai_service.clean_tokens(question)
    if not q_tokens:
        return []

    all_snippets = database.get_all_snippets(db_path=db_path)
    scored: List[Tuple[float, Dict[str, Any]]] = []

    for item in all_snippets:
        s_text = item["snippet_text"]
        s_tokens = ai_service.clean_tokens(s_text)
        if not s_tokens:
            continue

        matched_q_tokens = set()
        total_occurrences = 0
        for qt in q_tokens:
            count = 0
            for st in s_tokens:
                if qt in st or st in qt:
                    count += 1
            if count > 0:
                matched_q_tokens.add(qt)
                total_occurrences += count

        coverage = len(matched_q_tokens) / len(q_tokens)
        score = (coverage * 4.0) + (total_occurrences * 0.3)

        if coverage >= 0.3 or (total_occurrences >= 2 and coverage >= 0.2):
            scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:top_k]]

def ask_question(question: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Processes a question through KB retrieval, answer synthesis, citation matching,
    qa_runs recording, and audit logging.
    """
    start_time = time.perf_counter()
    action = "ask_question"
    input_data = {"question": question}
    error_reason: Optional[str] = None

    try:
        if not question or not question.strip():
            error_reason = "empty_question"
            res = {
                "answer": "Вопрос не может быть пустым.",
                "sources": [],
                "needs_review": True
            }
            duration_ms = (time.perf_counter() - start_time) * 1000
            database.insert_qa_run(
                question=question or "",
                answer=res["answer"],
                sources=[],
                needs_review=True,
                error=error_reason,
                db_path=db_path
            )
            database.log_audit(
                action=action,
                input_data=input_data,
                output_data=res,
                status="error",
                error=error_reason,
                duration_ms=duration_ms,
                db_path=db_path
            )
            return res

        relevant_snippets = search_snippets(question, db_path=db_path, top_k=3)

        if not relevant_snippets:
            error_reason = "no_relevant_sources"
            res = {
                "answer": "Данных недостаточно для ответа на этот вопрос.",
                "sources": [],
                "needs_review": True
            }
        else:
            context_blocks = []
            for snip in relevant_snippets:
                context_blocks.append(snip["snippet_text"])
            combined_context = "\n\n".join(context_blocks)

            ai_result = ai_service.answer_with_sources(question, combined_context)

            if ai_result.get("needs_review") or ai_result.get("confidence") == "low" or not ai_result.get("sources"):
                error_reason = "low_confidence_or_insufficient_data"
                res = {
                    "answer": "Данных недостаточно для ответа на этот вопрос.",
                    "sources": [],
                    "needs_review": True
                }
            else:
                matched_sources = []
                for src in ai_result["sources"]:
                    quote = src["quote"]
                    target_doc_id = relevant_snippets[0]["document_id"]
                    for snip in relevant_snippets:
                        if quote in snip["snippet_text"] or any(w in snip["snippet_text"] for w in quote.split()[:4]):
                            target_doc_id = snip["document_id"]
                            break
                    matched_sources.append({
                        "document_id": target_doc_id,
                        "quote": quote
                    })

                if not matched_sources:
                    error_reason = "no_verified_sources"
                    res = {
                        "answer": "Данных недостаточно для ответа на этот вопрос.",
                        "sources": [],
                        "needs_review": True
                    }
                else:
                    res = {
                        "answer": ai_result["answer"],
                        "sources": matched_sources,
                        "needs_review": False
                    }

        if not res["sources"]:
            res["needs_review"] = True

        duration_ms = (time.perf_counter() - start_time) * 1000

        database.insert_qa_run(
            question=question,
            answer=res["answer"],
            sources=res["sources"],
            needs_review=res["needs_review"],
            error=error_reason,
            db_path=db_path
        )

        database.log_audit(
            action=action,
            input_data=input_data,
            output_data=res,
            status="success" if not error_reason else "warning",
            error=error_reason,
            duration_ms=duration_ms,
            db_path=db_path
        )

        return res

    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        error_msg = str(e)
        res = {
            "answer": "Произошла ошибка при обработке вопроса.",
            "sources": [],
            "needs_review": True
        }
        database.insert_qa_run(
            question=question,
            answer=res["answer"],
            sources=[],
            needs_review=True,
            error=error_msg,
            db_path=db_path
        )
        database.log_audit(
            action=action,
            input_data=input_data,
            output_data=res,
            status="error",
            error=error_msg,
            duration_ms=duration_ms,
            db_path=db_path
        )
        return res
