# -*- coding: utf-8 -*-
"""
LLMReasoning/errors.py
------------------------
對應 Architect/LLMReasoning.md 第 5 節「異常處理與容錯」中，屬於「不執行
工具、立即中斷本輪工具呼叫」的例外類型，風格對齊 Harness/errors.py、
LLM/errors.py。

§5 表格裡其餘情境（LLM API 逾時重試、推理草稿截斷警告、歷史過長截斷、
安全守衛攔截）都不會中斷流程或已由其他模組處理，不需要專屬例外類別：
  - LLM API 逾時重試 -> LLM/ollama_client.py 內部處理，重試用盡才拋出
    LLM.OllamaConnectionError（LLM/errors.py），由 LLM/llm.py 接住轉成
    降級回覆，reasoning.py 這一層看到的只會是正常的事件串流。
  - 推理草稿截斷 -> reasoning.py 記錄警告，不拋例外。
  - 歷史過長 -> Harness/ 已經在組裝 payload 前截斷完成。
  - 安全守衛攔截 -> 屬於 Guardrails/ 套件範圍，尚未實作。
"""

from __future__ import annotations


class LLMReasoningError(Exception):
    """LLMReasoning/ 套件所有例外的共同基底類別，方便呼叫端一次 except 住。"""


class ToolCallFormatError(LLMReasoningError):
    """
    工具呼叫格式錯誤（如缺少必填參數）。

    對應 §5：「不執行工具，立即回傳錯誤提示給使用者，要求重新提問」——
    由 reasoning.py 接住這個例外並產生錯誤提示，不會進入暫存推理狀態／
    呼叫工具管線的流程。
    """
