# -*- coding: utf-8 -*-
"""
Harness/
--------
核心調度模組（Agent Harness）。實作 Architect/Harness.md 步驟 1–6：
純文字前處理、Session 管理、請求載荷（Payload）組裝。

對外只需要使用這個套件層級匯出的介面，不必理會內部模組怎麼切分：

    import Harness

    session_id, payload = None, None
    for event, data in Harness.handle_turn(user_text, session_id=prev_id):
        if event == "step":
            ...  # Trace.StepEvent，步驟②③④的即時進度，轉發給前端思考區
        elif event == "result":
            session_id, payload = data
    ...（呼叫 LLM 取得回覆後）...
    Harness.append_assistant_message(session_id, reply_text)

Architect/ThoughtPanelStep.md §6.2：handle_turn() 已改為 generator，即時
發射步驟②③④的 StepEvent，最終以 ("result", (session_id, payload)) 收尾；
HarnessError（EMPTY_CONTENT／INVALID_SESSION）語意不變，仍在第一次迭代
（第一個 next()）時直接拋出。
"""

from Harness.errors import HarnessError, empty_content_error, invalid_session_error
from Harness.harness import append_assistant_message, handle_turn
from Harness.session import SESSION_STORE

__all__ = [
    "HarnessError",
    "SESSION_STORE",
    "append_assistant_message",
    "empty_content_error",
    "handle_turn",
    "invalid_session_error",
]
