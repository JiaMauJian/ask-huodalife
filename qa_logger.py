import os
import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

def log_qa(question: str, keywords: list, candidate_count: int,
           top_ids: list, articles: list, answer: str):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return

    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/qa_logs",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "question": question,
                "keywords": keywords,
                "candidate_count": candidate_count,
                "top_ids": top_ids,
                "article_titles": [a.get("title", "") for a in articles],
                "answer_preview": answer,
            },
            timeout=5,
        )
    except Exception:
        pass