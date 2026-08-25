# -*- coding: utf-8 -*-
"""
LLM/config.py
--------------
集中管理 LLM/ 套件所需的常數設定，風格對齊 Harness/config.py：
魔術數字（逾時秒數）與環境相依的設定（Ollama 服務位址、模型名稱）集中在
這裡，不散落在呼叫端程式碼中。

這裡刻意用環境變數做覆蓋，而不是寫死常數：Ollama 的服務位址與模型 tag
是「跑在哪台機器、拉了哪個模型」這種部署環境相關的資訊，跟 Harness/、
Prompt/ 那些「規格本身就固定」的常數性質不同。
"""

from __future__ import annotations

import os

# --- Ollama 服務位址 ----------------------------------------------------------
# 本機執行 `ollama serve`（或 `ollama run <model>` 時背景自動啟動）預設監聽
# 這個位址。若要連到別的主機／port，設定環境變數 OLLAMA_HOST 覆蓋即可
# （OLLAMA_HOST 是 Ollama 官方就在用的環境變數名稱，沿用同一個名字）。
OLLAMA_HOST: str = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# --- 使用的模型 ----------------------------------------------------------------
# 對齊使用者本機 `ollama run qwen3...` 的模型系列。若實際拉的是特定尺寸的
# tag（例如 qwen3:8b、qwen3:30b-a3b），設定環境變數 LLM_OLLAMA_MODEL 覆蓋，
# 不用改程式碼；不設定時預設用 "qwen3"（交給 Ollama 解析成該模型的預設 tag）。
OLLAMA_MODEL: str = os.environ.get("LLM_OLLAMA_MODEL", "qwen3.5:0.8b")

# --- 逾時設定（秒）--------------------------------------------------------------
# 連線逾時：Ollama 若完全連不上（服務未啟動、位址錯誤），應該很快就要失敗，
# 不要讓使用者對著轉圈圈等半天。
CONNECT_TIMEOUT_SECONDS: float = 10.0
# 單次讀取逾時：串流期間只要模型還在持續吐出思考內容／回覆片段，就不會
# 觸發這個逾時；只有在真的完全卡住、沒有任何新資料時才會觸發。深度思考
# 模型偶爾會想比較久，這裡抓寬鬆一點。
READ_TIMEOUT_SECONDS: float = 300.0

# --- 深度思考 -------------------------------------------------------------------
# 對應 Harness 送來的 request_payload["thinking_mode"]；這裡僅作為該欄位
# 缺漏時的備援預設值，實際開關以每次請求的 payload 為準。
DEFAULT_THINK: bool = True

# --- API 逾時重試（Architect/LLMReasoning.md §5：「LLM API 逾時」->「重試
# 最多 2 次（指數退避），逾時後回傳友善降級回答」）------------------------------
# 只在「這次嘗試完全沒收到任何一個串流 chunk」就逾時時才重試整個請求，見
# LLM/ollama_client.py 的實作說明；已經開始吐出內容後才卡住不重試。
API_RETRY_MAX: int = 2
API_RETRY_BACKOFF_BASE_SECONDS: float = 1.0
