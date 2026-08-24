# -*- coding: utf-8 -*-
"""
Backend/config.py
--------------------
集中管理 Backend/ 套件（Tool Pipeline）所需的常數設定，風格對齊
Harness/config.py、Tool/config.py：規格書明確給了數字的參數集中在這裡。

部署相關的路徑/目錄設定允許用環境變數覆蓋（比照 LLM/config.py 的慣例），
其餘「規格本身就固定」的數字直接寫死常數。
"""

from __future__ import annotations

import os
from typing import List

# --- §3.1 執行具體工具：逾時設定 -------------------------------------------------
HTTP_TIMEOUT_SECONDS: float = 30.0
LOCAL_TIMEOUT_SECONDS: float = 60.0
# §3.1 錯誤處理策略：「網路超時或連線錯誤，應立即中斷重試（最多重試 1 次）」。
HTTP_RETRY_MAX: int = 1

# --- §3.3 後執行處理：截斷與結構提取 --------------------------------------------
MAX_RESULT_LENGTH_DEFAULT: int = 8000  # 硬性限制：最終輸出字串長度上限（字元數）
JSON_ARRAY_HEAD_LIMIT: int = 5  # JSON 陣列只保留前 N 筆（如搜尋結果僅留前 5 個連結）
FILE_SUMMARY_HEAD_LINES: int = 100  # 檔案讀取超過限制時，改回傳摘要 + 前 100 行

# --- §5 效能與監控指標 -----------------------------------------------------------
# 壓縮後大小 / 原始大小 < 此門檻時記 Warning（代表原始資料可能有過多無用雜訊）。
COMPRESSION_RATIO_WARN_THRESHOLD: float = 0.05

# --- §3.1 本地執行：白名單目錄（檔案 I/O 僅能在這些目錄內進行） -------------------
# 可用環境變數 BACKEND_FILE_WHITELIST_DIRS 覆蓋，多個目錄以 os.pathsep 分隔。
_DEFAULT_WHITELIST_DIR = os.path.join(os.getcwd(), "workspace")
WHITELISTED_DIRS: List[str] = [
    path.strip()
    for path in os.environ.get("BACKEND_FILE_WHITELIST_DIRS", _DEFAULT_WHITELIST_DIR).split(os.pathsep)
    if path.strip()
]
