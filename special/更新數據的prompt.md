# 我上傳了更新後的「中型回檔&黑天鵝回檔數據」xlsx 檔案。

請讀取「大盤數據」和「系統報酬率對比」兩個 sheet，重新產生 special/ 用的 JSON 知識庫檔案。

規則：

- 格式跟上次一樣：JSON 陣列，每筆包含 id、title、date、url、category、content
- id 用 pullback_data_midsize，不要改
- category 用「數據參考」
- url 留空字串
- date 改成檔案中的最新日期
- content 前半段【原始數據】放所有原始表格數據（用 / 分隔欄位），包含：
  - 中型回檔數據統計（年分、回檔幅度、股價60日新低比例最大值、回檔融資餘額減幅）
  - 黑天鵝回檔數據統計（同上欄位）
  - 系統報酬率在回檔中的表現（年分、大盤回檔幅度、回檔前最高報酬率、回檔後報酬率、報酬率回檔幅度、年度報酬率）
- content 後半段【分析】放關鍵觀察
- 產出後給我 JSON 檔案和純文字版方便確認
- 提醒我刪除 blog_index.json 裡 pullback_data_midsize 的舊索引再重跑 blog_indexer.py

# 我上傳了更新後的「豁達人生交易統計」xlsx 檔案。

請讀取「個股操作」、「選股績效」、「年度績效」三個 sheet，重新產生 special/ 用的 JSON 知識庫檔案。

規則：

- 格式跟上次一樣：JSON 陣列，每筆包含 id、title、date、url、category、content
- id 用 trading_stats_overview，不要改
- category 用「數據參考」
- url 留空字串
- date 改成檔案中的最新日期
- content 前半段【原始數據】放所有原始表格數據（用 / 分隔欄位），包含：
  - 個股操作彙總（交易次數、勝率、平均盈虧、賺賠比等）
  - 各策略績效比較（穩定型、衝刺型、強勢型、長期強勢型、短期強勢型）
  - 年度績效（每年的交易次數、勝率、報酬率、大盤漲幅）
  - 持有時間與報酬的關係（分5個區間）
  - 大魚紀錄（報酬超過100%的交易）
  - 最大虧損紀錄（top 5）
  - 主要賣出原因（top 10，依頻率排序）
- content 後半段【分析】放關鍵觀察
- 產出後給我 JSON 檔案和純文字版方便確認
- 提醒我刪除 blog_index.json 裡 trading_stats_overview 的舊索引再重跑 blog_indexer.py
