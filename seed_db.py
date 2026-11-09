import json
import os
import database
import kb_service

def seed_database():
    database.init_db()
    docs_path = os.path.join(os.path.dirname(__file__), "tests_data", "kb_documents.jsonl")
    if not os.path.exists(docs_path):
        print(f"Error: {docs_path} not found.")
        return

    # Check existing documents
    existing = database.list_documents()
    existing_titles = {d["title"] for d in existing}

    with open(docs_path, "r", encoding="utf-8") as f:
        docs = [json.loads(line) for line in f if line.strip()]

    added = 0
    for doc in docs:
        if doc["title"] not in existing_titles:
            snippets = kb_service.chunk_text(doc["text"])
            database.insert_document(title=doc["title"], text=doc["text"], snippets=snippets)
            added += 1

    print(f"Database seeded successfully. Added {added} new documents (total: {len(existing) + added}).")

if __name__ == "__main__":
    seed_database()
