"""
豁達人生文章爬蟲
支援多分類爬取，目前包含：月報、年度回顧、好書分享、交易紀錄
支援斷點續爬：每爬完一篇立即寫入 articles.json，重跑時自動跳過已爬的文章

執行方式：
  python blog_scraper.py
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import random
import re
from datetime import datetime
from pathlib import Path

# ── 設定 ─────────────────────────────────────────────────
BLOG_SITE   = "huodalife"
OUTPUT_FILE = "articles.json"
PINNED_IDS  = {"9466534769"}  # 置頂文章 id，爬取時跳過

# 爬到新文章後是否自動更新索引（pixnet 來源不穩定時設為 False）
AUTO_INDEX  = False

# 交易紀錄分類只保留標題含以下關鍵字的文章
TRADE_TITLE_KEYWORDS = [
    "長期強勢型成長股",
    "短期強勢型成長股",
    "穩定型成長股",
]

# 要爬的分類清單：(分類名稱, category_id, 總頁數)
# 頁數設 99 當保險，增量更新模式會在整頁都已存在時自動停止
CATEGORIES = [
    ("月報",     "9003584108", 99),
    ("年度回顧", "9003584114", 99),
    ("好書分享", "9003584120", 99),
    ("交易紀錄", "9003584117", 99),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer":    f"https://{BLOG_SITE}.pixnet.net/blog",
}

MONTH_MAP = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}


# ── 狀態管理：每篇寫入一次 ───────────────────────────────
def load_articles() -> dict:
    """載入已存的文章，回傳 {id: article} 的 dict，方便查詢是否已爬"""
    if Path(OUTPUT_FILE).exists():
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            articles = json.load(f)
        return {a["id"]: a for a in articles}
    return {}


def save_article(article: dict, existing: dict):
    """將單篇文章寫入 articles.json"""
    existing[article["id"]] = article
    articles_list = list(existing.values())
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(articles_list, f, ensure_ascii=False, indent=2)


# ── 爬列表頁：取文章清單 ─────────────────────────────────
def fetch_article_list(category_id: str, page: int) -> list:
    """
    爬分類列表頁，回傳該頁所有文章的基本資料
    [{"id", "title", "date", "url"}, ...]
    """
    url = f"https://{BLOG_SITE}.pixnet.net/blog/categories/{category_id}?page={page}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.encoding = "utf-8"

        if resp.status_code != 200:
            print(f"     ❌ HTTP {resp.status_code}")
            return []

        soup   = BeautifulSoup(resp.text, "html.parser")
        result = []

        for div in soup.select("div.article[id^='article-']"):
            art_id = div.get("id", "").replace("article-", "")

            # 過濾空值或已知置頂文章
            if not art_id or art_id in PINNED_IDS:
                continue

            # 標題與連結
            a_tag = div.select_one("li.title h2 a")
            if not a_tag:
                continue
            title = a_tag.get_text(strip=True)
            link  = a_tag.get("href", "")

            # 日期
            pub_li = div.select_one("li.publish")
            date   = ""
            if pub_li:
                month = pub_li.select_one("span.month")
                day   = pub_li.select_one("span.date")
                year  = pub_li.select_one("span.year")
                t     = pub_li.select_one("span.time")
                if month and day and year:
                    m_str = MONTH_MAP.get(month.get_text(strip=True), month.get_text(strip=True))
                    d_str = day.get_text(strip=True).zfill(2)
                    date  = f"{year.get_text(strip=True)}/{m_str}/{d_str}"
                    if t:
                        date += f" {t.get_text(strip=True)}"

            result.append({
                "id":    art_id,
                "title": title,
                "date":  date,
                "url":   link,
            })

        return result

    except Exception as e:
        print(f"     ❌ fetch_article_list 錯誤：{e}")
        return []


# ── 爬文章頁：取完整內容 ─────────────────────────────────
def fetch_article_content(url: str) -> str:
    """
    爬文章頁，取 div.article-content-inner 的純文字
    去掉圖片、廣告 iframe，保留文字段落
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.encoding = "utf-8"

        if resp.status_code != 200:
            print(f"     ❌ HTTP {resp.status_code}")
            return ""

        soup    = BeautifulSoup(resp.text, "html.parser")
        content = soup.select_one("div.article-content-inner")

        if not content:
            print(f"     ⚠️  找不到 article-content-inner")
            return ""

        # 移除圖片
        for tag in content.find_all("img"):
            tag.decompose()

        # 移除廣告 iframe 和廣告容器
        for tag in content.find_all("div", id=lambda x: x and "pixnet_pc_article" in x):
            tag.decompose()
        for tag in content.find_all("iframe"):
            tag.decompose()


        # 標記豁達人生特別強調的藍色粗體文字
        for span in content.find_all('span', style=True):
            style = span.get('style', '').replace(' ', '').lower()
            if 'color:#0000ff' in style or 'color:blue' in style:
                marked = span.get_text(strip=True)
                if marked:
                    span.replace_with(f'【豁達人生特別標注】{marked}【End】')

        # 取純文字，段落間保留換行
        lines = []
        for elem in content.descendants:
            if elem.name == "br":
                lines.append("\n")
            elif elem.name in ("p", "div") and elem.get_text(strip=True):
                lines.append(elem.get_text(strip=True))

        # 合併、壓縮連續空行
        text = "\n".join(lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    except Exception as e:
        print(f"     ❌ fetch_article_content 錯誤：{e}")
        return ""


# ── 標題過濾（交易紀錄專用）────────────────────────────
def should_include(title: str, category_name: str) -> bool:
    """
    交易紀錄分類只保留標題含指定關鍵字的文章
    其他分類全部保留
    """
    if category_name != "交易紀錄":
        return True
    return any(kw in title for kw in TRADE_TITLE_KEYWORDS)


# ── 爬單一分類 ───────────────────────────────────────────
def scrape_category(category_name: str, category_id: str, total_pages: int,
                    existing: dict) -> tuple:
    """
    爬取單一分類的所有文章，回傳 (new_count, skip_count)
    增量更新模式：從第 1 頁開始，整頁都已存在時停止
    """
    total_new  = 0
    total_skip = 0
    total_filtered = 0

    print(f"\n  ── {category_name}（最多 {total_pages} 頁）──")

    for page in range(1, total_pages + 1):
        print(f"  📄 第 {page} 頁...")

        article_list = fetch_article_list(category_id, page)
        if not article_list:
            print(f"     ⚠️  無法取得列表，跳過此頁")
            time.sleep(random.uniform(2.0, 4.0))
            continue

        # 先套用標題過濾
        filtered_list = [
            m for m in article_list
            if should_include(m["title"], category_name)
        ]
        filtered_out = len(article_list) - len(filtered_list)
        if filtered_out > 0:
            print(f"     🔖 標題過濾：略過 {filtered_out} 篇不符合的文章")
            total_filtered += filtered_out

        # 檢查這頁（過濾後）是否全部已存在
        new_in_page = [m for m in filtered_list if m["id"] not in existing]

        # 若整頁原始文章都已存在（不論過濾），代表後面也不會有新文章
        all_existing = all(m["id"] in existing for m in article_list)
        if not new_in_page and all_existing:
            print(f"     ✅ 整頁都已存在，停止爬取")
            break

        for meta in filtered_list:
            art_id = meta["id"]

            # 已爬過就跳過
            if art_id in existing:
                print(f"     ✅ 已存在：{meta['title'][:30]}...")
                total_skip += 1
                continue

            print(f"     🔍 爬取：{meta['title'][:30]}...")

            time.sleep(random.uniform(1.5, 3.0))
            content = fetch_article_content(meta["url"])

            if not content:
                print(f"     ⚠️  內容為空，跳過")
                continue

            article = {
                "id":       art_id,
                "title":    meta["title"],
                "date":     meta["date"],
                "url":      meta["url"],
                "category": category_name,
                "content":  content,
            }

            save_article(article, existing)
            print(f"     💾 已儲存（{len(content)} 字）")
            total_new += 1

        print()
        time.sleep(random.uniform(2.0, 4.0))

    if total_filtered > 0:
        print(f"     🔖 本分類共略過 {total_filtered} 篇不符標題條件的文章")

    return total_new, total_skip


# ── 主程式 ───────────────────────────────────────────────
def main():
    print(f"\n{'='*55}")
    print(f"  豁達人生文章爬蟲")
    print(f"  執行時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    cats_info = "、".join(f"{name}({pages}頁)" for name, _, pages in CATEGORIES)
    print(f"  爬取分類：{cats_info}")
    print(f"  交易紀錄過濾關鍵字：{', '.join(TRADE_TITLE_KEYWORDS)}")
    print(f"{'='*55}")

    existing   = load_articles()
    print(f"\n  已存文章：{len(existing)} 篇")

    total_new  = 0
    total_skip = 0

    for category_name, category_id, total_pages in CATEGORIES:
        new, skip = scrape_category(category_name, category_id, total_pages, existing)
        total_new  += new
        total_skip += skip

    print(f"{'='*55}")
    print(f"  完成！新增 {total_new} 篇，跳過 {total_skip} 篇")
    print(f"  總計 {len(existing)} 篇文章存於 {OUTPUT_FILE}")
    print(f"{'='*55}\n")

    # 有新文章才更新索引（AUTO_INDEX = False 時跳過）
    if total_new > 0 and AUTO_INDEX:
        print('  🔄 發現新文章，開始更新摘要索引...')
        import blog_indexer
        blog_indexer.main()
    elif total_new > 0:
        print('  ℹ️  有新文章，但 AUTO_INDEX=False，請手動執行 blog_indexer.py')
    else:
        print('  ℹ️  無新文章，跳過索引更新')

if __name__ == "__main__":
    main()