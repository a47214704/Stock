# 台股選股系統

以 GitHub Actions 每日抓取交易所公開資料，計算技術面與籌碼面指標，
產出靜態 JSON 供純前端讀取。**不需要伺服器、不需要資料庫、不需要費用。**

選股條件：

1. **盤整三個月以上** — 近 60 個交易日高低區間夠窄，且季線接近水平
2. **季線扣底翻揚** — 季線仍下彎，但扣抵值已落到底部區，只要價格守住就會翻揚
3. **籌碼面** — 融資連三個月遞減 ＋ 外資庫存增加 ＋ 三大法人合計買超
4. **MACD** — 柱狀體收斂後由綠轉紅

---

## 快速開始

```bash
pip install -r requirements-dev.txt
python -m pytest -q          # 145 個測試，不需要網路
```

### 第一次部署，請照這個順序

**第 1 步：驗證端點**（必做，5 分鐘）

```bash
python -m etl verify --date 2026-09-05
```

程式裡的欄位別名是依官方文件整理的，**尚未經實際請求驗證**。這個指令會實際
打每個端點、印出真實表頭與第一列資料，並指出哪個欄位對不上。若有欄位對不上，
照著印出的表頭去補 `etl/sources/twse.py` 裡的別名清單即可——欄位是以**表頭
文字**定位的，所以只需要加別名，不必改索引。

**第 2 步：回補歷史**

```bash
python -m etl backfill --start 2026-03-01 --markets twse
```

一天約 4 次請求、每次間隔 4 秒，回補一季約需 40 分鐘。也可以在 GitHub 上用
Actions → 每日 ETL → Run workflow，選 `mode=backfill` 執行。

> 上櫃（TPEx）的 OpenAPI 多半只提供當日資料，**無法回補歷史**，
> 只能從導入日起每日累積。

**第 3 步：確認資料是否足以判斷**

```bash
python -m etl coverage
```

會列出每項條件是否已累積足夠歷史。歷史不足時，選股結果會標成
`insufficient` 而不是 `fail`——這兩者的差別很重要，別把「還不知道」
當成「不符合」。

**第 4 步：開啟排程**

`.github/workflows/etl.yml` 已設定台北時間每個交易日 19:00 自動執行。
推上 GitHub 後在 Actions 頁面啟用即可。

### 日常指令

```bash
python -m etl fetch                      # 抓今天（已有快照會略過）
python -m etl fetch --date 2026-09-05    # 抓指定日期
python -m etl build                      # 重算指標與選股結果
python -m etl coverage                   # 檢查資料累積進度
```

---

## 資料流

```
交易所 API ──fetch──▶ data/daily/YYYY-MM-DD.json  （每日快照，append-only）
                              │
                            build
                              ▼
                  data/signals.json      入選名單與完整判斷依據
                  data/screen_all.json   全市場精簡結果
                  data/history/*.json    入選個股的 K 線與指標
                              │
                              ▼
                        前端 fetch 同源 JSON
```

**每日快照是唯一的真實來源，寫入後不再改動。** 這樣做有三個理由：

- 外資持股（`MI_QFIIS`）官方只給當日快照、沒有歷史查詢端點。每日累積是
  取得庫存趨勢的唯一辦法——**今天不開始存，三個月後才有得分析**。
- git 每天只新增一個 blob，不必重寫既有檔案，repo 成長線性可控。
- 所有衍生產物都能從快照重建，算錯了重跑 `build` 就好。

一個交易日只需要 4 個「全市場報表」端點 × 市場數，約 8 次請求就能取得
全部 1800 檔的價量與籌碼，**不需要逐檔迴圈**。這是整套架構能用免費排程
跑起來的關鍵。

### repo 成長

快照採欄位化編碼（欄位名只出現一次，每檔是值陣列）。以 1800 檔實測：

| | 每日 | 一年（250 天） | 五年 |
|---|---|---|---|
| 原始 | 240 KB | 58 MB | 292 MB |
| git 壓縮後 | 105 KB | 26 MB | 128 MB |

五年約 128 MB，在 GitHub 的建議範圍內。若日後想再壓，可把兩年前的快照
合併成年度檔案封存。

---

## 專案結構

```
etl/
  config.py       端點、抓取節流、選股門檻（要調參數只改這裡）
  http.py         重試與退避
  parsing.py      回應正規化、以表頭文字定位欄位
  sources/
    twse.py       上市
    tpex.py       上櫃
  storage.py      每日快照讀寫、時間序列組裝
  indicators.py   SMA / EMA / MACD / 季線扣抵 / 迴歸斜率（純函式）
  screen.py       四組選股條件
  build.py        產出前端檔案
  verify.py       端點探測
tests/            145 個測試，全部離線執行
```

---

## 調整選股門檻

全部集中在 `etl/config.py` 的 `ScreenConfig`。常用的幾個：

| 參數 | 預設 | 說明 |
|---|---|---|
| `consolidation_max_range_pct` | 0.15 | 盤整區間寬度上限 |
| `deduction_low_percentile` | 0.5 | 扣抵值須落在近半年收盤的下半部 |
| `margin_min_decline_pct` | 0.10 | 融資三個月至少減少 10% |
| `foreign_min_increase_pct` | 0.02 | 外資庫存至少增加 2% |
| `macd_within_days` | 3 | 翻紅後幾天內仍算數 |

`macd_within_days` 值得說明：「由綠轉紅」嚴格說是單日事件，設 1 的話每天
入選的股票會非常少，而且晚看一天就錯過。預設 3 是取捨的結果，代價是名單
會納入已經紅了兩三天的個股。

改完門檻跑 `python -m etl build` 即可重算，不必重抓資料。

---

## 已知限制

- **欄位別名未經實際驗證。** 首次使用務必先跑 `python -m etl verify`。
- **上櫃無法回補歷史。** 見上方第 2 步。
- **回補時的日期防呆。** 若端點忽略 `date` 參數回傳當日資料，程式會偵測到
  日期不符並跳過該筆，避免把今天的數字寫進過去的日期。無法從回應判斷日期
  時只能放行，此時不會宣稱驗證過。
- 交易所公開 API 沒有正式使用授權，請維持低頻率抓取。

相關評估文件見 `docs/data-sources.md` 與 `docs/frontend-only-architecture.md`。
