# -*- coding: utf-8 -*-
"""
LLMReasoning/actions.py
--------------------------
對應 Architect/LLMReasoning.md §3.3「判斷是否無須呼叫工具」與 §5「工具呼叫
格式錯誤」檢查。

decide_action() 是規格書 3.3 節那段 Python 偽代碼的正式版本：僅依模型是否
回傳 tool_calls 判斷，不額外進行規則兜底（規格書關鍵約束：「該判斷僅基於
模型輸出，不額外進行規則兜底，除非安全模組攔截」——安全模組攔截屬於
Guardrails/ 套件的範圍，尚未實作，本函式不處理）。
"""

from __future__ import annotations

import enum
import json
from typing import Any, Dict, List

from LLMReasoning.errors import ToolCallFormatError


class Action(enum.Enum):
    """§3.3 判定結果：對應規格書偽代碼裡的 Action.FINAL_ANSWER / Action.TOOL_CALL。"""

    FINAL_ANSWER = "final_answer"
    TOOL_CALL = "tool_call"


def decide_action(tool_calls: List[Dict[str, Any]]) -> Action:
    """
    §3.3：`llm_response.tool_calls` 為 None 或空列表 -> FINAL_ANSWER；
    否則 -> TOOL_CALL。

    Args:
        tool_calls: 本輪 LLM 回應累積到的 tool_calls 列表（可能是空列表）。
    """
    if tool_calls:
        return Action.TOOL_CALL
    return Action.FINAL_ANSWER


def validate_tool_calls(tool_calls: List[Dict[str, Any]]) -> None:
    """
    §5：「工具呼叫格式錯誤（如缺少必填參數）」的格式檢查。

    只檢查「這是不是一個結構合法的工具呼叫指令」，不檢查參數語意是否正確
    （例如 query 是否真的有意義）——語意檢查屬於實際執行工具、或 Guardrails/
    套件的責任，此處只把「模型講的話能不能被解析」這件事把關掉。

    每個 tool_call 至少要有 `function.name`（非空字串）；若帶有
    `function.arguments`，必須是 dict，或是可以被解析成 JSON 的字串
    （Ollama／OpenAI 風格的 tool_calls，arguments 常以 JSON 字串傳遞）。

    Raises:
        ToolCallFormatError: 任一個 tool_call 格式不合法。
    """
    for call in tool_calls:
        function = call.get("function") if isinstance(call, dict) else None
        if not isinstance(function, dict) or not function.get("name"):
            raise ToolCallFormatError(f"工具呼叫缺少必填的 function.name：{call!r}")

        arguments = function.get("arguments")
        if arguments is None or isinstance(arguments, dict):
            continue
        if isinstance(arguments, str):
            try:
                json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise ToolCallFormatError(
                    f"工具呼叫「{function.get('name')}」的 arguments 不是合法 JSON：{arguments!r}"
                ) from exc
            continue
        raise ToolCallFormatError(
            f"工具呼叫「{function.get('name')}」的 arguments 型別不合法：{type(arguments)!r}"
        )


__all__ = ["Action", "decide_action", "validate_tool_calls"]
