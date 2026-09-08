"""台股選股 ETL。

資料流：交易所 API → data/daily/ 每日快照（append-only）→ 衍生產出給前端。
指令進入點見 etl/__main__.py，或直接 `python -m etl --help`。
"""
__version__ = "0.1.0"
