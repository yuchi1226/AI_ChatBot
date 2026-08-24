# -*- coding: utf-8 -*-
"""
Harness/
--------
核心調度模組（Agent Harness）。實作 Architect/Harness.md 步驟 1–6：
純文字前處理、Session 管理、請求載荷（Payload）組裝。

對外只需要使用這個套件層級匯出的介面，不必理會內部模組怎麼切分：

    import Harness

    session_id, payload = Harness.handle_turn(user_text, session_id=prev_id)
    ...（呼叫 LLM 取得回覆後）...
    Harness.append_assistant_message(session_id, reply_text)
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
