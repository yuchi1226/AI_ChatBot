# -*- coding: utf-8 -*-
"""
Guardrails/config.py
-----------------------
Guardrails/ 套件的規則資料與參數集中地，風格對齊 Backend/config.py、
Tool/catalog.py 的慣例：規則本身（關鍵字表、正則、逾時秒數）跟審查邏輯
（Guardrails/rules.py、Guardrails/llm_judge.py）分開，方便之後只改名單
不用動程式碼。

對應 Guardrails/precheck.py 步驟⑨「執行前置鉤子（權限/敏感詞審查）」；
審查分兩層：
  1. Guardrails/rules.py：規則式（關鍵字/正則）快速掃描，決定性、不依賴
     模型，涵蓋已知違規樣式，是唯一保證「一定跑得動」的底線。
  2. Guardrails/llm_judge.py：規則放行後才進行的 LLM 二次複核，抓規則
     比對不到的換句話說/委婉包裝手法；本機模型逾時或格式解析失敗時
     優雅降級為只採規則式結果（見該模組說明），不影響第 1 層的結論。
"""

from __future__ import annotations

import os
from typing import Dict, List

from LLM.config import OLLAMA_MODEL as _DEFAULT_JUDGE_MODEL

# --- 敏感詞審查：分類關鍵字表（中英文皆有，比對前先轉小寫、只做子字串比對）------
# 對應 Prompt/system_prompt_cache.py 的 safety_guardrails 文字所列類別，
# 幫模型層級的軟性防線加上一層可稽核的硬性複查。刻意保持精簡：純子字串
# 比對詞庫做到位沒有意義（見 Guardrails/rules.py 模組說明的已知限制），
# 這裡列的是明確、低誤判風險的樣式，換句話說/委婉包裝交給 llm_judge.py。
SENSITIVE_KEYWORDS: Dict[str, List[str]] = {
    "violence": ["炸彈製作", "如何殺死", "殺人方法", "bomb making instructions", "how to kill someone"],
    "illegal_activity": ["毒品製造", "如何製毒", "槍枝走私", "洗錢方法", "drug synthesis", "how to launder money"],
    "hate_speech": ["種族滅絕宣傳", "genocide propaganda"],
    "self_harm": ["自殺方法", "如何自殺", "suicide method"],
    "csae": ["兒童色情", "未成年性剝削", "child sexual abuse material", "csam"],
    "privacy_exfiltration": ["身分證字號查詢", "信用卡號產生器", "credit card number generator"],
    "prompt_injection": [
        "忽略先前的指令", "忽略你的系統提示詞", "忽略上述所有指令",
        "ignore previous instructions", "ignore your system prompt", "disregard all prior instructions",
    ],
}

# --- 權限審查：database_query 破壞性/寫入型關鍵字（ToolCalling.md §3：
# database_query 語意是「查閱內部知識庫」，唯讀查詢，非此範圍視為越權） -------
SQL_WRITE_KEYWORDS: List[str] = [
    "drop", "delete", "truncate", "alter", "update", "insert", "exec", "execute", "grant", "revoke", "merge",
]

# --- 權限審查：http_request SSRF 防護（禁止呼叫內網/本機位址） -----------------
ALLOWED_URL_SCHEMES: List[str] = ["http", "https"]
BLOCKED_HOST_PATTERNS: List[str] = [
    r"^localhost$",
    r"^127\.",
    r"^0\.0\.0\.0$",
    r"^10\.",
    r"^172\.(1[6-9]|2\d|3[0-1])\.",
    r"^192\.168\.",
    r"^169\.254\.",
    r"^::1$",
    r".*\.internal$",
]

# --- 權限審查：code_interpreter 高風險樣式（沙箱尚未落地，先做輕量防呆） -------
CODE_DANGEROUS_PATTERNS: List[str] = [
    r"os\.system", r"subprocess\.", r"rm\s+-rf", r"shutil\.rmtree", r"eval\(", r"exec\(", r"socket\.", r"__import__",
]

# --- LLM 二次複核 --------------------------------------------------------------
# 逾時刻意設得比 LLM/config.py 的 READ_TIMEOUT_SECONDS（300 秒，給主要對話
# 串流用）緊很多：這裡只是一次分類判斷，不是真正執行工具，不該讓使用者
# 為了一個背景安全複核多等太久；逾時就降級為只採規則式結果，見
# Guardrails/llm_judge.py。
LLM_JUDGE_TIMEOUT_SECONDS: float = 8.0
# 預設沿用主要對話流程同一個本機模型；可用環境變數單獨覆蓋（例如之後想換
# 一個更小、更快的模型專門做複核，不影響主要對話品質）。
LLM_JUDGE_MODEL: str = os.environ.get("GUARDRAILS_LLM_JUDGE_MODEL", _DEFAULT_JUDGE_MODEL)

__all__ = [
    "SENSITIVE_KEYWORDS",
    "SQL_WRITE_KEYWORDS",
    "ALLOWED_URL_SCHEMES",
    "BLOCKED_HOST_PATTERNS",
    "CODE_DANGEROUS_PATTERNS",
    "LLM_JUDGE_TIMEOUT_SECONDS",
    "LLM_JUDGE_MODEL",
]
