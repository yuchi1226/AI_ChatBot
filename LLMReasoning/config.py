# -*- coding: utf-8 -*-
"""
LLMReasoning/config.py
------------------------
集中管理 LLMReasoning/ 套件所需的常數設定，風格對齊 Harness/config.py：
規格書（Architect/LLMReasoning.md）明確給了數字或預設值的參數集中在這裡，
不散落在呼叫端程式碼中。

這些是「規格本身就固定」的推理參數，跟 LLM/config.py 的 OLLAMA_HOST／
OLLAMA_MODEL 那種「部署環境相關」的設定性質不同，所以不用環境變數覆蓋。

目前串接的是本機 Ollama（qwen3 系列），不是規格書目標的 DeepSeek-V3 API，
Ollama 沒有 reasoning_effort／max_reasoning_tokens 這類參數可以直接對應，
所以 REASONING_EFFORT／MAX_FINAL_TOKENS 目前尚未真正傳給 LLM/ 套件，先保留
規格書要求的設定值；MAX_REASONING_TOKENS 則已經在 reasoning.py 用來做 §5／
§6 的推理草稿 token 使用率警告。等之後真的換成支援這些參數的 API 時，
LLM/config.py、LLM/llm.py 再接上即可，呼叫端介面不需要改。
"""

from __future__ import annotations

# --- §2 輸入資料：深度思考／最終回答的 token 上限 ------------------------------
MAX_REASONING_TOKENS: int = 4096
MAX_FINAL_TOKENS: int = 2048

# --- §3.2 呼叫參數：推理深度 ----------------------------------------------------
REASONING_EFFORT: str = "medium"

# --- §6 效能指標：推理草稿 token 使用率門檻（超過就記警告，不中斷流程） --------
REASONING_TOKEN_WARN_RATIO: float = 0.8

# --- Architect/AgentLoop.md §6 效能指標：第二輪推理 Token 總消耗上限 ------------
AGENT_LOOP_MAX_CONTEXT_TOKENS: float = 4096

# --- AgentLoop.md §5「結果超過 Token 限制」：壓縮摘要子程序的目標大小 -----------
AGENT_LOOP_SUMMARY_TARGET_TOKENS: float = 300

# --- AgentLoop.md §4：confidence_score 低於此門檻，建議前端顯示免責聲明 ---------
LOW_CONFIDENCE_THRESHOLD: float = 0.6

# --- AgentLoop.md §5「原始草稿與結果嚴重衝突」：強制觸發的信心指數降級量 --------
CONFLICT_CONFIDENCE_PENALTY: float = 0.3

# --- AgentLoop.md §5「時間敏感資訊」：工具結果超過此秒數視為過期（1 小時） ------
STALE_RESULT_SECONDS: float = 60 * 60

# --- AgentLoop.md §6 效能指標：端對端延遲（P95）警告門檻，供 log 監控使用 -------
AGENT_LOOP_E2E_LATENCY_WARN_SECONDS: float = 5.0
