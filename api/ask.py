"""
Vercel Serverless Function
接收使用者問題，呼叫 blog_qa 邏輯，回傳回答
"""

import json
import os
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler

# 把上層目錄加入 path，才能 import blog_qa
sys.path.insert(0, str(Path(__file__).parent.parent))

from blog_qa import ask


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        # 讀取請求內容
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body)
            question = data.get("question", "").strip()

            if not question:
                self._respond(400, {"error": "問題不能為空"})
                return

            # 呼叫 blog_qa 邏輯
            answer = ask(question, verbose=False)

            self._respond(200, {"answer": answer})

        except Exception as e:
            self._respond(500, {"error": str(e)})

    def do_OPTIONS(self):
        # 處理 CORS preflight
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def _respond(self, status: int, data: dict):
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
