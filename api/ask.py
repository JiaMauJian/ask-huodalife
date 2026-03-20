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
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from blog_qa import (
    expand_keywords, search_candidates,
    select_top_articles, fetch_articles,
    load_data, build_prompt,
    API_KEY, SONNET
)
from qa_logger import log_qa


def stream_answer(question: str, articles: list):
    """呼叫 Anthropic API 串流版，yield SSE 格式的文字片段"""
    if not articles:
        yield 'data: {"token": "抱歉，找不到相關文章，無法回答這個問題。"}\n\n'
        yield 'data: [DONE]\n\n'
        return

    prompt = build_prompt(question, articles)

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

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self._set_cors_headers()
            self.end_headers()

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

            full_answer = "".join(answer_chunks)
            log_qa(
                question=question,
                keywords=keywords,
                candidate_count=len(candidates),
                top_ids=top_ids,
                articles=top_articles,
                answer=full_answer,
            )

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
        pass
