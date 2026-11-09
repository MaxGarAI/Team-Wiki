import sqlite3
import json
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

DB_FILE = "knowledge_base.db"

def get_db_path(db_path: Optional[str] = None) -> str:
    return db_path if db_path is not None else DB_FILE

def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    target_path = get_db_path(db_path)
    conn = sqlite3.connect(target_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(db_path: Optional[str] = None) -> None:
    target_path = get_db_path(db_path)
    conn = get_connection(target_path)
    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            title TEXT NOT NULL,
            text TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS snippets (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            document_id TEXT NOT NULL,
            snippet_text TEXT NOT NULL,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS qa_runs (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            sources_json TEXT NOT NULL,
            needs_review INTEGER NOT NULL,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS audit_runs (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            action TEXT NOT NULL,
            input TEXT,
            output TEXT,
            status TEXT NOT NULL,
            error TEXT,
            duration_ms REAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_snippets_document_id ON snippets(document_id);
        CREATE INDEX IF NOT EXISTS idx_qa_runs_created ON qa_runs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_runs_created ON audit_runs(created_at DESC);
        """)
    conn.close()

def log_audit(
    action: str,
    input_data: Any,
    output_data: Any,
    status: str,
    error: Optional[str] = None,
    duration_ms: float = 0.0,
    db_path: Optional[str] = None
) -> str:
    target_path = get_db_path(db_path)
    audit_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    input_str = json.dumps(input_data, ensure_ascii=False) if input_data is not None else None
    output_str = json.dumps(output_data, ensure_ascii=False) if output_data is not None else None

    conn = get_connection(target_path)
    with conn:
        conn.execute(
            """
            INSERT INTO audit_runs (id, created_at, action, input, output, status, error, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (audit_id, created_at, action, input_str, output_str, status, error, duration_ms)
        )
    conn.close()
    return audit_id

def insert_document(title: str, text: str, snippets: List[str], db_path: Optional[str] = None) -> str:
    target_path = get_db_path(db_path)
    doc_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection(target_path)
    with conn:
        conn.execute(
            "INSERT INTO documents (id, created_at, title, text) VALUES (?, ?, ?, ?)",
            (doc_id, now, title, text)
        )
        snippet_rows = [
            (str(uuid.uuid4()), now, doc_id, snippet)
            for snippet in snippets
        ]
        conn.executemany(
            "INSERT INTO snippets (id, created_at, document_id, snippet_text) VALUES (?, ?, ?, ?)",
            snippet_rows
        )
    conn.close()
    return doc_id

def list_documents(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    target_path = get_db_path(db_path)
    conn = get_connection(target_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, created_at FROM documents ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": row["id"], "title": row["title"], "created_at": row["created_at"]} for row in rows]

def get_document_by_id(doc_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    target_path = get_db_path(db_path)
    conn = get_connection(target_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, text, created_at FROM documents WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row["id"], "title": row["title"], "text": row["text"], "created_at": row["created_at"]}
    return None

def delete_document(doc_id: str, db_path: Optional[str] = None) -> bool:
    target_path = get_db_path(db_path)
    conn = get_connection(target_path)
    with conn:
        cursor = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        deleted = cursor.rowcount > 0
    conn.close()
    return deleted

def get_all_snippets(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    target_path = get_db_path(db_path)
    conn = get_connection(target_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT s.id, s.document_id, s.snippet_text, d.title as document_title
        FROM snippets s
        JOIN documents d ON s.document_id = d.id
        """
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": row["id"],
            "document_id": row["document_id"],
            "snippet_text": row["snippet_text"],
            "document_title": row["document_title"]
        }
        for row in rows
    ]

def insert_qa_run(
    question: str,
    answer: str,
    sources: List[Dict[str, str]],
    needs_review: bool,
    error: Optional[str] = None,
    db_path: Optional[str] = None
) -> str:
    target_path = get_db_path(db_path)
    qa_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    sources_json = json.dumps(sources, ensure_ascii=False)
    conn = get_connection(target_path)
    with conn:
        conn.execute(
            """
            INSERT INTO qa_runs (id, created_at, question, answer, sources_json, needs_review, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (qa_id, now, question, answer, sources_json, 1 if needs_review else 0, error)
        )
    conn.close()
    return qa_id

def list_qa_runs(
    limit: int = 100,
    only_needs_review: bool = False,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    target_path = get_db_path(db_path)
    conn = get_connection(target_path)
    cursor = conn.cursor()
    query = "SELECT id, created_at, question, answer, sources_json, needs_review, error FROM qa_runs"
    params = []
    if only_needs_review:
        query += " WHERE needs_review = 1"
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append({
            "id": r["id"],
            "created_at": r["created_at"],
            "question": r["question"],
            "answer": r["answer"],
            "sources": json.loads(r["sources_json"]) if r["sources_json"] else [],
            "needs_review": bool(r["needs_review"]),
            "error": r["error"]
        })
    return results

def get_qa_run_by_id(qa_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    target_path = get_db_path(db_path)
    conn = get_connection(target_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, created_at, question, answer, sources_json, needs_review, error FROM qa_runs WHERE id = ?",
        (qa_id,)
    )
    r = cursor.fetchone()
    conn.close()
    if r:
        return {
            "id": r["id"],
            "created_at": r["created_at"],
            "question": r["question"],
            "answer": r["answer"],
            "sources": json.loads(r["sources_json"]) if r["sources_json"] else [],
            "needs_review": bool(r["needs_review"]),
            "error": r["error"]
        }
    return None
