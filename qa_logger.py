import os
import requests as req_lib

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

def log_qa(question: str, keywords: list, candidate_count: int,
           top_ids: list, articles: list, answer: str):

    print(f"[log_qa] 開始寫入 question={question[:20]}")
    print(f"[log_qa] URL={SUPABASE_URL[:30] if SUPABASE_URL else 'EMPTY'}")
    print(f"[log_qa] KEY={SUPABASE_KEY[:20] if SUPABASE_KEY else 'EMPTY'}")

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[log_qa] 環境變數未設定，跳過")
        return

    try:
        r = req_lib.post(
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
                "answer": answer,
            },
            timeout=5,
        )
        print(f"[log_qa] 狀態碼={r.status_code} 回應={r.text[:100]}")
    except Exception as e:
        print(f"[log_qa] 例外={e}")