"""
豁達人生知識庫問答系統（語意搜尋版）
流程：
  1. 使用者提問
  2. 語意搜尋 + 關鍵字比對混合檢索候選文章
  3. Haiku 從候選摘要中選出最相關 3 篇 id
  4. 從 articles.json 撈出完整內容
  5. Sonnet 根據完整內容回答，附出處連結

執行方式：
  python blog_qa.py
  python blog_qa.py "發生戰爭事件想賣股票怎麼辦"
"""

import requests
import json
import sys
import os
import math
import numpy as np
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── 設定 ─────────────────────────────────────────────────
INDEX_FILE    = "blog_index.json"
ARTICLES_FILE = "articles.json"
API_KEY       = os.environ.get("ANTHROPIC_API_KEY", "")
VOYAGE_KEY    = os.environ.get("VOYAGE_API_KEY", "")
HAIKU         = "claude-haiku-4-5-20251001"
SONNET        = "claude-sonnet-4-6"
VOYAGE_MODEL  = "voyage-3"

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


# ── Voyage Embedding（查詢用）─────────────────────────────
def embed_query(text: str) -> list:
    """用 Voyage API 把問題轉成向量"""
    if not VOYAGE_KEY:
        return []

    try:
        resp = requests.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {VOYAGE_KEY}",
            },
            json={
                "input":      [text],
                "model":      VOYAGE_MODEL,
                "input_type": "query",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"⚠️ Voyage 查詢錯誤：{resp.status_code}")
            return []

        data = resp.json()
        return data["data"][0]["embedding"]

    except Exception as e:
        print(f"⚠️ embed_query 錯誤：{e}")
        return []


def cosine_similarity(a: list, b: list) -> float:
    """計算兩個向量的 cosine similarity（Voyage 向量已正規化，dot product 即可）"""
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(np.dot(a, b))


# ── 語意搜尋 ─────────────────────────────────────────────
def semantic_search(query_embedding: list, index: list, top_n: int = CANDIDATE_COUNT) -> list:
    """用向量相似度從索引中找最相關的文章，回傳 [(similarity, entry), ...]"""
    if not query_embedding:
        return []

    scored = []
    for entry in index:
        emb = entry.get("embedding")
        if not emb:
            continue
        sim = cosine_similarity(query_embedding, emb)
        scored.append((sim, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_n]


# ── 關鍵字比對（fallback）────────────────────────────────
def keyword_search(question: str, index: list, top_n: int = CANDIDATE_COUNT) -> list:
    """用關鍵字比對搜尋，回傳 [(score, entry), ...]"""
    # 用問題的 bigram 作為關鍵字
    keywords = list(set(
        question[i:i+2] for i in range(len(question) - 1)
    ))

    scored = []
    for entry in index:
        text = f"{entry.get('title', '')} {entry.get('summary', '')}"
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_n]


# ── 混合搜尋 ─────────────────────────────────────────────
def hybrid_search(question: str, index: list, top_n: int = CANDIDATE_COUNT, verbose: bool = False) -> list:
    """
    混合語意搜尋和關鍵字比對，回傳最終候選文章列表
    語意搜尋權重 0.7，關鍵字權重 0.3
    """
    # 語意搜尋
    query_emb = embed_query(question)
    semantic_results = semantic_search(query_emb, index, top_n=top_n * 2)

    # 關鍵字搜尋
    keyword_results = keyword_search(question, index, top_n=top_n * 2)

    if verbose:
        print(f"\n🔍 語意搜尋 top 5：")
        if not query_emb:
            print(f"   ⚠️ 無法取得 query embedding（VOYAGE_API_KEY 未設定？）")
        for sim, entry in semantic_results[:5]:
            print(f"   {sim:.4f} | {entry['title'][:50]}")
        print(f"\n🔑 關鍵字搜尋 top 5：")
        for score, entry in keyword_results[:5]:
            print(f"   {score:5.0f} 分 | {entry['title'][:50]}")

    # 合併計分
    final_scores = {}

    # 語意搜尋分數：正規化到 0~1 後乘以權重
    if semantic_results:
        max_sim = semantic_results[0][0] if semantic_results[0][0] > 0 else 1
        for sim, entry in semantic_results:
            eid = entry["id"]
            normalized = sim / max_sim if max_sim > 0 else 0
            final_scores[eid] = {
                "entry": entry,
                "score": normalized * 0.7,
            }

    # 關鍵字搜尋分數：正規化後加上去
    if keyword_results:
        max_kw = keyword_results[0][0] if keyword_results[0][0] > 0 else 1
        for kw_score, entry in keyword_results:
            eid = entry["id"]
            normalized = kw_score / max_kw if max_kw > 0 else 0
            if eid in final_scores:
                final_scores[eid]["score"] += normalized * 0.3
            else:
                final_scores[eid] = {
                    "entry": entry,
                    "score": normalized * 0.3,
                }

    # 排序取 top_n
    ranked = sorted(final_scores.values(), key=lambda x: x["score"], reverse=True)

    if verbose:
        print(f"\n📊 混合排序 top 5：")
        for item in ranked[:5]:
            print(f"   {item['score']:.4f} | {item['entry']['title'][:50]}")
        print()

    return [item["entry"] for item in ranked[:top_n]]



# ── Haiku 選出最相關的文章 id ────────────────────────────
def select_top_articles(question: str, candidates: list) -> list:
    if not candidates:
        return []

    candidate_text = ""
    for c in candidates:
        candidate_text += (
            f"[id: {c['id']}] {c['title']}（{c['date']}）\n"
            f"分類：{c.get('category', '')}\n"
            f"摘要：{c['summary']}\n\n"
        )

    prompt = f"""以下是部落格文章候選清單，每篇包含 id、日期、標題、分類、摘要：

{candidate_text}
使用者問題：{question}

請從上面選出最相關的 {TOP_K} 篇文章 id。

選擇規則：
- 如果問題是關於策略定義、優勢、劣勢、比較，且候選中有「策略知識」分類的文章，應優先選取
- 如果同主題有新舊文章，優先選較新的
- 只回傳 {TOP_K} 個 id，每行一個，不要其他文字"""

    result = call_claude(HAIKU, prompt, max_tokens=100)
    valid_ids = {c["id"] for c in candidates}
    ids = [
        line.strip()
        for line in result.strip().split("\n")
        if line.strip() in valid_ids
    ]
    return ids[:TOP_K]


# ── 從 articles.json 撈完整內容 ──────────────────────────
def fetch_articles(ids: list, articles_map: dict) -> list:
    result = []
    for art_id in ids:
        art_id = art_id.strip()
        if art_id in articles_map:
            result.append(articles_map[art_id])
    return result


# ── soul.md 快取 ─────────────────────────────────────────
_soul_cache: str = None

def _load_soul() -> str:
    global _soul_cache
    if _soul_cache is not None:
        return _soul_cache
    soul_path = Path("soul.md")
    if not soul_path.exists():
        soul_path = Path(__file__).parent / "soul.md"
    if soul_path.exists():
        with open(soul_path, "r", encoding="utf-8") as f:
            _soul_cache = f.read()
    else:
        _soul_cache = ""
    return _soul_cache


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

    soul = _load_soul()

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


# ── Sonnet 正式回答 ──────────────────────────────────────
def generate_answer(question: str, articles: list) -> str:
    if not articles:
        return NO_RESULT_MSG

    prompt = build_prompt(question, articles)
    return call_claude(SONNET, prompt, max_tokens=2000)


# ── 載入資料 ─────────────────────────────────────────────
_index_cache: list = None
_articles_cache: dict = None

def load_data() -> tuple:
    global _index_cache, _articles_cache
    if _index_cache is not None:
        return _index_cache, _articles_cache

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

    _index_cache = index
    _articles_cache = articles_map
    return _index_cache, _articles_cache


# ── 主流程 ───────────────────────────────────────────────
def ask(question: str, verbose: bool = True) -> str:
    index, articles_map = load_data()
    if not index:
        return "知識庫載入失敗"

    if verbose:
        print(f"\n❓ 問題：{question}")
        print(f"\n{'─'*50}")

    # 語意 + 關鍵字混合搜尋（不再需要 expand_keywords）
    candidates = hybrid_search(question, index, verbose=verbose)

    if verbose:
        print(f"📋 候選文章：{len(candidates)} 篇")
        for c in candidates[:5]:
            print(f"   - {c['title'][:40]}")

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
        print("豁達人生知識庫問答系統（語意搜尋版）")
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