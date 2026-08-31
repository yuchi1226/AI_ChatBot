# -*- coding: utf-8 -*-
"""
Guardrails/
-----------
安全守衛（Guardrails）。對應 Architect/Architect.md 循序圖步驟⑨「執行前置
鉤子（權限/敏感詞審查）」。

precheck() 對本輪 tool_calls 逐一審查：先跑 Guardrails/rules.py 的規則式
（關鍵字/正則）快速掃描，放行的才進 Guardrails/llm_judge.py 的 LLM 二次
複核；同時即時發射步驟⑨的 StepEvent，讓思考區序列保持完整。攔截粒度是
單一 tool_call，被擋下的由呼叫端（LLMReasoning/reasoning.py）合成拒絕
結果，其餘沒被擋下的照常執行，見 Guardrails/precheck.py 模組說明。

使用者授權子流程（⚠️請求批准／✅確認）維持 stub 狀態，留待後續實作。

對外只需要：

    import Guardrails

    for event, data in Guardrails.precheck(tool_calls, reason_content):
        ...
"""

from Guardrails.precheck import precheck
from Guardrails.rules import RejectionReason

__all__ = ["precheck", "RejectionReason"]
