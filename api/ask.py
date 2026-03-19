"""
Vercel Serverless Function - 串流版
接收使用者問題，串流回傳 Sonnet 的回答
"""

import json
import os
import sys
import requests as req
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from qa_logger import log_qa
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from blog_qa import (
    expand_keywords, search_candidates,
    select_top_articles, fetch_articles,
    load_data, API_KEY, SONNET
)
from pathlib import Path


def stream_answer(question: str, articles: list):
    """呼叫 Anthropic API 串流版，yield SSE 格式的文字片段"""
    if not articles:
        yield 'data: {"token": "抱歉，找不到相關文章，無法回答這個問題。"}\n\n'
        yield 'data: [DONE]\n\n'
        return

    # 組參考文章區塊
    article_blocks = ""
    for i, art in enumerate(articles, 1):
        content = art.get("content", "")
        if len(content) > 6000:
            content = content[:6000] + "...(以下略)"
        article_blocks += (
            f"文章{i}：{art.get('title', '')}（{art.get('date', '')}）\n"
            f"連結：{art.get('url', '')}\n"
            f"{content}\n\n"
            f"{'─'*40}\n\n"
        )

    # 載入 soul.md
    soul = ""
    soul_path = Path(__file__).parent.parent / "soul.md"
    if soul_path.exists():
        with open(soul_path, "r", encoding="utf-8") as f:
            soul = f.read()

    prompt = f"""{soul}

請根據以下文章內容回答使用者問題。

回答規則：
- 只根據提供的文章內容回答，不要加入文章以外的觀點
- 如果新舊文章觀點有衝突，以新文章為準，並說明觀點的演變
- 回答時清楚標明觀點來自豁達人生的文章，例如「根據豁達人生財經室的文章...」
- 如果觀點來自書籍引用，請明確說明「根據《書名》」
- 如果文章裡沒有相關內容，直接說不知道，不要自行發揮
- 用繁體中文回答
- 不要使用 Markdown 格式，不要用表格、粗體、連結語法，純文字回答
- 回答末尾必須完整列出所有提供給你的參考文章標題和連結，不管有沒有引用到都要全部列出，一篇都不能少

【參考文章】

{article_blocks}
【使用者問題】
{question}"""

    resp = req.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         API_KEY,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model":      SONNET,
            "max_tokens": 1500,
            "stream":     True,
            "messages":   [{"role": "user", "content": prompt}],
        },
        stream=True,
        timeout=60,
    )

    for line in resp.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8")
        if not line.startswith("data: "):
            continue
        raw = line[6:].strip()
        if raw == "[DONE]":
            break
        try:
            event = json.loads(raw)
            if event.get("type") == "content_block_delta":
                token = event.get("delta", {}).get("text", "")
                if token:
                    yield f'data: {json.dumps({"token": token}, ensure_ascii=False)}\n\n'
        except Exception:
            continue

    yield 'data: [DONE]\n\n'


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            data     = json.loads(body)
            question = data.get("question", "").strip()

            if not question:
                self._respond_json(400, {"error": "問題不能為空"})
                return

            index, articles_map = load_data()
            if not index:
                self._respond_json(500, {"error": "知識庫載入失敗"})
                return

            keywords     = expand_keywords(question)
            candidates   = search_candidates(keywords, index, question)

            if not candidates:
                self._respond_json(200, {"answer": "抱歉，知識庫中找不到相關內容。"})
                return

            top_ids      = select_top_articles(question, candidates)
            top_articles = fetch_articles(top_ids, articles_map)

            # 先送 header
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self._set_cors_headers()
            self.end_headers()

            # 串流 + 同時收集 answer
            answer_chunks = []
            for chunk in stream_answer(question, top_articles):
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
                if chunk.startswith('data: ') and '[DONE]' not in chunk:
                    try:
                        obj = json.loads(chunk[6:])
                        answer_chunks.append(obj.get("token", ""))
                    except Exception:
                        pass

            # 串流結束，背景寫 log
            import threading
            full_answer = "".join(answer_chunks)
            threading.Thread(
                target=log_qa,
                args=(question, keywords, len(candidates),
                    top_ids, top_articles, full_answer),
                daemon=True,
            ).start()

        except Exception as e:
            try:
                err_msg = f'data: {json.dumps({"error": str(e)}, ensure_ascii=False)}\n\n'
                self.wfile.write(err_msg.encode("utf-8"))
                self.wfile.write(b'data: [DONE]\n\n')
                self.wfile.flush()
            except Exception:
                pass

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def _respond_json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _set_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format, *args):
        pass  # 關閉預設 log