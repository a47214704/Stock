# 台股選股系統 — 資料來源評估

針對四項選股條件的資料需求盤點與串接方式。結論：**四項條件所需資料，官方免費公開 API 全部涵蓋，不需付費資料源。**

---

## 一、條件 → 資料需求對照

| # | 選股條件 | 實際需要的原始資料 | 回看期間 |
|---|---|---|---|
| 1 | 盤整 3 個月以上 | 日 K（開高低收、量） | ≥ 6 個月（約 120 個交易日） |
| 2 | 季線扣底翻揚 | 日收盤價 | ≥ 120 個交易日（算 MA60 + 未來扣抵值） |
| 3a | 融資餘額連 3 月遞減 | 個股每日融資餘額（張） | ≥ 4 個月 |
| 3b | 外資庫存持續增加 | 個股外資**持股張數**（存量，非買賣超） | ≥ 4 個月 |
| 3c | 三大法人合計買超 | 個股外資/投信/自營商每日買賣超 | 依判斷窗口（5～20 日） |
| 4 | MACD 由綠轉紅 | 日收盤價 | ≥ 半年（EMA 需暖機期） |

重點：全部條件的輸入只有四種資料 —— **日 K、融資餘額、外資持股張數、三大法人買賣超**。前兩項與 MACD/季線都只吃收盤價序列，不需要額外資料源。

---

## 二、推薦方案

### 主力：交易所官方 OpenAPI（免費、無需申請、資料權威）

上市（TWSE）與上櫃（TPEx）是**兩套獨立 API**，兩邊都要接才有完整台股。

**上市 — 臺灣證券交易所**

| 資料 | 端點 | 說明 |
|---|---|---|
| 個股日 K | `https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date=YYYYMMDD&stockNo=2330&response=json` | 一次回傳該月整月日 K |
| 全市場當日收盤 | `https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL` | 只有**當日**快照，適合每日增量 |
| 三大法人買賣超 | `https://www.twse.com.tw/rwd/zh/fund/T86?date=YYYYMMDD&selectType=ALL&response=json` | 全市場個股，可指定日期回補歷史 |
| 融資融券餘額 | `MI_MARGN`，路徑分段待 `python -m etl probe` 試出（`margin/` 實測不正確） | `selectType=STOCK` 才是個股明細 |
| 外資及陸資持股 | `https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS?date=YYYYMMDD&selectType=ALLBUT0999&response=json` | **條件 3b 的核心**：持股張數與比率。當日查不到，隔一個交易日才公布 |
| 上市公司基本資料 | `https://openapi.twse.com.tw/v1/opendata/t187ap03_L` | 建立股票代號主檔 |

**上櫃 — 證券櫃檯買賣中心**
API 目錄與 schema：`https://www.tpex.org.tw/openapi/`（Swagger：`https://www.tpex.org.tw/openapi/swagger.json`）
涵蓋上櫃的日收盤行情、三大法人（個股/彙總）、融資融券、本益比、注意處置股、除權息等，欄位命名與 TWSE 不同，ETL 需各寫一組 parser 正規化成同一張表。

### 備援／開發加速：FinMind

`https://api.finmindtrade.com/api/v4/data?dataset=<name>&data_id=2330&start_date=...&end_date=...&token=<token>`

一支 API 就把上市＋上櫃、歷史回補全包，開發初期最省事：

| 條件 | dataset |
|---|---|
| 1 / 2 / 4 | `TaiwanStockPrice` |
| 3a | `TaiwanStockMarginPurchaseShortSale` |
| 3b | `TaiwanStockShareholding`（外資持股） |
| 3c | `TaiwanStockInstitutionalInvestorsBuySell` |
| 股票主檔 | `TaiwanStockInfo` |

資料自 2001 年起，每個交易日 21:00 更新。免費 tier 有 API 呼叫次數上限，全市場逐檔回補會很快撞到 —— 建議 **用 FinMind 做一次性歷史回補，之後每日增量改走交易所官方 API**。

### 不建議
- **yfinance / Yahoo**：只有價量，完全沒有籌碼資料，條件 3 整組做不出來。
- **Goodinfo、神秘金字塔等網站爬蟲**：版面易變、明確擋爬蟲，維運成本高。
- **TEJ**：資料品質最好但付費，這個需求用不到。
- **券商 API（富果 Fugle / 永豐 Shioaji / 富邦）**：需開戶綁帳號，強項是即時報價與下單；本專案是盤後選股，用不到即時報價。

---

## 三、架構關鍵決策

**必須自建資料庫每日落地，不能即時查 API。** 三個理由：

1. **`MI_QFIIS`（外資持股）當天查不到，要隔一個交易日才公布。** 實測當日查詢會回「查詢日期大於可查詢最大日期，請重新查詢!」。所以每日 ETL 之後要再跑一次補抓，把前幾天缺的填回既有快照。這份報表本身**吃 `date` 參數、可以回補歷史**（先前推測「只有當日快照、無法回補」是錯的，已修正）。
2. 交易所網站 API 沒有正式使用授權，流量大會被限速／擋 IP。全市場約 1,800 檔逐檔查詢絕不能放在使用者請求路徑上。
3. 選股掃描是全市場交叉比對，DB 一次 query 遠快於 N 次 HTTP。

建議流程：

```
每日 14:30 後 ETL（TWSE + TPEx）
    → 落地 PostgreSQL（daily_price / margin / foreign_holding / institutional_trade）
    → 盤後批次計算指標（MA60、扣抵值、MACD、盤整區間、籌碼趨勢）
    → 寫入 signals 表
    → 前端 / API 只讀 DB
```

抓取禮儀：每次請求間隔 3～5 秒、帶 User-Agent、失敗指數退避重試、已抓日期記錄避免重複請求。

---

## 四、各條件的計算方式

**1. 盤整 3 個月以上**（只需日 K）
取近 60 個交易日，`(區間最高 - 區間最低) / 區間均價 < 15%`（門檻可調），並要求
MA60 斜率接近 0，避免抓到緩跌股——緩跌股的區間可能夠窄，但季線持續下彎。

另外回報箱型**實際持續天數**：先只用幅度往前擴張取最長區段，再檢驗該區段的
淨漂移（|迴歸斜率| × 天數 / 箱寬）是否遠小於 1。只看幅度會把趨勢股誤報成盤整，
因為趨勢股在區間拉開前必然有一段「夠窄」的天數。

**2. 季線扣底翻揚**（只需收盤價）
季線 = MA60。扣抵值 = 60 個交易日前的收盤價，也就是明天計算 MA60 時「即將被扣掉」的那一根。

- 今日收盤 > 扣抵值 → 明日 MA60 上升
- 未來 5～20 日的扣抵值（即 T-60 ~ T-40 那段收盤）持續走低 → 只要股價不破底，季線就會由下彎轉為翻揚

篩選寫法：`MA60 目前斜率 ≤ 0`（還在下彎或剛走平）**且**`未來 N 日扣抵值呈下降`**且**`今日收盤 > 目前扣抵值`。這正是「剛剛要往上」的量化定義。

**3. 籌碼面**
- 3a 融資：取近 3 個月融資餘額，按月（或 20 日）分段比較，要求逐段遞減；用線性回歸斜率為負更穩健，可容忍短期雜訊。
- 3b 外資庫存：`MI_QFIIS` 的外資持股張數，同樣做 3 個月趨勢，要求遞增。**注意別用三大法人買賣超累加代替** —— 那是流量不是存量，會漏掉鉅額轉帳、ETF 調整等造成的差異。
- 3c 合計買超：T86 的外資 + 投信 + 自營商買賣超股數，在判斷窗口內加總 > 0。

**4. MACD 由綠轉紅**
DIF = EMA12 - EMA26，MACD(訊號線) = DIF 的 EMA9，柱狀體 OSC = DIF - MACD。
「由綠轉紅」= OSC 由負轉正，即 `OSC[t-1] < 0 且 OSC[t] > 0`。「收斂」= OSC 絕對值連續數日縮小。EMA 需要暖機，至少餵 半年 資料再取最後結果。

---

## 五、資料表草案

```sql
stock_info        (stock_id PK, name, market, industry)
daily_price       (stock_id, date, open, high, low, close, volume)          PK(stock_id, date)
margin_trading    (stock_id, date, margin_balance, short_balance)           PK(stock_id, date)
foreign_holding   (stock_id, date, shares_held, holding_ratio)              PK(stock_id, date)
institutional     (stock_id, date, foreign_net, trust_net, dealer_net)      PK(stock_id, date)
```

四張表都以 `(stock_id, date)` 為主鍵，ETL 用 upsert 保證重跑不會重複。

---

## 附註

本文件的端點路徑來自官方文件與公開資料整理；因本次開發環境的網路政策封鎖了 `twse.com.tw`、`tpex.org.tw`、`finmindtrade.com` 對外連線，**未能實際發送請求驗證回傳內容**。實作第一步請先在可連外的環境逐一打通這些端點、確認欄位名稱後再寫 parser。

## 參考連結

- [臺灣證券交易所 OpenAPI](https://openapi.twse.com.tw/)
- [TWSE 三大法人買賣超日報 T86](https://www.twse.com.tw/zh/trading/foreign/t86.html)
- [TWSE 融資融券彙總 MI_MARGN](https://www.twse.com.tw/en/trading/margin/mi-margn.html)
- [TWSE 外資及陸資投資持股統計 MI_QFIIS](https://www.twse.com.tw/en/trading/foreign/mi-qfiis.html)
- [TWSE 個股日成交資訊 STOCK_DAY](https://www.twse.com.tw/en/trading/historical/stock-day.html)
- [櫃買中心 TPEx OpenAPI](https://www.tpex.org.tw/openapi/)
- [FinMind 資料集總覽](https://finmind.github.io/tutor/TaiwanMarket/DataList/)
- [FinMind 籌碼面資料集](https://finmind.github.io/tutor/TaiwanMarket/Chip/)
