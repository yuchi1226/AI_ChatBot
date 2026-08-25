# -*- coding: utf-8 -*-
"""
Tool/config.py
-----------------
集中管理 Tool/ 套件所需的常數設定，風格對齊 Harness/config.py、
LLMReasoning/config.py。

Architect/ToolCalling.md §6：「若模型輸出的工具名稱不在白名單，或參數型態
錯誤，Harness 應觸發重試機制（要求模型重新生成 tool_calls），最多 2 次」。
重試迴圈實際執行位置在 LLMReasoning/reasoning.py（該套件已經是「呼叫 LLM
→ 判斷 → 流轉分支」的協調者，LLM/ 本身無狀態、不做決策），但重試次數是
這份規格書定義的數字，因此常數放在這裡，由 LLMReasoning/ 匯入使用——沿用
專案既有的跨套件常數引用慣例（例如 Harness/payload.py 匯入 Prompt 的
CURRENT_DATE_PLACEHOLDER）。
"""

from __future__ import annotations

# --- §6 錯誤處理：白名單/型態錯誤時的重試上限 -----------------------------------
RETRY_MAX: int = 2
