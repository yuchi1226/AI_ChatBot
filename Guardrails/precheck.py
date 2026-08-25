# -*- coding: utf-8 -*-
"""
Guardrails/precheck.py
--------------------------
對應 Architect/Architect.md 循序圖步驟⑨「執行前置鉤子（權限/敏感詞審查）」，
以及可選子流程「⚠️ 請求批准／✅ 確認」（使用者授權）。

目前為最小可用 stub：真正的權限/敏感詞審查邏輯尚未實作（沿用
LLMReasoning/reasoning.py 既有 TODO 註記的狀態），precheck() 一律直接放行，
但仍會即時發射步驟⑨的 StepEvent（status="skipped"），讓思考區誠實呈現
「這一步存在、但目前尚未真正審查」，符合 Architect/ThoughtPanelStep.md
顯示原則 5「錯誤也需呈現，不能直接跳過步驟」。

真正的審查邏輯完成後，只需要在本函式內補上判斷：
  - 通過 -> status="success"，yield ("result", True)。
  - 攔截 -> status="error"，delta 帶攔截原因，yield ("result", False)，
    呼叫端（LLMReasoning.reasoning.process）應在收到 False 時中止本輪工具
    呼叫，直接回傳安全攔截提示（比照 Architect.md 循序圖「不調用任何工具，
    直接回覆拒絕訊息」的分支）。
  - 需要使用者授權 -> 額外 yield 一個 step_key="guardrails_user_authorization"
    （meta.parent_step=9）的事件，前端渲染為⑨區塊內的子狀態列（見
    ThoughtPanelStep.md §3 表格備註），等待使用者確認後再繼續，而不是佔用
    獨立的步驟編號。
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Tuple

from Trace.step_events import make_step_event

Event = Tuple[str, Any]


def precheck(tool_calls: List[Dict[str, Any]]) -> Iterator[Event]:
    """
    步驟⑨ stub：對本輪即將執行的 tool_calls 做前置審查。

    Args:
        tool_calls: 本輪已通過 §5/§6 結構與白名單檢查、即將交付工具執行管道
            的 tool_calls 列表（見 LLMReasoning/reasoning.py process()）。

    Yields:
        ("step", StepEvent) — 步驟⑨的即時進度事件。
        ("result", bool) — True 代表放行，False 代表攔截（尚未實作攔截邏輯，
            目前恆為 True）；呼叫端需迭代取得這個值再決定是否繼續。
    """
    tool_names = [call.get("function", {}).get("name", "?") for call in tool_calls]
    yield "step", make_step_event(
        "guardrails_precheck",
        status="skipped",
        delta=(
            f"安全守衛尚未啟用，本次未對 {', '.join(tool_names) or '（無工具）'} "
            "執行實際審查，直接放行。"
        ),
        meta={"tool_names": tool_names},
    )
    yield "result", True


__all__ = ["precheck"]
