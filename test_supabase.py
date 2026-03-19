# test_supabase.py
from dotenv import load_dotenv
load_dotenv()

import os
import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

print(f"URL: {SUPABASE_URL}")
print(f"KEY: {SUPABASE_KEY[:20]}...")

resp = requests.post(
    f"{SUPABASE_URL}/rest/v1/qa_logs",
    headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    },
    json={
        "question": "本地端測試問題",
        "keywords": ["測試"],
        "candidate_count": 3,
        "top_ids": ["123"],
        "article_titles": ["測試文章"],
        "answer": "本地端測試回答",
    },
    timeout=10,
)

print(f"狀態碼: {resp.status_code}")
print(f"回應: {resp.text}")