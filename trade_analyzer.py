"""
豁達人生交易紀錄分類器
從 articles.json 中篩出「交易紀錄」分類的三種文章，各自存成 JSON 檔：
  - special/長期強勢型.json
  - special/短期強勢型.json
  - special/穩定型.json

執行方式：
  python trade_analyzer.py
"""

import json
from pathlib import Path
from datetime import datetime

# ── 設定 ─────────────────────────────────────────────────
ARTICLES_FILE = "articles.json"
SPECIAL_DIR   = "special"

TYPES = [
    ("長期強勢型成長股", "長期強勢型.json"),
    ("短期強勢型成長股", "短期強勢型.json"),
    ("穩定型成長股",     "穩定型.json"),
]


# ── 主程式 ───────────────────────────────────────────────
def main():
    print(f"\n{'='*55}")
    print(f"  豁達人生交易紀錄分類器")
    print(f"  執行時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}\n")

    # 載入文章
    if not Path(ARTICLES_FILE).exists():
        print(f"❌ 找不到 {ARTICLES_FILE}，請先執行 blog_scraper.py")
        return

    with open(ARTICLES_FILE, "r", encoding="utf-8") as f:
        all_articles = json.load(f)

    trade_articles = [a for a in all_articles if a.get("category") == "交易紀錄"]
    print(f"  交易紀錄文章共 {len(trade_articles)} 篇\n")

    # 建立 special/ 資料夾
    Path(SPECIAL_DIR).mkdir(exist_ok=True)

    # 分類存檔
    for keyword, filename in TYPES:
        matched = [a for a in trade_articles if keyword in a.get("title", "")]
        output_path = Path(SPECIAL_DIR) / filename

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(matched, f, ensure_ascii=False, indent=2)

        print(f"  ✅ {filename}：{len(matched)} 篇 → {output_path}")

    print(f"\n{'='*55}")
    print(f"  完成！")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
