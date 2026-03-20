"""
豁達人生知識庫索引產生器
讀取 articles.json 和 special/ 底下所有 JSON
用 Haiku 產生每篇摘要，存成 blog_index.json
支援斷點續跑：已產生過摘要的文章直接跳過

執行方式：
  python blog_indexer.py
"""

import requests
import json
import time
import random
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

# ── 設定 ─────────────────────────────────────────────────
ARTICLES_FILE = "articles.json"
SPECIAL_DIR   = "special"
INDEX_FILE    = "blog_index.json"
API_KEY       = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL         = "claude-haiku-4-5-20251001"

SUMMARY_PROMPT = """以下是一篇投資部落格文章，請用 150 字以內繁體中文摘要這篇文章的核心觀點。

摘要需包含：
- 主要投資觀念或決策邏輯
- 提到的具體情境或事件（例如戰爭、系統、情緒、換股、回檔、比較原則）
- 作者的結論或行動
- 作者兩字請寫豁達人生
- 如果是書籍心得，第一句話是豁達人生認為這本書最重要的核心觀點，摘要時必須優先保留，摘要分兩部分：「書摘：」和「心得：」
- 如果是數據統計，摘要需包含關鍵數字和判斷依據
- 不要加標題或粗體字，直接輸出純文字摘要

只回傳摘要文字，不要加任何前言或解釋。

文章標題：{title}
文章分類：{category}
文章日期：{date}

文章內容：
{content}"""


# ── API 呼叫 ─────────────────────────────────────────────
def generate_summary(article: dict) -> str:
    """呼叫 Haiku 產生摘要，回傳摘要文字"""
    if not API_KEY:
        print("  ⚠️  未設定 ANTHROPIC_API_KEY")
        return ""

    # 內容太長就截斷，避免超過 token 限制
    content = article.get("content", "")
    if len(content) > 8000:
        content = content[:8000] + "...(以下略)"

    prompt = SUMMARY_PROMPT.format(
        title    = article.get("title", ""),
        category = article.get("category", ""),
        date     = article.get("date", ""),
        content  = content,
    )

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         API_KEY,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model":      MODEL,
                "max_tokens": 300,
                "messages":   [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )

        if resp.status_code != 200:
            print(f"     ❌ API 錯誤：{resp.status_code} {resp.text}")
            return ""

        data = resp.json()
        return data["content"][0]["text"].strip()

    except Exception as e:
        print(f"     ❌ generate_summary 錯誤：{e}")
        return ""


# ── 狀態管理 ─────────────────────────────────────────────
def load_index() -> dict:
    """載入已存的索引，回傳 {id: entry} 的 dict"""
    if Path(INDEX_FILE).exists():
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            index = json.load(f)
        return {entry["id"]: entry for entry in index}
    return {}


def save_index(index: dict):
    """將索引寫入 blog_index.json"""
    index_list = list(index.values())
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index_list, f, ensure_ascii=False, indent=2)


# ── 讀取所有文章 ─────────────────────────────────────────
def load_all_articles() -> list:
    """讀取 articles.json 和 special/ 底下所有 JSON"""
    articles = []

    # 主文章庫
    if Path(ARTICLES_FILE).exists():
        with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
            articles.extend(json.load(f))
        print(f"  📂 articles.json：{len(articles)} 篇")
    else:
        print(f"  ⚠️  找不到 {ARTICLES_FILE}")

    # special/ 資料夾
    special_path = Path(SPECIAL_DIR)
    if special_path.exists():
        for json_file in sorted(special_path.glob("*.json")):
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 支援單筆或列表
            if isinstance(data, list):
                articles.extend(data)
                print(f"  📂 {json_file.name}：{len(data)} 筆")
            else:
                articles.append(data)
                print(f"  📂 {json_file.name}：1 筆")

    return articles


# ── 主程式 ───────────────────────────────────────────────
def main():
    print(f"\n{'='*55}")
    print(f"  豁達人生知識庫索引產生器")
    print(f"  執行時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  模型：{MODEL}")
    print(f"{'='*55}\n")

    # 讀取所有文章
    print("  載入文章...")
    articles = load_all_articles()
    print(f"  共 {len(articles)} 篇\n")

    # 載入已存索引
    index = load_index()
    print(f"  已有摘要：{len(index)} 篇\n")

    total_new  = 0
    total_skip = 0
    total_fail = 0

    for i, article in enumerate(articles, 1):
        art_id = article.get("id", "")
        title  = article.get("title", "")

        if not art_id:
            continue

        # 已有摘要就跳過
        if art_id in index:
            total_skip += 1
            continue

        print(f"  [{i}/{len(articles)}] {title[:35]}...")

        # 數據參考類直接用 content 當 summary，不呼叫 API
        if article.get("category") == "數據參考":
            summary = article.get("content", "")
            print(f"     📊 數據類，直接使用 content")
        else:
            summary = generate_summary(article)

        if not summary:
            print(f"     ⚠️  摘要產生失敗，跳過")
            total_fail += 1
            continue

        # 寫入索引
        index[art_id] = {
            "id":       art_id,
            "title":    title,
            "date":     article.get("date", ""),
            "url":      article.get("url", ""),
            "category": article.get("category", ""),
            "summary":  summary,
        }

        save_index(index)
        print(f"     ✅ 完成（{len(summary)} 字）")
        total_new += 1

        # 避免 API rate limit
        time.sleep(random.uniform(0.5, 1.0))

    print(f"\n{'='*55}")
    print(f"  完成！新增 {total_new} 篇，跳過 {total_skip} 篇，失敗 {total_fail} 篇")
    print(f"  索引共 {len(index)} 筆，存於 {INDEX_FILE}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
