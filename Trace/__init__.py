# -*- coding: utf-8 -*-
"""
Trace/
------
思考區步驟事件的共用資料結構。實作 Architect/ThoughtPanelStep.md §4：
`StepEvent`／`STEP_REGISTRY`／`MIRRORS_TO_CHAT`／`make_step_event()`，供
`Harness/`、`LLMReasoning/`、`Backend/`、`Guardrails/`、`Frontend/` 共用。

刻意獨立成套件、不依賴 Harness/、Backend/、LLMReasoning/ 任一方，見
Trace/step_events.py 模組說明。
"""

from Trace.step_events import (
    CIRCLED_DIGITS,
    MIRRORS_TO_CHAT,
    STEP_REGISTRY,
    StepEvent,
    circled_step_no,
    make_step_event,
)

__all__ = [
    "CIRCLED_DIGITS",
    "MIRRORS_TO_CHAT",
    "STEP_REGISTRY",
    "StepEvent",
    "circled_step_no",
    "make_step_event",
]
