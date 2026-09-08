"""集中管理端點、抓取行為與選股門檻。"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass

# --- 抓取行為 -------------------------------------------------------------
# 交易所公開 API 沒有正式使用授權，流量過大會被限速或擋 IP。
# 這裡刻意放慢，ETL 一天只跑一次，慢一點無所謂。
REQUEST_DELAY_SEC = float(os.environ.get("ETL_REQUEST_DELAY", "4"))
REQUEST_TIMEOUT_SEC = 30
MAX_RETRIES = 4
RETRY_BACKOFF_SEC = (2, 4, 8, 16)
USER_AGENT = (
    "Mozilla/5.0 (compatible; stock-screener-etl/1.0; "
    "+https://github.com/a47214704/Stock)"
)

# --- 端點 -----------------------------------------------------------------
# 注意：這些路徑取自官方文件整理，尚未經實際請求驗證欄位名稱。
# 第一次部署前請先跑 `python -m etl verify` 確認回傳結構。
TWSE_BASE = "https://www.twse.com.tw/rwd/zh"
TWSE_OPENAPI = "https://openapi.twse.com.tw/v1"
TPEX_OPENAPI = "https://www.tpex.org.tw/openapi/v1"

TWSE_ENDPOINTS = {
    # 每日收盤行情（全部）— 含開高低收，支援 date 參數，可回補歷史
    "price": f"{TWSE_BASE}/afterTrading/MI_INDEX",
    # 三大法人買賣超日報
    "institutional": f"{TWSE_BASE}/fund/T86",
    # 融資融券餘額（selectType=STOCK 才有個股明細）
    # 分段是 marginTrading 而非 margin——由 probe 實測確認
    "margin": f"{TWSE_BASE}/marginTrading/MI_MARGN",
    # 外資及陸資投資持股統計（外資庫存）
    "foreign": f"{TWSE_BASE}/fund/MI_QFIIS",
}

# TWSE 的 rwd 路徑分段無法從網頁路徑推導——T86 的網頁在 /trading/foreign/
# 但 rwd 路徑是 /rwd/zh/fund/T86，兩者的分段名稱不一致。猜錯時伺服器回的是
# HTML 而不是 404，所以用 `python -m etl probe` 逐一試出正確的那個。
# 每個資料集的第一項就是 TWSE_ENDPOINTS 目前採用的路徑。
TWSE_PATH_CANDIDATES = {
    "price": [
        "afterTrading/MI_INDEX", "exchangeReport/MI_INDEX",
        "afterTrading/STOCK_DAY_ALL",
    ],
    "institutional": [
        "fund/T86", "fund/BFI82U", "foreign/T86", "afterTrading/T86",
    ],
    "margin": [
        "marginTrading/MI_MARGN", "exchange/MI_MARGN",
        "afterTrading/MI_MARGN", "fund/MI_MARGN", "credit/MI_MARGN",
    ],
    "foreign": [
        "fund/MI_QFIIS", "foreign/MI_QFIIS", "afterTrading/MI_QFIIS",
        "fund/MI_QFIIS_sort_20",
    ],
}

# 部分報表當日盤後才會公布，甚至隔一個交易日。這些資料集在當天抓不到是正常的，
# 要靠 `python -m etl refresh` 事後補進既有快照。
LATE_DATASETS = ("foreign",)

TWSE_PARAMS = {
    "price": {"type": "ALLBUT0999", "response": "json"},
    "institutional": {"selectType": "ALL", "response": "json"},
    "margin": {"selectType": "STOCK", "response": "json"},
    "foreign": {"selectType": "ALLBUT0999", "response": "json"},
}

# 上櫃。以下路徑是依文件推測的，**已知至少有一個不正確**——TPEx 的端點名稱
# 無法從公開文件可靠推斷，猜錯時伺服器會回 HTML 錯誤頁而不是 404。
# 使用前請先跑 `python -m etl discover`，它會讀官方 OpenAPI 規格、列出真實路徑，
# 並直接指出這裡哪幾個對不上。
# 另外 TPEx 的 openapi 端點多半只提供當日資料，上櫃無法回補歷史。
# 注意：swagger.json 裡的路徑不含 /v1，實際網址要加上 /openapi/v1 前綴。
# price 已實測可用（回傳 10991 列，含 ETF 與權證，程式會濾成普通股）。
TPEX_ENDPOINTS = {
    "price": f"{TPEX_OPENAPI}/tpex_mainboard_daily_close_quotes",
    "institutional": f"{TPEX_OPENAPI}/tpex_3insti_daily_trading",
    "margin": f"{TPEX_OPENAPI}/tpex_mainboard_margin_balance",
    # 外資持股：關鍵字搜尋只找到董監事持股相關的端點，正確的還沒確認。
    # 待 discover --all 列出全部 225 個端點後挑選。
    "foreign": f"{TPEX_OPENAPI}/tpex_foreign_dealers_hold",
}

# --- 儲存路徑 -------------------------------------------------------------
DATA_DIR = "data"
DAILY_DIR = f"{DATA_DIR}/daily"          # 每日快照，append-only，一天一個檔
STOCK_INFO_PATH = f"{DATA_DIR}/stock_info.json"
SIGNALS_PATH = f"{DATA_DIR}/signals.json"
SCREEN_ALL_PATH = f"{DATA_DIR}/screen_all.json"
HISTORY_DIR = f"{DATA_DIR}/history"      # 前端用的個股歷史，由 daily 重建


@dataclass
class ScreenConfig:
    """選股門檻。全部集中在這裡，方便日後調參而不必動邏輯。"""

    # 1. 盤整：近 N 個交易日的高低區間相對均價的幅度上限
    consolidation_window: int = 60          # 約 3 個月
    consolidation_max_range_pct: float = 0.15
    # 季線斜率接近零才算真盤整（避免抓到緩跌股）
    consolidation_max_abs_slope_pct: float = 0.0008   # 每日均線變動 / 價格
    # 實際盤整持續天數的判定：淨漂移不得超過區間寬度的這個比例。
    # 趨勢股單向走完整個區間，比值接近 1；箱型來回震盪，比值明顯偏低。
    consolidation_max_drift_ratio: float = 0.5
    consolidation_run_min_days: int = 20    # 短於此不回報持續天數（統計量不穩）

    # 2. 季線扣抵翻揚
    ma_period: int = 60
    ma_slope_lookback: int = 5              # 判斷「目前仍下彎或走平」的回看天數
    ma_slope_max: float = 0.0               # 季線斜率須 <= 0（尚未翻揚）
    deduction_forward_days: int = 20        # 觀察未來 N 日的扣抵值
    # 扣抵值須落在近 M 日收盤的低檔（「扣底」）
    deduction_low_lookback: int = 120
    deduction_low_percentile: float = 0.5

    # 3a. 融資遞減
    margin_window: int = 60                 # 約 3 個月
    margin_min_decline_pct: float = 0.10    # 期間至少減少 10%
    margin_max_slope: float = 0.0           # 迴歸斜率須為負

    # 3b. 外資庫存增加
    foreign_window: int = 60
    foreign_min_increase_pct: float = 0.02
    foreign_min_slope: float = 0.0

    # 3c. 三大法人合計買超
    institutional_window: int = 5
    institutional_min_net_shares: int = 0

    # 4. MACD
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    macd_converge_days: int = 3             # 轉正前柱狀體須連續收斂的天數
    # 轉紅是單日事件。設 1 為「只認當天翻紅」，放寬到 3 可避免晚看一天就錯過，
    # 代價是名單會納入已經紅了兩三天的股票。
    macd_within_days: int = 3

    # 產出
    min_score_to_list: int = 4              # screen_all 只列出通過幾項以上的

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_SCREEN = ScreenConfig()
