# -*- coding: utf-8 -*-
"""
Guardrails/
-----------
安全守衛（Guardrails）。對應 Architect/Architect.md 循序圖步驟⑨「執行前置
鉤子（權限/敏感詞審查）」。

目前僅有 precheck() 一個最小可用 stub：一律放行，但會即時發射步驟⑨的
StepEvent（status="skipped"），讓 Architect/ThoughtPanelStep.md 定義的思考
區步驟序列保持完整。真正的權限/敏感詞審查邏輯、使用者授權子流程，留待
本套件後續實作，見 Guardrails/precheck.py 模組說明。

對外只需要：

    import Guardrails

    for event, data in Guardrails.precheck(tool_calls):
        ...
"""

from Guardrails.precheck import precheck

__all__ = ["precheck"]
