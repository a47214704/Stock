# 端點診斷報告

產生時間：2026-09-08 11:59:09 UTC
測試日期參數：`（預設：昨天）`

此檔由 `.github/workflows/diagnose.yml` 產生，請勿手動編輯。
把下面各段列出的可用路徑填回 `etl/config.py` 即可。

## TWSE 報表路徑試誤

```
$ python -m etl probe 
以 20260907 逐一測試候選路徑

========================================================================
[price]  params={'type': 'ALLBUT0999', 'response': 'json', 'date': '20260907'}
  ✓ afterTrading/MI_INDEX            可用，1382 列，欄位對得上
  ✗ exchangeReport/MI_INDEX          回應不是 JSON（路徑不存在）
  ✗ afterTrading/STOCK_DAY_ALL       回應不是 JSON（路徑不存在）
========================================================================
[institutional]  params={'selectType': 'ALL', 'response': 'json', 'date': '20260907'}
  ✓ fund/T86                         可用，17350 列，欄位對得上
  △ fund/BFI82U                      有回應（6 列）但欄位對不上，請用 verify 看表頭
  ✗ foreign/T86                      回應不是 JSON（路徑不存在）
  ✗ afterTrading/T86                 回應不是 JSON（路徑不存在）
========================================================================
[margin]  params={'selectType': 'STOCK', 'response': 'json', 'date': '20260907'}
  ✗ margin/MI_MARGN                  回應不是 JSON（路徑不存在）
  △ marginTrading/MI_MARGN           有回應（1063 列）但欄位對不上，請用 verify 看表頭
  ✗ exchange/MI_MARGN                回應不是 JSON（路徑不存在）
  ✗ afterTrading/MI_MARGN            回應不是 JSON（路徑不存在）
  ✗ fund/MI_MARGN                    回應不是 JSON（路徑不存在）
  ✗ credit/MI_MARGN                  回應不是 JSON（路徑不存在）
========================================================================
[foreign]  params={'selectType': 'ALLBUT0999', 'response': 'json', 'date': '20260907'}
  ✓ fund/MI_QFIIS                    可用，1362 列，欄位對得上
  ✗ foreign/MI_QFIIS                 回應不是 JSON（路徑不存在）
  ✗ afterTrading/MI_QFIIS            回應不是 JSON（路徑不存在）
  ✓ fund/MI_QFIIS_sort_20            可用，20 列，欄位對得上

========================================================================

可用的路徑（填回 etl/config.py 的 TWSE_ENDPOINTS）：

TWSE_ENDPOINTS = {
    "price": f"{TWSE_BASE}/afterTrading/MI_INDEX",
    "institutional": f"{TWSE_BASE}/fund/T86",
    "margin": f"{TWSE_BASE}/marginTrading/MI_MARGN",
    "foreign": f"{TWSE_BASE}/fund/MI_QFIIS",
}
```

## TPEx OpenAPI 端點清單

```
$ python -m etl discover --market tpex
讀取 https://www.tpex.org.tw/openapi/swagger.json
規格共 225 個端點

========================================================================
目前設定的端點是否存在於規格中
  price           /v1/tpex_mainboard_daily_close_quotes            ✗ 不存在
  institutional   /v1/tpex_3itrade_hedge_daily                     ✗ 不存在
  margin          /v1/tpex_margin_balance                          ✗ 不存在
  foreign         /v1/tpex_foreign_dealers_hold                    ✗ 不存在

========================================================================
依關鍵字比對出的候選端點

  [price]  關鍵字 ['收盤', '行情', 'close', 'quote', 'daily_close']
      /tpcgi_change
          上櫃公司治理指數當日收盤指數
      /tpcgi_reward_index
          上櫃公司治理指數歷史收盤指數
      /tpci_change
          櫃買「薪酬指數」當日收盤指數
      /tpci_reward_index
          櫃買「薪酬指數」歷史收盤指數
      /tpex200_change
          櫃買「富櫃200指數」當日收盤指數
      /tpex50_change
          櫃買「富櫃50指數」當日收盤指數

  [institutional]  關鍵字 ['三大法人', '法人', 'institution', '3itrade', 'trade_hedge', 'foreign_trust_dealer']
      /tpex_3insti_daily_trading
          上櫃股票三大法人買賣明細資訊
      /tpex_3insti_summary
          上櫃股票三大法人買賣金額彙總表

  [margin]  關鍵字 ['融資', '融券', 'margin', 'short_sale']
      /tpex_mainboard_margin_balance
          上櫃股票融資融券餘額
      /tpex_margin_sbl
          上櫃股票融券借券賣出餘額
      /tpex_margin_trading_adjust
          上櫃融資融券調整成數
      /tpex_margin_trading_lend
          上櫃融資融券標借
      /tpex_margin_trading_margin_mark
          上櫃平盤下得融(借)券賣出之證券名單
      /tpex_margin_trading_margin_used
          上櫃融資融券使用率報表

  [foreign]  關鍵字 ['外資', '持股', '僑外', 'foreign', 'shareholding', 'holding']
      /mopsfin_t187ap02_O
          上櫃公司持股逾 10% 大股東名單
      /mopsfin_t187ap08_O
          上櫃公司董事、監察人持股不足法定成數彙總表
      /mopsfin_t187ap10_O
          上櫃公司董事、監察人持股不足法定成數連續達3個月以上彙總表
      /mopsfin_t187ap11_O
          上櫃公司董監事持股餘額明細資料
      /mopsfin_t187ap11_R
          興櫃公司董監事持股餘額明細資料
      /mopsfin_t187ap12_O
          上櫃公司每日內部人持股轉讓事前申報表-持股轉讓日報表

========================================================================
把確認過的路徑填回 etl/config.py 的 TPEX_ENDPOINTS，例如：

TPEX_ENDPOINTS = {
    "price": "https://www.tpex.org.tw/openapi/tpcgi_change",
    "institutional": "https://www.tpex.org.tw/openapi/tpex_3insti_daily_trading",
    "margin": "https://www.tpex.org.tw/openapi/tpex_mainboard_margin_balance",
    "foreign": "https://www.tpex.org.tw/openapi/mopsfin_t187ap02_O",
}

（以上只是關鍵字命中的第一個候選，請對照上面的說明挑對的那個）

有 4 個端點需要更正。
```

## 欄位別名驗證

```
$ python -m etl verify --market both 

========================================================================
[TWSE] price
  https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX
  params={'type': 'ALLBUT0999', 'response': 'json', 'date': '20260907'}
  stat='OK'  date='20260907'
  回應中的資料日期（推斷）='20260907'
  top-level keys=['tables', 'type', 'params', 'stat', 'date']

  -- 表格 0：56 列
     表頭：["指數", "收盤指數", "漲跌(+/-)", "漲跌點數", "漲跌百分比(%)", "特殊處理註記"]
     首列：["寶島股價指數", "52,478.80", "<p style ='color:red'>+</p>", "860.80", "1.67", ""]
     欄位對應：✗ 找不到欄位「stock_id」（比對別名 ['證券代號', '股票代號', '代號']）。實際表頭為 ['指數', '收盤指數', '漲跌(+/-)', '漲跌點數', '漲跌百分比(%)', '特殊處理註記']。請跑 `python -m etl verify` 對照後更新 etl/sources 的欄位別名。

  -- 表格 1：48 列
     表頭：["指數", "收盤指數", "漲跌(+/-)", "漲跌點數", "漲跌百分比(%)", "特殊處理註記"]
     首列：["臺灣生技指數", "4,296.31", "<p style ='color:green'>-</p>", "14.87", "-0.34", ""]
     欄位對應：✗ 找不到欄位「stock_id」（比對別名 ['證券代號', '股票代號', '代號']）。實際表頭為 ['指數', '收盤指數', '漲跌(+/-)', '漲跌點數', '漲跌百分比(%)', '特殊處理註記']。請跑 `python -m etl verify` 對照後更新 etl/sources 的欄位別名。

  -- 表格 2：37 列
     表頭：["指數", "收盤指數", "漲跌(+/-)", "漲跌點數", "漲跌百分比(%)", "特殊處理註記"]
     首列：["金融類日報酬兩倍指數", "123,310.00", "<p style ='color:green'>-</p>", "561.97", "-0.45", ""]
     欄位對應：✗ 找不到欄位「stock_id」（比對別名 ['證券代號', '股票代號', '代號']）。實際表頭為 ['指數', '收盤指數', '漲跌(+/-)', '漲跌點數', '漲跌百分比(%)', '特殊處理註記']。請跑 `python -m etl verify` 對照後更新 etl/sources 的欄位別名。

  -- 表格 3：47 列
     表頭：["報酬指數", "收盤指數", "漲跌(+/-)", "漲跌點數", "漲跌百分比(%)", "特殊處理註記"]
     首列：["寶島股價報酬指數", "81,528.17", "<p style ='color:red'>+</p>", "1,337.71", "1.67", ""]
     欄位對應：✗ 找不到欄位「stock_id」（比對別名 ['證券代號', '股票代號', '代號']）。實際表頭為 ['報酬指數', '收盤指數', '漲跌(+/-)', '漲跌點數', '漲跌百分比(%)', '特殊處理註記']。請跑 `python -m etl verify` 對照後更新 etl/sources 的欄位別名。

  -- 表格 4：49 列
     表頭：["報酬指數", "收盤指數", "漲跌(+/-)", "漲跌點數", "漲跌百分比(%)", "特殊處理註記"]
     首列：["臺灣生技報酬指數", "5,052.38", "<p style ='color:green'>-</p>", "17.49", "-0.34", ""]
     欄位對應：✗ 找不到欄位「stock_id」（比對別名 ['證券代號', '股票代號', '代號']）。實際表頭為 ['報酬指數', '收盤指數', '漲跌(+/-)', '漲跌點數', '漲跌百分比(%)', '特殊處理註記']。請跑 `python -m etl verify` 對照後更新 etl/sources 的欄位別名。

  -- 表格 5：36 列
     表頭：["報酬指數", "收盤指數", "漲跌(+/-)", "漲跌點數", "漲跌百分比(%)", "特殊處理註記"]
     首列：["漲升股利150報酬指數", "34,687.53", "<p style ='color:red'>+</p>", "546.18", "1.60", ""]
     欄位對應：✗ 找不到欄位「stock_id」（比對別名 ['證券代號', '股票代號', '代號']）。實際表頭為 ['報酬指數', '收盤指數', '漲跌(+/-)', '漲跌點數', '漲跌百分比(%)', '特殊處理註記']。請跑 `python -m etl verify` 對照後更新 etl/sources 的欄位別名。

  -- 表格 6：17 列
     表頭：["成交統計", "成交金額(元)", "成交股數(股)", "成交筆數"]
     首列：["1.一般股票", "909,693,478,847", "4,732,073,853", "3,971,306"]
     欄位對應：✗ 找不到欄位「stock_id」（比對別名 ['證券代號', '股票代號', '代號']）。實際表頭為 ['成交統計', '成交金額(元)', '成交股數(股)', '成交筆數']。請跑 `python -m etl verify` 對照後更新 etl/sources 的欄位別名。

  -- 表格 7：5 列
     表頭：["類型", "整體市場", "股票"]
     首列：["上漲(漲停)", "7,451(148)", "404(11)"]
     欄位對應：✗ 找不到欄位「stock_id」（比對別名 ['證券代號', '股票代號', '代號']）。實際表頭為 ['類型', '整體市場', '股票']。請跑 `python -m etl verify` 對照後更新 etl/sources 的欄位別名。

  -- 表格 8：1382 列
     表頭：["證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌(+/-)", "漲跌價差", "最後揭示買價", "最後揭示買量", "最後揭示賣價", "最後揭示賣量", "本益比"]
     首列：["00400A", "主動國泰動能高息", "40,033,236", "6,895", "610,555,603", "15.20", "15.34", "15.18", "15.21", "<p>X</p>", "0.00", "15.21", "779", "15.22", "99", "0.00"]
     欄位對應：✓
       amount               → [4] '成交金額' = '610,555,603'
       close                → [8] '收盤價' = '15.21'
       high                 → [6] '最高價' = '15.34'
       low                  → [7] '最低價' = '15.18'
       name                 → [1] '證券名稱' = '主動國泰動能高息'
       open                 → [5] '開盤價' = '15.20'
       stock_id             → [0] '證券代號' = '00400A'
       volume               → [2] '成交股數' = '40,033,236'

========================================================================
[TWSE] institutional
  https://www.twse.com.tw/rwd/zh/fund/T86
  params={'selectType': 'ALL', 'response': 'json', 'date': '20260907'}
  stat='OK'  date='20260907'
  回應中的資料日期（推斷）='20260907'
  top-level keys=['stat', 'date', 'title', 'hints', 'fields', 'data', 'selectType', 'notes', 'total']

  -- 表格 0：17350 列
     表頭：["證券代號", "證券名稱", "外陸資買進股數(不含外資自營商)", "外陸資賣出股數(不含外資自營商)", "外陸資買賣超股數(不含外資自營商)", "外資自營商買進股數", "外資自營商賣出股數", "外資自營商買賣超股數", "投信買進股數", "投信賣出股數", "投信買賣超股數", "自營商買賣超股數", "自營商買進股數(自行買賣)", "自營商賣出股數(自行買賣)", "自營商買賣超股數(自行買賣)", "自營商買進股數(避險)", "自營商賣出股數(避險)", "自營商買賣超股數(避險)", "三大法人買賣超股數"]
     首列：["00403A", "主動統一升級50  ", "130,806,103", "18,797,307", "112,008,796", "0", "0", "0", "0", "0", "0", "135,640,339", "0", "0", "0", "138,523,670", "2,883,331", "135,640,339", "247,649,135"]
     欄位對應：✓
       dealer_net           → [11] '自營商買賣超股數' = '135,640,339'
       foreign_dealer_net   → [7] '外資自營商買賣超股數' = '0'
       foreign_net          → [4] '外陸資買賣超股數(不含外資自營商)' = '112,008,796'
       name                 → [1] '證券名稱' = '主動統一升級50  '
       stock_id             → [0] '證券代號' = '00403A'
       total_net            → [18] '三大法人買賣超股數' = '247,649,135'
       trust_net            → [10] '投信買賣超股數' = '0'

========================================================================
[TWSE] margin
  https://www.twse.com.tw/rwd/zh/margin/MI_MARGN
  params={'selectType': 'STOCK', 'response': 'json', 'date': '20260907'}
  ✗ 請求失敗：https://www.twse.com.tw/rwd/zh/margin/MI_MARGN 的回應不是 JSON（HTTP 200，Content-Type: text/html，內容開頭：'<!DOCTYPE html> <html lang="zh-Hant-tw"> <head> <meta charset="utf-8"> <meta name="viewport" content="width=device-width, initial-scale=1.0"> <title>404</title> <meta name="layout" content="blank"/> <'）。請確認端點路徑是否正確——可用 `python -m etl discover` 列出交易所實際提供的路徑。原始錯誤：Expecting value: line 1 column 1 (char 0)

========================================================================
[TWSE] foreign
  https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS
  params={'selectType': 'ALLBUT0999', 'response': 'json', 'date': '20260907'}
  stat='OK'  date='20260907'
  回應中的資料日期（推斷）='20260907'
  top-level keys=['stat', 'date', 'selectType', 'title', 'hints', 'fields', 'data', 'notes', 'total']

  -- 表格 0：1362 列
     表頭：["證券代號", "證券名稱", "國際證券編碼", "發行股數", "外資及陸資尚可投資股數", "全體外資及陸資持有股數", "外資及陸資尚可投資比率", "全體外資及陸資持股比率", "外資及陸資共用法令投資上限比率", "陸資法令投資上限比率", "與前日異動原因(註)", "最近一次上市公司申報外資及陸資持股異動日期"]
     首列：["00400A", "主動國泰動能高息", "TW00000400A3", "1,906,140,000", "1,850,256,449", "55,883,551", 97.06, 2.93, "100.00", "100.00", "", "115/04/10"]
     欄位對應：✓
       holding_ratio        → [7] '全體外資及陸資持股比率' = 2.93
       issued_shares        → [3] '發行股數' = '1,906,140,000'
       name                 → [1] '證券名稱' = '主動國泰動能高息'
       remaining_shares     → [4] '外資及陸資尚可投資股數' = '1,850,256,449'
       shares_held          → [5] '全體外資及陸資持有股數' = '55,883,551'
       stock_id             → [0] '證券代號' = '00400A'

========================================================================
[TPEx] price
  https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes
  回傳 10991 列
  首列 keys：['Date', 'SecuritiesCompanyCode', 'CompanyName', 'Close', 'Change', 'Open', 'High', 'Low', 'Average', 'TradingShares', 'TransactionAmount', 'TransactionNumber', 'LatestBidPrice', 'LatesAskPrice', 'Capitals', 'NextReferencePrice', 'NextLimitUp', 'NextLimitDown']
  首列：{"Date": "1150908", "SecuritiesCompanyCode": "00411A", "CompanyName": "主動統一前沿科技", "Close": "9.76", "Change": "-0.05 ", "Open": "9.87", "High": "9.87", "Low": "9.76", "Average": "9.81", "TradingShares": "16833668", "TransactionAmount": "165167729", "TransactionNumber": "1566", "LatestBidPrice": "9.76", "LatesAskPrice": "9.77", "Capitals": "632076000", "NextReferencePrice": "9.76", "NextLimitUp": "9 …

========================================================================
[TPEx] institutional
  https://www.tpex.org.tw/openapi/v1/tpex_3itrade_hedge_daily
  ✗ 請求失敗：https://www.tpex.org.tw/openapi/v1/tpex_3itrade_hedge_daily 的回應不是 JSON（HTTP 200，Content-Type: text/html，內容開頭：'<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>è\xad\x89å\x88¸æ«\x83æª¯è²·è³£ä¸\xadå¿\x83</title><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1, user-sc'）。請確認端點路徑是否正確——可用 `python -m etl discover` 列出交易所實際提供的路徑。原始錯誤：Expecting value: line 1 column 1 (char 0)

========================================================================
[TPEx] margin
  https://www.tpex.org.tw/openapi/v1/tpex_margin_balance
  ✗ 請求失敗：https://www.tpex.org.tw/openapi/v1/tpex_margin_balance 的回應不是 JSON（HTTP 200，Content-Type: text/html，內容開頭：'<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>è\xad\x89å\x88¸æ«\x83æª¯è²·è³£ä¸\xadå¿\x83</title><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1, user-sc'）。請確認端點路徑是否正確——可用 `python -m etl discover` 列出交易所實際提供的路徑。原始錯誤：Expecting value: line 1 column 1 (char 0)

========================================================================
[TPEx] foreign
  https://www.tpex.org.tw/openapi/v1/tpex_foreign_dealers_hold
  ✗ 請求失敗：https://www.tpex.org.tw/openapi/v1/tpex_foreign_dealers_hold 的回應不是 JSON（HTTP 200，Content-Type: text/html，內容開頭：'<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>è\xad\x89å\x88¸æ«\x83æª¯è²·è³£ä¸\xadå¿\x83</title><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1, user-sc'）。請確認端點路徑是否正確——可用 `python -m etl discover` 列出交易所實際提供的路徑。原始錯誤：Expecting value: line 1 column 1 (char 0)

========================================================================
有 4 個端點需要處理，請依上面印出的表頭調整 etl/sources/ 的欄位別名。
（此步驟回報有問題，詳見上方輸出）
```
