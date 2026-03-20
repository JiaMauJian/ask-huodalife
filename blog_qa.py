"""
豁達人生知識庫問答系統
流程：
  1. 使用者提問
  2. Haiku 擴充關鍵字
  3. 程式用關鍵字比對 blog_index.json，篩出候選文章
  4. Haiku 從候選摘要中選出最相關 3 篇 id
  5. 從 articles.json 撈出完整內容
  6. Sonnet 根據完整內容回答，附出處連結

執行方式：
  python blog_qa.py
  python blog_qa.py "發生戰爭事件想賣股票怎麼辦"
"""

import requests
import json
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── 設定 ─────────────────────────────────────────────────
INDEX_FILE    = "blog_index.json"
ARTICLES_FILE = "articles.json"
API_KEY       = os.environ.get("ANTHROPIC_API_KEY", "")
HAIKU         = "claude-haiku-4-5-20251001"
SONNET        = "claude-sonnet-4-6"

CANDIDATE_COUNT = 20
TOP_K           = 3

NO_RESULT_MSG = """這個問題在豁達人生的文章裡找不到直接相關的內容。

你可以直接到以下地方找看看：

[豁達人生財經室部落格](https://huodalife.pixnet.net/blog)
[豁達人生財經室 YouTube](https://www.youtube.com/@豁達人生財經室)"""

SERVICE_ERROR_MSG = """服務暫時無法使用，請稍後再試。

如果問題持續發生，可以直接到以下地方找看看：

[豁達人生財經室部落格](https://huodalife.pixnet.net/blog)
[豁達人生財經室 YouTube](https://www.youtube.com/@豁達人生財經室)"""


# ── API 呼叫 ─────────────────────────────────────────────
def call_claude(model: str, prompt: str, max_tokens: int = 1000) -> str:
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         API_KEY,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model":      model,
                "max_tokens": max_tokens,
                "messages":   [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        data = resp.json()
        if data.get("type") == "error":
            error_type = data.get("error", {}).get("type", "")
            error_msg  = data.get("error", {}).get("message", "未知錯誤")
            print(f"❌ Anthropic API 錯誤：{error_msg}")
            raise Exception(f"{error_type}:{error_msg}")
        return data["content"][0]["text"].strip()
    except Exception as e:
        print(f"❌ API 錯誤：{e}")
        raise


# ── 步驟一：擴充關鍵字 ───────────────────────────────────
def expand_keywords(question: str) -> list:
    prompt = f"""使用者問了一個投資相關問題，請把這個問題擴充成 10 個繁體中文搜尋關鍵字。

要求：
- 每個關鍵字必須是 2~5 個字的短詞，絕對不可以是長句
- 包含同義詞、相關概念、情境描述
- 關鍵字之間用逗號分隔
- 只回傳關鍵字，不要其他文字

範例格式：回檔,恐慌,賣出,靜觀其變,大跌,停損,應對策略,歷史數據,單一事件,情緒

問題：{question}"""

    result = call_claude(HAIKU, prompt, max_tokens=100)
    keywords = [k.strip() for k in result.split(",") if k.strip()]
    return keywords


# ── 步驟二：關鍵字比對摘要索引 ──────────────────────────
def search_candidates(keywords: list, index: list, question: str = "") -> list:
    question_words = [question[i:i+2] for i in range(len(question) - 1)] if question else []
    all_keywords = list(set(keywords + question_words))

    scored = []
    for entry in index:
        text = f"{entry.get('title', '')} {entry.get('summary', '')}"
        score = sum(1 for kw in all_keywords if kw in text)
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored[:CANDIDATE_COUNT]]


# ── 步驟三：Haiku 選出最相關的文章 id ───────────────────
def select_top_articles(question: str, candidates: list) -> list:
    if not candidates:
        return []

    candidate_text = ""
    for c in candidates:
        candidate_text += (
            f"[id: {c['id']}] {c['title']}（{c['date']}）\n"
            f"摘要：{c['summary']}\n\n"
        )

    prompt = f"""以下是部落格文章候選清單，每篇包含 id、日期、標題、摘要：

{candidate_text}
使用者問題：{question}

請從上面選出最相關的 {TOP_K} 篇文章 id。
注意：如果同主題有新舊文章，優先選較新的。
只回傳 {TOP_K} 個 id，每行一個，不要其他文字。"""

    result = call_claude(HAIKU, prompt, max_tokens=100)
    ids = [line.strip() for line in result.strip().split("\n") if line.strip()]
    return ids[:TOP_K]


# ── 步驟四：從 articles.json 撈完整內容 ─────────────────
def fetch_articles(ids: list, articles_map: dict) -> list:
    result = []
    for art_id in ids:
        art_id = art_id.strip()
        if art_id in articles_map:
            result.append(articles_map[art_id])
    return result


# ── 共用 prompt 組裝 ─────────────────────────────────────
def build_prompt(question: str, articles: list) -> str:
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

    soul = ""
    soul_path = Path("soul.md")
    if not soul_path.exists():
        soul_path = Path(__file__).parent / "soul.md"
    if soul_path.exists():
        with open(soul_path, "r", encoding="utf-8") as f:
            soul = f.read()

    return f"""{soul}

請根據以下文章內容回答使用者問題。

回答規則：
- 只根據提供的文章內容回答，不要加入文章以外的觀點
- 如果新舊文章觀點有衝突，以新文章為準，並說明觀點的演變
- 回答時自然地標明觀點來自豁達人生的文章，不需要每次都用固定開頭，避免重複
- 如果觀點來自書籍引用，請明確說明「根據《書名》」
- 好書分享類文章的第一句話是豁達人生認為該書最重要的核心觀點，引用時需特別重視
- 如果文章裡沒有相關內容，直接說不知道，不要自行發揮
- 用繁體中文回答
- 回答內文用純文字，不要用表格、粗體
- 參考文章和引導連結必須嚴格用這個格式，不能加任何其他文字：[標題](連結)
- 參考文章只列出你實際引用到內容的文章，如果某篇文章的內容沒有用到，就不要列出來
- 如果沒有引用到任何文章，就不要列出參考文章區塊

參考文章：
[標題](連結)

【參考文章】

{article_blocks}
【使用者問題】
{question}"""


# ── 步驟五：Sonnet 正式回答 ──────────────────────────────
def generate_answer(question: str, articles: list) -> str:
    if not articles:
        return NO_RESULT_MSG

    prompt = build_prompt(question, articles)
    return call_claude(SONNET, prompt, max_tokens=2000)


# ── 載入資料 ─────────────────────────────────────────────
def load_data() -> tuple:
    if not Path(INDEX_FILE).exists():
        print(f"❌ 找不到 {INDEX_FILE}")
        return [], {}
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        index = json.load(f)

    if not Path(ARTICLES_FILE).exists():
        print(f"❌ 找不到 {ARTICLES_FILE}")
        return index, {}
    with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
        articles_list = json.load(f)
    articles_map = {a["id"]: a for a in articles_list}

    special_path = Path("special")
    if special_path.exists():
        for json_file in special_path.glob("*.json"):
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    articles_map[item["id"]] = item
            else:
                articles_map[data["id"]] = data

    return index, articles_map


# ── 主流程 ───────────────────────────────────────────────
def ask(question: str, verbose: bool = True) -> str:
    index, articles_map = load_data()
    if not index:
        return "知識庫載入失敗"

    if verbose:
        print(f"\n❓ 問題：{question}")
        print(f"\n{'─'*50}")

    try:
        keywords = expand_keywords(question)
    except Exception:
        return SERVICE_ERROR_MSG

    if verbose:
        print(f"🔑 關鍵字：{', '.join(keywords)}")

    candidates = search_candidates(keywords, index, question)
    if verbose:
        print(f"📋 候選文章：{len(candidates)} 篇")

    if not candidates:
        return NO_RESULT_MSG

    try:
        top_ids = select_top_articles(question, candidates)
    except Exception:
        return SERVICE_ERROR_MSG

    if verbose:
        print(f"✅ 選出文章 id：{top_ids}")

    top_articles = fetch_articles(top_ids, articles_map)
    if verbose:
        print(f"📄 載入 {len(top_articles)} 篇完整文章")
        print(f"\n{'─'*50}\n")

    try:
        answer = generate_answer(question, top_articles)
    except Exception:
        return SERVICE_ERROR_MSG

    return answer


# ── 主程式 ───────────────────────────────────────────────
def main():
    if not API_KEY:
        print("❌ 未設定 ANTHROPIC_API_KEY")
        return

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        answer = ask(question)
        print(answer)
    else:
        print("豁達人生知識庫問答系統")
        print("輸入 'quit' 離開\n")
        while True:
            question = input("❓ 請輸入問題：").strip()
            if question.lower() in ("quit", "exit", "q"):
                break
            if not question:
                continue
            answer = ask(question)
            print(f"\n{answer}\n")
            print("─" * 50)


if __name__ == "__main__":
    main()