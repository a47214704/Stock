# 端點診斷報告

產生時間：2026-09-08 12:49:20 UTC
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

## TPEx OpenAPI 端點比對

```
$ python -m etl discover --market tpex
讀取 https://www.tpex.org.tw/openapi/swagger.json
規格共 225 個端點
規格宣告的 server 基底：https://www.tpex.org.tw/openapi/v1
注意：規格裡的路徑可能不含實際網址的版本前綴，以本專案實測可用的網址為準。

========================================================================
目前設定的端點是否存在於規格中
  price           tpex_mainboard_daily_close_quotes                ✓ 存在
  institutional   tpex_3insti_daily_trading                        ✓ 存在
  margin          tpex_mainboard_margin_balance                    ✓ 存在
  foreign         tpex_foreign_dealers_hold                        ✗ 不存在

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
    "price": f"{TPEX_OPENAPI}/tpcgi_change",
    "institutional": f"{TPEX_OPENAPI}/tpex_3insti_daily_trading",
    "margin": f"{TPEX_OPENAPI}/tpex_mainboard_margin_balance",
    "foreign": f"{TPEX_OPENAPI}/mopsfin_t187ap02_O",
}

（前綴以目前設定的 https://www.tpex.org.tw/openapi/v1 為準；以上只是關鍵字命中的第一個候選，請對照上面的說明挑對的那個）

有 1 個端點需要更正。
```

## TPEx 全部端點清單

```
$ python -m etl discover --market tpex --all
讀取 https://www.tpex.org.tw/openapi/swagger.json
規格共 225 個端點
規格宣告的 server 基底：https://www.tpex.org.tw/openapi/v1
注意：規格裡的路徑可能不含實際網址的版本前綴，以本專案實測可用的網址為準。

========================================================================
全部端點（共 225 個）
  /BDdos209UTF                                         美元零息可贖回國際債券理論價格
  /BDdos215UTF                                         美元附息固定利率可贖回國際債券理論價格
  /BDdos216UTF                                         美元固定利率不可贖回國際債券理論價格
  /bond_ISSBD10_data                                   國際債券(寶島債券)-本國發行人及第一、二上市(櫃)公司之外國發行人發行資料下載
  /bond_ISSBD11_data                                   國際債券(寶島債券)-外國發行人(在我國未公開發行股權商品者)發行資料下載
  /bond_ISSBD1_data                                    公債發行資料下載
  /bond_ISSBD2_data                                    外國金融債發行資料下載
  /bond_ISSBD3_data                                    金融債發行資料下載
  /bond_ISSBD4_data                                    普通債發行資料下載
  /bond_ISSBD5_data                                    轉(交)換債發行資料下載
  /bond_ISSBD6_data                                    海外轉換債發行資料下載
  /bond_ISSBD7_data                                    附認股權公司債發行資料下載
  /bond_ISSBD8_data                                    海外附認股權公司債發行資料下載
  /bond_ISSBD9_data                                    海外普通債發行資料下載
  /bond_cb_daily                                       轉(交)換公司債買賣斷券商買賣日報表
  /mopsfin_187ap17_O                                   上櫃公司營益分析查詢彙總表(全體公司彙總報表)
  /mopsfin_t187ap01                                    券商業務別人員數
  /mopsfin_t187ap02_O                                  上櫃公司持股逾 10% 大股東名單
  /mopsfin_t187ap03_O                                  上櫃股票基本資料
  /mopsfin_t187ap03_R                                  興櫃公司基本資料
  /mopsfin_t187ap04_O                                  上櫃公司每日重大訊息
  /mopsfin_t187ap05_O                                  上櫃公司每月營業收入彙總表
  /mopsfin_t187ap05_OA                                 二十九大類股營收變化統計表
  /mopsfin_t187ap05_OB                                 發行公司營收創新高一覽表(上櫃)
  /mopsfin_t187ap06_O_basi                             上櫃公司綜合損益表(金融業)
  /mopsfin_t187ap06_O_basiA                            上櫃公司財報資訊(金融業)
  /mopsfin_t187ap06_O_bd                               上櫃公司綜合損益表(證券期貨業)
  /mopsfin_t187ap06_O_bdA                              上櫃公司財報資訊(證券期貨業)
  /mopsfin_t187ap06_O_ci                               上櫃公司綜合損益表(一般業)
  /mopsfin_t187ap06_O_ciA                              上櫃公司財報資訊( 一般業)
  /mopsfin_t187ap06_O_fh                               上櫃公司綜合損益表(金控業)
  /mopsfin_t187ap06_O_fhA                              上櫃公司財報資訊(金控業)
  /mopsfin_t187ap06_O_ins                              上櫃公司綜合損益表(保險業)
  /mopsfin_t187ap06_O_insA                             上櫃公司財報資訊(保險業)
  /mopsfin_t187ap06_O_mim                              上櫃公司綜合損益表(異業)
  /mopsfin_t187ap06_O_mimA                             上櫃公司財報資訊(異業)
  /mopsfin_t187ap06_U_basi                             興櫃公司綜合損益表-金融業
  /mopsfin_t187ap06_U_bd                               興櫃公司綜合損益表-證券期貨業
  /mopsfin_t187ap06_U_ci                               興櫃公司綜合損益表-一般業
  /mopsfin_t187ap06_U_fh                               興櫃公司綜合損益表-金控業
  /mopsfin_t187ap06_U_ins                              興櫃公司綜合損益表-保險業
  /mopsfin_t187ap06_U_mim                              興櫃公司綜合損益表-異業
  /mopsfin_t187ap07_O_basi                             上櫃公司資產負債表(金融業)
  /mopsfin_t187ap07_O_bd                               上櫃公司資產負債表(證券期貨業)
  /mopsfin_t187ap07_O_ci                               上櫃公司資產負債表(一般業)
  /mopsfin_t187ap07_O_fh                               上櫃公司資產負債表(金控業)
  /mopsfin_t187ap07_O_ins                              上櫃公司資產負債表(保險業)
  /mopsfin_t187ap07_O_mim                              上櫃公司資產負債表(異業)
  /mopsfin_t187ap07_U_basi                             興櫃公司資產負債表-金融業
  /mopsfin_t187ap07_U_bd                               興櫃公司資產負債表-證券期貨業
  /mopsfin_t187ap07_U_ci                               興櫃公司資產負債表-一般業
  /mopsfin_t187ap07_U_fh                               興櫃公司資產負債表-金控業
  /mopsfin_t187ap07_U_ins                              興櫃公司資產負債表-保險業
  /mopsfin_t187ap07_U_mim                              興櫃公司資產負債表-異業
  /mopsfin_t187ap08_O                                  上櫃公司董事、監察人持股不足法定成數彙總表
  /mopsfin_t187ap09_O                                  上櫃公司董事、監察人質權設定占董事及監察人實際持有股數彙總表
  /mopsfin_t187ap10_O                                  上櫃公司董事、監察人持股不足法定成數連續達3個月以上彙總表
  /mopsfin_t187ap11_O                                  上櫃公司董監事持股餘額明細資料
  /mopsfin_t187ap11_R                                  興櫃公司董監事持股餘額明細資料
  /mopsfin_t187ap12_O                                  上櫃公司每日內部人持股轉讓事前申報表-持股轉讓日報表
  /mopsfin_t187ap13_O                                  上櫃公司每日內部人持股轉讓事前申報表-持股未轉讓日報表
  /mopsfin_t187ap14_O                                  上櫃公司各產業EPS統計資訊
  /mopsfin_t187ap15_O                                  上櫃公司截至各季綜合損益財測達成情形(簡式)
  /mopsfin_t187ap16_O                                  上櫃公司當季綜合損益經會計師查核(核閱)數與當季預測數差異達百分之十以上者，或截至當季累計差異達百分之二十以上者(簡式)
  /mopsfin_t187ap19_O                                  電子式交易統計資訊(上櫃)
  /mopsfin_t187ap22_O                                  上櫃公司金管會證券期貨局裁罰案件專區
  /mopsfin_t187ap23_O                                  上櫃公司違反資訊申報、重大訊息及說明記者會規定專區
  /mopsfin_t187ap24_O                                  上櫃公司經營權及營業範圍異(變)動專區-經營權異動公司
  /mopsfin_t187ap25_O                                  上櫃公司經營權及營業範圍異(變)動專區-營業範圍重大變更公司
  /mopsfin_t187ap26_O                                  上櫃公司經營權及營業範圍異(變)動專區-經營權異動且營業範圍重大變更停止買賣公司
  /mopsfin_t187ap27_O                                  上櫃公司經營權及營業範圍異(變)動專區-經營權異動且營業範圍重大變更列為變更交易公司
  /mopsfin_t187ap29_A_O                                上櫃公司董事酬金相關資訊
  /mopsfin_t187ap29_B_O                                上櫃公司監察人酬金相關資訊
  /mopsfin_t187ap29_C_O                                上櫃公司合併報表董事酬金相關資訊
  /mopsfin_t187ap29_D_O                                上櫃公司合併報表監察人酬金相關資訊
  /mopsfin_t187ap30_O                                  上櫃公司獨立董監事兼任情形彙總表
  /mopsfin_t187ap31_O                                  上櫃公司財務報告經監察人承認情形
  /mopsfin_t187ap32_O                                  上櫃公司公司治理之相關規程規則
  /mopsfin_t187ap33_O                                  上櫃公司董事長是否兼任總經理
  /mopsfin_t187ap34_O                                  上櫃公司採累積投票制、全額連記法、候選人提名制選任董監事及當選資料彙總表
  /mopsfin_t187ap35_O                                  上櫃公司股東行使提案權情形彙總表
  /mopsfin_t187ap36_O                                  上櫃認購(售)權證年度發行量概況統計表
  /mopsfin_t187ap37_O                                  上櫃權證基本資料彙總表
  /mopsfin_t187ap39_O                                  上櫃股利分派情形-董事會通過
  /mopsfin_t187ap42_O                                  上櫃認購(售)權證每日成交資料檔
  /t187ap05_R                                          興櫃公司每月營業收入彙總表
  /t187ap41_O                                          上櫃公司召開股東常 (臨時) 會日期、地點及採用電子投票情形等資料彙總表
  /t187ap46_O_1                                        上櫃公司企業ESG資訊揭露彙總資料-溫室氣體排放
  /t187ap46_O_12                                       上櫃公司企業ESG資訊揭露彙總資料-食品安全
  /t187ap46_O_13                                       上櫃公司企業ESG資訊揭露彙總資料-供應鏈管理
  /t187ap46_O_14                                       上櫃公司企業ESG資訊揭露彙總資料-產品品質與安全
  /t187ap46_O_15                                       上櫃公司企業ESG資訊揭露彙總資料-社區關係
  /t187ap46_O_19                                       上櫃公司企業ESG資訊揭露彙總資料-風險管理政策
  /t187ap46_O_2                                        上櫃公司企業ESG資訊揭露彙總資料-能源管理
  /t187ap46_O_20                                       上櫃公司企業ESG資訊揭露彙總資料-反競爭行為法律訴訟
  /t187ap46_O_21                                       上櫃公司企業ESG資訊揭露彙總資料-職業安全衛生
  /t187ap46_O_3                                        上櫃公司企業ESG資訊揭露彙總資料-水資源管理
  /t187ap46_O_4                                        上櫃公司企業ESG資訊揭露彙總資料-廢棄物管理
  /t187ap46_O_5                                        上櫃公司企業ESG資訊揭露彙總資料-人力發展
  /t187ap46_O_6                                        上櫃公司企業ESG資訊揭露彙總資料-董事會
  /t187ap46_O_7                                        上櫃公司企業ESG資訊揭露彙總資料-投資人溝通
  /t187ap46_O_8                                        上櫃公司企業ESG資訊揭露彙總資料-氣候相關議題管理
  /t187ap46_O_9                                        上櫃公司企業ESG資訊揭露彙總資料-功能性委員會
  /tpcgi_change                                        上櫃公司治理指數當日收盤指數
  /tpcgi_constituents                                  上櫃公司治理指數當日成分股資訊
  /tpcgi_reward_index                                  上櫃公司治理指數歷史收盤指數
  /tpci_change                                         櫃買「薪酬指數」當日收盤指數
  /tpci_constituents                                   櫃買「薪酬指數」當日成分股
  /tpci_reward_index                                   櫃買「薪酬指數」歷史收盤指數
  /tpex200_change                                      櫃買「富櫃200指數」當日收盤指數
  /tpex200_constituents                                櫃買「富櫃200指數」當日成分股
  /tpex50_change                                       櫃買「富櫃50指數」當日收盤指數
  /tpex50_constituents                                 櫃買「富櫃50指數」當日成分股
  /tpex50_index                                        富櫃50指數歷史收盤指數
  /tpex_3insti_daily_trading                           上櫃股票三大法人買賣明細資訊
  /tpex_3insti_dealer_trading                          上櫃股票自營商買賣超彙總表
  /tpex_3insti_qfii                                    上櫃僑外資及陸資持股比例排行表
  /tpex_3insti_qfii_industry                           上櫃各類股僑外資及陸資持股比例表
  /tpex_3insti_qfii_trading                            上櫃股票外資及陸資買賣超彙總表
  /tpex_3insti_summary                                 上櫃股票三大法人買賣金額彙總表
  /tpex_3insti_trading                                 上櫃股票投信買賣超彙總表
  /tpex_active_advanced                                上櫃盤中個股漲幅排行
  /tpex_active_broker_volume                           上櫃股票熱門股證券商進出排行
  /tpex_active_declined                                上櫃盤中個股跌幅排行
  /tpex_active_dollar_volume                           上櫃盤中個股成交金額排行
  /tpex_amount_rank                                    上櫃歷史個股成交值排行
  /tpex_ceil_non_trading                               上櫃漲跌停未成交資訊
  /tpex_cmode                                          上櫃股票變更交易、分盤交易、管理股票與停止交易資訊
  /tpex_daily_broker1                                  上櫃各券商當日營業金額統計表
  /tpex_daily_broker2                                  上櫃股票各券商總公司當日營業金額統計表
  /tpex_daily_market_value                             上櫃歷史個股市值排行
  /tpex_daily_qutoes_block                             上櫃鉅額交易日成交資訊
  /tpex_daily_trade_block_day                          鉅額交易歷史成交資訊
  /tpex_daily_trading_block                            上櫃個股單一證券鉅額交易日成交資訊
  /tpex_daily_trading_index                            上櫃日成交量值指數
  /tpex_daily_trading_summary_odd                      上櫃鉅額交易日成交量值統計
  /tpex_daily_turnover                                 上櫃歷史個股週轉率排行
  /tpex_delayed_stock_close                            上櫃每日暫緩收盤股票
  /tpex_delayed_stock_open                             上櫃每日暫緩開盤股票
  /tpex_disposal_information                           上櫃處置有價證券資訊
  /tpex_dpsp_monthly_CBmcs007                          可轉債資產交換ASO及ASW銀行承作餘額
  /tpex_emp88_change                                   櫃買「勞工就業88指數」當日收盤指數
  /tpex_emp88_constituents                             櫃買「勞工就業88指數」當日成分股
  /tpex_emp88_reward_index                             櫃買「勞工就業88指數」歷史收盤指數
  /tpex_esb_applicant_companies                        申請上櫃公司
  /tpex_esb_capitals_rank                              興櫃公司資本額排名
  /tpex_esb_disposal_information                       興櫃處置有價證券資訊
  /tpex_esb_eps_rank                                   本國興櫃公司EPS排名
  /tpex_esb_highlight                                  興櫃股票市場現況
  /tpex_esb_latest_statistics                          興櫃股票當日行情表
  /tpex_esb_recommended_dealer                         興櫃推薦證券商與推薦之股票
  /tpex_esb_warning_information                        興櫃公布注意有價證券資訊
  /tpex_exright_daily                                  上櫃股票除權除息計算結果表
  /tpex_exright_prepost                                上櫃股票除權除息預告表
  /tpex_gisa_company                                   創櫃板公司資訊
  /tpex_gisa_financing_before                          於登錄創櫃板前辦理籌資資訊
  /tpex_gisa_financing_history                         創櫃板公司透過籌資系統辦理籌資資訊
  /tpex_gisa_financing_in_process                      創櫃板辦理中籌資資訊
  /tpex_gisa_highlight                                 創櫃板公司市場現況
  /tpex_gold_latest                                    黃金現貨當日行情表
  /tpex_gold_market_highlight                          黃金現貨市場現況
  /tpex_gold_recommended_dealer                        造市商與造市之黃金現貨
  /tpex_index                                          櫃買指數歷史資料
  /tpex_index_consti                                   櫃買指數成分股
  /tpex_international_bond_issue_investor              國際債券(一般投資人)
  /tpex_international_bond_issue_org                   國際債券(僅售予專業投資人者)
  /tpex_international_bond_quotes                      國際債券當日盤中報價行情表(含寶島債)
  /tpex_international_bond_trade                       國際債券當日盤中成交行情表(含寶島債)
  /tpex_intraday_fee                                   上櫃應付現股當日沖銷券差借券費率
  /tpex_intraday_trading_his                           上櫃暫停先賣後買當日沖銷交易歷史查詢
  /tpex_intraday_trading_pre                           上櫃暫停先賣後買當日沖銷交易標的預告表
  /tpex_intraday_trading_statistics                    上櫃股票現股當沖交易統計資訊
  /tpex_ipo_no_limit                                   上櫃首五日無漲跌幅資訊
  /tpex_mainboard_daily_close_quotes                   上櫃股票行情
  /tpex_mainboard_margin_balance                       上櫃股票融資融券餘額
  /tpex_mainboard_peratio_analysis                     上櫃股票個股本益比、殖利率、股價淨值比
  /tpex_mainboard_quotes                               上櫃股票收盤行情
  /tpex_mainborad_highlight                            上櫃股票市場現況
  /tpex_margin_sbl                                     上櫃股票融券借券賣出餘額
  /tpex_margin_trading_adjust                          上櫃融資融券調整成數
  /tpex_margin_trading_lend                            上櫃融資融券標借
  /tpex_margin_trading_margin_mark                     上櫃平盤下得融(借)券賣出之證券名單
  /tpex_margin_trading_margin_used                     上櫃融資融券使用率報表
  /tpex_margin_trading_marginspot                      上櫃信用交易餘額概況表
  /tpex_margin_trading_short_sell                      上櫃融資融券增減排行表
  /tpex_margin_trading_term                            上櫃融資融券暫停融券賣出預告表
  /tpex_monthly_trading_summary_block                  上櫃鉅額交易月成交量值統計
  /tpex_odd_stock                                      上櫃股票零股交易資訊
  /tpex_off_market                                     上櫃股票盤後定價行情
  /tpex_opfund_latest                                  開放式基金當日行情表
  /tpex_opfund_market_highlight                        開放式基金市場現況
  /tpex_opfund_recommended_dealer                      開放式基金受益憑證造市商與造市之基金
  /tpex_pe_ratio_top10                                 上櫃歷史個股本益比排行
  /tpex_prvol                                          上櫃股票等價系統成交分價表
  /tpex_reward_index                                   櫃買指數與報酬指數之收市指數
  /tpex_securities                                     上櫃股票現股當沖交易標的資訊
  /tpex_short_sell                                     上櫃當日融券賣出與借券賣出成交量值
  /tpex_spendi_history                                 上櫃歷史公布暫停/恢復交易股票
  /tpex_spendi_today                                   上櫃當日公布暫停/恢復交易股票
  /tpex_trading_amount_avg                             上櫃歷史個股日均值排行
  /tpex_trading_volume_ratio                           上櫃歷史類股成交價量比重
  /tpex_trading_volumes_avg                            上櫃歷史個股日均量排行
  /tpex_trading_warning_information                    上櫃公布注意股票資訊
  /tpex_trading_warning_note                           上櫃公布注意累計次數異常資訊
  /tpex_volume_rank                                    上櫃歷史個股成交量排行
  /tpex_warrant                                        上櫃股票權證資訊
  /tpex_warrant_daily_quts                             上櫃權證收盤行情日報表
  /tpex_warrant_gold                                   黃金現貨權證發行基本資料
  /tpex_warrant_gold_quts                              黃金現貨權證收盤行情
  /tpex_warrant_issue                                  上櫃權證發行基本資料
  /tpex_warrant_monthly_quts                           上櫃權證收盤行情月報表
  /tpex_warrant_quts                                   單筆權證成交資料
  /tpex_warrant_statistics                             每日權證交易人數(上櫃)
  /tpex_warrant_suspend_history                        上櫃權證歷史暫停/恢復交易資訊
  /tpex_warrant_suspend_today                          上櫃權證當日暫停/恢復交易資訊
  /tpex_warrant_wcb_daily_quts                         上櫃牛熊證收盤行情(不含展延型牛熊證)日報表
  /tpex_warrant_wcb_issue                              上櫃牛熊證發行基本資料(不含展延型牛熊證)
  /tpex_warrant_wcb_monthly_quts                       上櫃牛熊證收盤行情(不含展延型牛熊證)月報表
  /tpex_warrant_wxy_daily_quts                         上櫃展延型牛熊證收盤行情日報表
  /tpex_warrant_wxy_issue                              上櫃展延型牛熊證發行基本資料
  /tpex_warrant_wxy_monthly_quts                       上櫃展延型牛熊證收盤行情月報表
  /tpex_yearly_trading_summary_block                   上櫃鉅額交易年成交量值統計
  /tphd_change                                         櫃買「高殖利率指數」當日收盤指數
  /tphd_constituents                                   櫃買「高殖利率指數」當日成分股
  /tphd_index                                          高殖利率指數歷史收盤指數
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
  https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN
  params={'selectType': 'STOCK', 'response': 'json', 'date': '20260907'}
  stat='OK'  date='20260907'
  回應中的資料日期（推斷）='20260907'
  top-level keys=['stat', 'date', 'tables']

  -- 表格 0：1063 列
     表頭：["代號", "名稱", "買進", "賣出", "現金償還", "前日餘額", "今日餘額", "次一營業日限額", "買進", "賣出", "現券償還", "前日餘額", "今日餘額", "次一營業日限額", "資券互抵", "註記"]
     首列：["　", "合計", "320,493", "254,685", "2,713", "6,568,019", "6,631,114", "192,003,069", "25,169", "16,389", "654", "135,944", "126,510", "192,003,069", "5,567", "　"]
     欄位對應：✗ 找不到欄位「margin_balance」（比對別名 ['融資今日餘額', '融資餘額']）。實際表頭為 ['代號', '名稱', '買進', '賣出', '現金償還', '前日餘額', '今日餘額', '次一營業日限額', '買進', '賣出', '現券償還', '前日餘額', '今日餘額', '次一營業日限額', '資券互抵', '註記']。請跑 `python -m etl verify` 對照後更新 etl/sources 的欄位別名。
  ✗ 沒有任何表格能對應到必要欄位，請依上面的表頭更新 etl/sources/twse.py 的別名

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
  https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading
  回傳 895 列
  首列 keys：['Date', 'SecuritiesCompanyCode', 'CompanyName', 'Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Total Buy', ' Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Total Sell', 'Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Difference', 'Foreign Dealers-Total Buy', 'Foreign Dealers-TotalSell', 'ForeignDealers-Difference', 'ForeignInvestorsIncludeMainlandAreaInvestors-TotalBuy', 'ForeignInvestorsIncludeMainlandAreaInvestors-TotalSell', 'ForeignInvestorsInclude MainlandAreaInvestors-Difference', 'SecuritiesInvestmentTrustCompanies-TotalBuy', 'SecuritiesInvestmentTrustCompanies-TotalSell', 'SecuritiesInvestmentTrustCompanies-Difference', 'Dealers-TotalBuy', 'Dealers-TotalSell', 'Dealers-Difference', 'Dealers -TotalSell', 'TotalDifference']
  首列：{"Date": "1150908", "SecuritiesCompanyCode": "00411A", "CompanyName": "主動統一前沿科技", "Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Total Buy": "3033101", " Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Total Sell": "20000", "Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Difference": "3013101", "Foreign Deale …

========================================================================
[TPEx] margin
  https://www.tpex.org.tw/openapi/v1/tpex_mainboard_margin_balance
  回傳 920 列
  首列 keys：['Date', 'SecuritiesCompanyCode', 'CompanyName', 'MarginPurchaseBalancePreviousDay', 'MarginPurchase', 'MarginSales', 'CashRedemption', 'MarginPurchaseBalance', 'MarginPurchaseBalanceBelongSecuritiesFinanceEnterprise', 'MarginPurchaseUtilizationRate', 'MarginPurchaseQuota', 'ShortSaleBalancePreviousDay', 'ShortSale', 'ShortConvering', 'StockRedemption', 'ShortSaleBalance', 'ShortSaleBalanceBelongSecuritiesFinanceEnterprise', 'ShortSaleUtilizationRate', 'ShortSaleQuota', 'Offsetting', 'Note']
  首列：{"Date": "1150907", "SecuritiesCompanyCode": "00411A", "CompanyName": "主動統一前沿科技", "MarginPurchaseBalancePreviousDay": "5594", "MarginPurchase": "120", "MarginSales": "556", "CashRedemption": "0", "MarginPurchaseBalance": "5158", "MarginPurchaseBalanceBelongSecuritiesFinanceEnterprise": "20", "MarginPurchaseUtilizationRate": "3.26", "MarginPurchaseQuota": "158019", "ShortSaleBalancePreviousDay": "0 …

========================================================================
[TPEx] foreign
  https://www.tpex.org.tw/openapi/v1/tpex_foreign_dealers_hold
  ✗ 請求失敗：https://www.tpex.org.tw/openapi/v1/tpex_foreign_dealers_hold 的回應不是 JSON（HTTP 200，Content-Type: text/html，內容開頭：'<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>è\xad\x89å\x88¸æ«\x83æª¯è²·è³£ä¸\xadå¿\x83</title><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1, user-sc'）。請確認端點路徑是否正確——可用 `python -m etl discover` 列出交易所實際提供的路徑。原始錯誤：Expecting value: line 1 column 1 (char 0)

========================================================================
有 2 個端點需要處理，請依上面印出的表頭調整 etl/sources/ 的欄位別名。
（此步驟回報有問題，詳見上方輸出）
```
