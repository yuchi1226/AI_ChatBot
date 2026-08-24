# -*- coding: utf-8 -*-
"""
Harness/config.py
------------------
集中管理 Harness 模組所需的常數設定。
對應 Architect/Harness.md 中散落於各節的數字規格，全部集中在這裡，
避免魔術數字散落在各個模組中。
"""

# --- 3.1 Session ID 管理機制 -------------------------------------------------
# Session 逾時（TTL）：預設 30 分鐘無活動即失效。
SESSION_TTL_SECONDS: int = 30 * 60

# 「壓縮後的歷史對話陣列」：保留最近 N 則訊息（user/assistant 各算一則），
# 超過就從最舊的開始丟棄，這是目前最簡單可行的「壓縮」策略。
MAX_HISTORY_MESSAGES: int = 40

# --- 2.1 純文字處理規範 -------------------------------------------------------
# Token 緩衝區預留量（例如 16,000 Token）。
MAX_INPUT_TOKENS: int = 16_000

# 截斷處插入的標記文字。
TRUNCATION_MARKER: str = "...[前文已截斷]..."

# --- 3.2 請求載荷封裝流程 -----------------------------------------------------
DEFAULT_MODE: str = "default"

# 時區：規格書範例使用 +08:00（對齊使用者所在時區 Asia/Taipei）。
TIMEZONE_OFFSET_HOURS: int = 8

# --- 5. 效能規格（SLA，供 log 監控使用，非強制中斷條件） -----------------------
SLA_PREPROCESS_MS: float = 5.0
SLA_REQUEST_BUILD_MS: float = 10.0

# --- Architect/PreparatoryPhase.md §6 效能與快取策略 --------------------------
# 系統提示詞總長度（角色定義 + 工具定義 + 安全紅線）上限，超出時自動截斷
# 工具描述或角色定義，確保不超過模型上下文視窗的 30%（規格書換算成的 token 數）。
MAX_SYSTEM_PROMPT_TOKENS: int = 8_000
