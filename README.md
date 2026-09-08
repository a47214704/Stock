# 台股選股系統

以 GitHub Actions 每日抓取交易所公開資料，計算技術面與籌碼面指標，
產出靜態 JSON 供純前端讀取。**不需要伺服器、不需要資料庫、不需要費用。**

先講一個實測結果：**四組條件同時成立於可交易個股的機率極低。**
以 2026-09-08 的真實資料（1955 檔、可交易 968 檔）回測最近 6 個基準日，
全中檔數都是 0，差一項的只有 0~1 檔。這不是異常——MACD 由綠轉紅是單日事件，
要和季線剛翻揚在同一天發生本就罕見。所以實用的產出是**依符合項數排序、
標出各檔缺哪一組的觀察名單**，而不是等一份通常為空的全中名單。

選股條件：

0. **流動性下限**（前提，非選股條件）— 20 日中位成交額至少 1000 萬元
1. **盤整三個月以上** — 近 60 個交易日高低區間夠窄，且季線接近水平；
   另外回報箱型**實際已走了幾天**，可依此排序
2. **季線扣底翻揚** — 季線仍下彎，但扣抵值已落到底部區，只要價格守住就會翻揚
3. **籌碼面** — 融資連三個月遞減 ＋ 外資庫存增加 ＋ 三大法人合計買超
4. **MACD** — 柱狀體收斂後由綠轉紅

---

## 快速開始

```bash
pip install -r requirements-dev.txt
python -m pytest -q          # 226 個測試，不需要網路
```

### 不想在本機裝 Python？

診斷步驟都能在 GitHub 上跑，runner 已經有 Python：

**Actions → 端點診斷 → Run workflow**

它會把三項診斷（TWSE 路徑試誤、TPEx 端點清單、欄位驗證）的結果寫成
`docs/endpoint-report.md` 並 commit 回 repo，直接在 GitHub 上就能讀。
回補歷史與每日抓取也一樣走 Actions（見下方第 4、6 步），
全程不需要本機環境。

下面每一步都同時給出本機指令與對應的 Actions 操作。

### 第一次部署，請照這個順序

**第 1 步：試出 TWSE 的報表路徑**（必做）

```bash
python -m etl probe
```

> 在 GitHub 上跑：**Actions → 端點診斷 → Run workflow**，
> 結果看 `docs/endpoint-report.md` 的「TWSE 報表路徑試誤」一節。

TWSE 的 rwd 路徑分段無法從網頁路徑推導——三大法人的網頁在 `/trading/foreign/`
但 rwd 路徑是 `/rwd/zh/fund/T86`，兩者的分段名稱不一致。猜錯時伺服器回的是
HTML 而不是 404。這個指令會把候選路徑一個個打過去，直接指出哪個可用，
並印出可貼回 `TWSE_ENDPOINTS` 的片段。

若所有候選都失敗：到 TWSE 網站按下查詢，從瀏覽器開發者工具的 Network 分頁
複製實際網址，把路徑加進 `etl/config.py` 的 `TWSE_PATH_CANDIDATES`。

**第 2 步：確認 TPEx 端點路徑**（必做）

```bash
python -m etl discover
```

`etl/config.py` 裡的 TPEx 路徑是依文件推測的，**已知至少有一個不正確**。
TPEx 的端點名稱無法從公開文件可靠推斷，而且猜錯時伺服器回的是 HTML 錯誤頁
而不是 404，只看 JSON 解析失敗的訊息查不出原因。

這個指令會讀官方的 OpenAPI 規格，列出真實路徑、指出設定檔裡哪幾個對不上，
並依關鍵字給出候選，最後印出可直接貼回 `TPEX_ENDPOINTS` 的片段。
要自己找的話用 `python -m etl discover --grep 法人`。

> 在 GitHub 上跑：同一個「端點診斷」workflow，
> 結果看報告的「TPEx OpenAPI 端點清單」一節。

TWSE 用的是 `rwd` 報表端點，不在 OpenAPI 規格裡，所以這步只查上櫃。

**第 3 步：驗證欄位**（必做，5 分鐘）

```bash
python -m etl verify --date 2026-09-05
```

程式裡的欄位別名是依官方文件整理的，**尚未經實際請求驗證**。這個指令會實際
打每個端點、印出真實表頭與第一列資料，並指出哪個欄位對不上。若有欄位對不上，
照著印出的表頭去補 `etl/sources/twse.py` 裡的別名清單即可——欄位是以**表頭
文字**定位的，所以只需要加別名，不必改索引。

> 在 GitHub 上跑：同一個「端點診斷」workflow，
> 結果看報告的「欄位別名驗證」一節。

**第 4 步：回補歷史**

```bash
python -m etl backfill --start 2026-03-01 --markets twse
```

一天約 4 次請求、每次間隔 4 秒，回補一季約需 40 分鐘。

> 在 GitHub 上跑：**Actions → 每日 ETL → Run workflow**，`mode` 選
> `backfill`、填入 `start`。回補完它會自動接著跑 `refresh` 與 `build` 並
> commit 結果。

> 上櫃（TPEx）的 OpenAPI 多半只提供當日資料，**無法回補歷史**，
> 只能從導入日起每日累積。上市（TWSE）的報表都吃 `date` 參數，可以回補。

**第 5 步：確認資料是否足以判斷**

```bash
python -m etl coverage
```

會列出每項條件是否已累積足夠歷史。歷史不足時，選股結果會標成
`insufficient` 而不是 `fail`——這兩者的差別很重要，別把「還不知道」
當成「不符合」。

**第 6 步：開啟排程**

`.github/workflows/etl.yml` 已設定台北時間每個交易日 19:00 自動執行。
推上 GitHub 後在 Actions 頁面啟用即可。

前端要另外部署：Settings → Pages 把 Source 設為 **GitHub Actions**，
然後跑一次 **Actions → 部署前端**。之後 `main` 只要有 `web/` 或 `data/`
的變動就會自動重新部署，所以每日 ETL commit 完資料，網站會跟著更新。
在功能分支上開發時不會自動觸發，要用 Run workflow 手動部署。

### 日常指令

```bash
python -m etl fetch                      # 抓今天（已有快照會略過）
python -m etl fetch --date 2026-09-05    # 抓指定日期
python -m etl build                      # 重算指標與選股結果
python -m etl refresh --days 5            # 補抓延遲公布的報表（外資持股）
python -m etl coverage                   # 檢查資料累積進度
python -m etl probe                      # 試出 TWSE 報表路徑
python -m etl discover --grep 融資       # 在 TPEx 官方規格裡搜端點
```

**外資持股要靠 refresh 補。** TWSE 的 `MI_QFIIS` 當天查會回
「查詢日期大於可查詢最大日期」——這份報表要等下一個交易日才公布。
每日 ETL 之後跑 `refresh` 會往回把前幾天缺的補進既有快照，
排程裡已經包含這一步。

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

**每日快照是真實來源，原則上寫入後不再改動。** 這樣做有兩個理由：

- git 每天只新增一個 blob，不必重寫既有檔案，repo 成長線性可控。
- 所有衍生產物都能從快照重建，算錯了重跑 `build` 就好。

唯一的例外是 `refresh`：外資持股一類的報表當天查不到，要等下一個交易日
才公布，只能事後補進既有快照。補的時候只更新快照裡已存在的個股——價格是錨，
沒有 K 線的日期不該憑空長出籌碼資料。

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

## 分支

`main` 是主要分支，也是 GitHub Pages 與每日排程運作的分支：

- **每日 ETL** 的 cron 在預設分支上執行，資料 commit 回同一個分支
- **部署前端** 在 push 到 `main` 且動到 `web/` 或 `data/` 時自動觸發

功能分支上開發時，ETL 與部署都要用 Run workflow 手動觸發，
資料會 commit 到該功能分支而不是 `main`。

---

## 前端

純靜態頁面，零建置步驟、零外部依賴（圖表是手寫的 inline SVG）。

```bash
python tools/gen_demo_data.py     # 產生示範資料（ETL 還沒跑過時用）
python -m http.server 8000        # 從 repo 根目錄起
# 開 http://localhost:8000/web/
```

資料來源會依序試 `data/`、`../data/`、`demo/`，第一個取得到 `signals.json` 的就用。
所以同一份程式在 GitHub Pages、本機開發、以及還沒跑過 ETL 時都不必改設定；
落在示範資料時頁面會顯示提示帶，不會讓人誤以為是真實行情。

也可以用 `?data=<路徑>` 指定來源。

### 部署到 GitHub Pages

`.github/workflows/pages.yml` 會把 `web/` 與 `data/` 組成站台後發布。
在 repo 的 Settings → Pages 把 Source 設為 **GitHub Actions** 即可。
ETL 每天 commit 新資料後會自動觸發重新部署。

### 畫面

- **名單頁**：符合全部條件的檔數（英雄數字）、入選名單、可切換「顯示全市場」。
  搜尋、條件、排序在同一排篩選列，作用於下方所有內容。
- **個股頁**：六項條件各自的判斷依據（含實際數字，不只是過／不過），
  以及四張圖：價格與季線扣抵值、MACD 柱狀體、融資餘額、外資庫存。

### 幾個刻意的取捨

**沒有任何雙 Y 軸圖。** 融資餘額（萬張）與外資庫存（億股）量級差好幾個數量級，
疊在一張圖上會憑空製造出不存在的相關性，所以各自一張圖。

**MACD 用紅漲綠跌。** 紅綠在紅綠色盲下的色差只有 ΔE 4.1（配色的安全門檻是 8），
是常見的地雷配色。這裡仍採台股慣例，理由是柱狀體的正負是靠**零軸上下的位置**
表達的，顏色只是附帶慣例、不承載獨有資訊；讀不出顏色差異時，零軸與表格檢視
都能給出正負。

**每張圖都有表格檢視。** 扣抵值用的青色在淺色底下對比未達 3:1，
規範要求提供替代讀值途徑；表格同時也讓所有數值不必靠 hover 才讀得到。

**圖表支援鍵盤操作。** 聚焦圖表後用左右方向鍵逐日檢視，
顯示的內容與滑鼠 hover 完全相同。

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
  indicators.py   SMA / EMA / MACD / 季線扣抵 / 盤整持續天數 / 迴歸斜率（純函式）
  screen.py       四組選股條件
  build.py        產出前端檔案
  verify.py       端點探測、路徑試誤與 OpenAPI 規格查詢
web/
  index.html      單頁應用，hash 路由
  styles.css      設計 token、深淺色
  charts.js       手寫 SVG 圖表（折線、零軸發散柱狀、表格檢視）
  app.js          資料載入、名單頁、個股頁
  demo/           示範資料，由 tools/gen_demo_data.py 產生
tools/
  gen_demo_data.py
tests/            226 個測試，全部離線執行
```

---

## 調整選股門檻

全部集中在 `etl/config.py` 的 `ScreenConfig`。常用的幾個：

| 參數 | 預設 | 說明 |
|---|---|---|
| `min_median_amount` | 1e7 | 20 日中位成交額下限（流動性前提） |
| `margin_min_balance` | 500 | 融資餘額下限，低於此不視為有效訊號 |
| `macd_require_convergence` | False | 是否把「收斂」列為必要條件 |
| `consolidation_max_range_pct` | 0.15 | 盤整區間寬度上限 |
| `consolidation_max_drift_ratio` | 0.5 | 判定盤整天數時，淨漂移相對箱寬的上限 |
| `deduction_low_percentile` | 0.5 | 扣抵值須落在近半年收盤的下半部 |
| `margin_min_decline_pct` | 0.10 | 融資三個月至少減少 10% |
| `foreign_min_increase_pct` | 0.02 | 外資庫存至少增加 2% |
| `macd_within_days` | 3 | 翻紅後幾天內仍算數 |

`macd_within_days` 值得說明：「由綠轉紅」嚴格說是單日事件，設 1 的話每天
入選的股票會非常少，而且晚看一天就錯過。預設 3 是取捨的結果，代價是名單
會納入已經紅了兩三天的個股。

**流動性門檻不是可選的講究，是必要的。** 不設門檻時實測有兩檔「六項全中」，
但它們 20 日中位成交額只有 70 萬與 170 萬，融資餘額 130 張與 10 張——
「融資三個月減少 40%」其實是減少 4 張。加上門檻後全中歸零，也就是說那兩檔
完全是低流動性造成的假訊號。同理 `margin_min_balance` 讓融資條件在餘額
太小時不成立。

`macd_require_convergence` 預設關閉。「MACD 收斂，由綠轉紅」的訊號本體是
翻紅，收斂是品質描述；列為必要條件時實測全中 0 檔，非必要時 2 檔。
收斂仍會計算並顯示，判斷方式是對翻紅前綠柱的絕對值做迴歸取斜率——
不用「連續 N 天嚴格縮小」，那種寫法一次跳動就歸零，對真實資料太脆。

`consolidation_max_drift_ratio` 是「已盤整天數」的守門條件。單看區間幅度會
把趨勢股誤報成盤整——任何趨勢股在區間拉開前都有一段「夠窄」的天數，長度
大約是門檻 ÷ 每日漲跌幅。所以持續天數的判定分兩步：先只用幅度往前擴張取
最長區段，再檢驗該區段的淨漂移是否遠小於箱寬（趨勢股單向走完整個區間，
比值接近 1；箱型來回震盪，比值明顯偏低）。漂移只驗最終區段而非逐長度——
箱型內部本來就有方向性波段，最後二十天剛好是其中一段時，逐長度檢驗會把整個
箱型否定掉。

改完門檻跑 `python -m etl build` 即可重算，不必重抓資料。

---

## 已知限制

- **TPEx 端點路徑未驗證，已知至少一個錯誤。** 首次使用先跑
  `python -m etl discover`。抓取層遇到「200 但不是 JSON」會立刻失敗並印出
  實際回應內容與狀態碼，不會浪費四輪退避重試。
- **欄位別名未經實際驗證。** 接著跑 `python -m etl verify`。
- **上櫃無法回補歷史。** 見上方第 3 步。
- **回補時的日期防呆。** 若端點忽略 `date` 參數回傳當日資料，程式會偵測到
  日期不符並跳過該筆，避免把今天的數字寫進過去的日期。無法從回應判斷日期
  時只能放行，此時不會宣稱驗證過。
- 交易所公開 API 沒有正式使用授權，請維持低頻率抓取。

相關評估文件見 `docs/data-sources.md` 與 `docs/frontend-only-architecture.md`。
端點診斷的最新結果見 `docs/endpoint-report.md`（由 workflow 產生）。
