import unittest
import os
import json
import tempfile
import sqlite3
from fastapi.testclient import TestClient

import database
import app as app_module
from app import app

class TestKnowledgeBaseService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a temporary test database
        cls.temp_db_fd, cls.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(cls.temp_db_fd)
        database.DB_FILE = cls.temp_db_path

        # Initialize tables
        database.init_db(cls.temp_db_path)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.temp_db_path):
            try:
                os.remove(cls.temp_db_path)
            except Exception:
                pass

    def test_01_document_validation(self):
        # Empty title
        resp = self.client.post("/kb/documents", json={"title": "   ", "text": "Valid text"})
        self.assertEqual(resp.status_code, 422)

        # Empty text
        resp = self.client.post("/kb/documents", json={"title": "Valid title", "text": "  "})
        self.assertEqual(resp.status_code, 422)

        # Valid document
        resp = self.client.post("/kb/documents", json={"title": "Тестовый документ", "text": "Текст первого параграфа.\n\nТекст второго параграфа."})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue("document_id" in data)

    def test_02_load_test_documents(self):
        docs_path = os.path.join(os.path.dirname(__file__), "..", "tests_data", "kb_documents.jsonl")
        self.assertTrue(os.path.exists(docs_path), f"File {docs_path} does not exist")

        with open(docs_path, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        self.assertEqual(len(lines), 5, "Must contain exactly 5 test documents")

        for item in lines:
            resp = self.client.post("/kb/documents", json={"title": item["title"], "text": item["text"]})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["status"], "ok")
            self.assertTrue(bool(data["document_id"]))

        # Verify documents listing
        resp_list = self.client.get("/kb/documents")
        self.assertEqual(resp_list.status_code, 200)
        docs_list = resp_list.json()
        self.assertGreaterEqual(len(docs_list), 5)

    def test_03_run_all_test_questions(self):
        questions_path = os.path.join(os.path.dirname(__file__), "..", "tests_data", "kb_questions.jsonl")
        self.assertTrue(os.path.exists(questions_path), f"File {questions_path} does not exist")

        with open(questions_path, "r", encoding="utf-8") as f:
            questions = [json.loads(line) for line in f if line.strip()]

        self.assertEqual(len(questions), 10, "Must contain exactly 10 test questions")

        found_count = 0
        needs_review_count = 0

        for i, item in enumerate(questions, 1):
            q_text = item["question"]
            expected_review = item["expected_needs_review"]
            why = item.get("why", "")

            resp = self.client.post("/kb/ask", json={"question": q_text})
            self.assertEqual(resp.status_code, 200, f"Error on question {i}: {q_text}")
            data = resp.json()

            actual_review = data["needs_review"]
            sources = data["sources"]
            answer = data["answer"]

            # Assertion: result must strictly match expected_needs_review
            self.assertEqual(
                actual_review,
                expected_review,
                f"Question #{i} '{q_text}' expected needs_review={expected_review} ({why}), but got {actual_review}. Answer: {answer}"
            )

            # Invariant 1: if needs_review is False, sources MUST NOT be empty
            if not actual_review:
                self.assertGreater(len(sources), 0, f"Question #{i} marked verified but sources is empty!")
                for s in sources:
                    self.assertTrue(bool(s["document_id"]))
                    self.assertTrue(bool(s["quote"]))
                found_count += 1
            else:
                needs_review_count += 1

            # Invariant 2: if sources is empty, needs_review MUST be True
            if len(sources) == 0:
                self.assertTrue(actual_review, f"Question #{i} has empty sources but needs_review is False!")

        self.assertEqual(found_count, 7, f"Expected 7 verified questions, got {found_count}")
        self.assertEqual(needs_review_count, 3, f"Expected 3 questions requiring review, got {needs_review_count}")

    def test_04_ai_answer_with_sources_strict_json(self):
        # 1. Answerable question with context
        context = (
            "Для каждого Pull Request требуется минимум 2 аппрува от старших инженеров или тимлида. "
            "SLA для первичного ответа на код-ревью составляет 4 рабочих часа с момента назначения ревьюера."
        )
        question = "Какой SLA для ответа на код-ревью?"

        resp = self.client.post("/ai/answer_with_sources", json={"question": question, "context": context})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("answer", data)
        self.assertIn("sources", data)
        self.assertIn("confidence", data)
        self.assertIn("needs_review", data)

        self.assertFalse(data["needs_review"])
        self.assertIn(data["confidence"], ["high", "medium"])
        self.assertGreater(len(data["sources"]), 0)
        self.assertIn("quote", data["sources"][0])

        # 2. Unanswerable question
        unanswerable_q = "Какая погода на Марсе?"
        resp2 = self.client.post("/ai/answer_with_sources", json={"question": unanswerable_q, "context": context})
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()

        self.assertTrue(data2["needs_review"])
        self.assertEqual(data2["confidence"], "low")
        self.assertEqual(len(data2["sources"]), 0)

    def test_05_history_and_audit(self):
        # Fetch history list
        resp = self.client.get("/kb/history?limit=100")
        self.assertEqual(resp.status_code, 200)
        runs = resp.json()
        self.assertGreater(len(runs), 0)

        # Fetch filtered history (only needs_review)
        resp_filtered = self.client.get("/kb/history?needs_review=true")
        self.assertEqual(resp_filtered.status_code, 200)
        filtered_runs = resp_filtered.json()
        for r in filtered_runs:
            self.assertTrue(r["needs_review"])

        # Fetch history item detail
        qa_id = runs[0]["id"]
        resp_detail = self.client.get(f"/kb/history/{qa_id}")
        self.assertEqual(resp_detail.status_code, 200)
        detail = resp_detail.json()
        self.assertEqual(detail["id"], qa_id)
        self.assertIn("question", detail)
        self.assertIn("answer", detail)

    def test_06_delete_document(self):
        # Create temporary document to delete
        resp = self.client.post("/kb/documents", json={"title": "Временный документ для удаления", "text": "Текст для удаления."})
        self.assertEqual(resp.status_code, 200)
        doc_id = resp.json()["document_id"]

        # Verify document exists
        resp_check = self.client.get(f"/kb/documents/{doc_id}")
        self.assertEqual(resp_check.status_code, 200)

        # Delete document
        resp_del = self.client.delete(f"/kb/documents/{doc_id}")
        self.assertEqual(resp_del.status_code, 200)
        self.assertEqual(resp_del.json()["status"], "ok")

        # Verify document is gone
        resp_gone = self.client.get(f"/kb/documents/{doc_id}")
        self.assertEqual(resp_gone.status_code, 404)

        # Deleting non-existent document returns 404
        resp_del_again = self.client.delete(f"/kb/documents/{doc_id}")
        self.assertEqual(resp_del_again.status_code, 404)

if __name__ == "__main__":
    unittest.main()
