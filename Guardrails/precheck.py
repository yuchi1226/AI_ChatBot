# -*- coding: utf-8 -*-
"""
Guardrails/precheck.py
--------------------------
對應 Architect/Architect.md 循序圖步驟⑨「執行前置鉤子（權限/敏感詞審查）」。

逐一審查本輪 tool_calls：先跑 Guardrails/rules.py 的規則式檢查（快、
決定性，涵蓋已知違規樣式）；規則放行的 tool_call 才進
Guardrails/llm_judge.py 的 LLM 二次複核（慢、best-effort，抓規則式
關鍵字比對不到的換句話說手法；逾時/失敗時降級為維持規則式的放行結論，
見該模組說明），已被規則攔截的不再多打一次模型。

AI Transparency：每個 tool_call 會依序發射多則 StepEvent（"running" 開頭、
最後以 "success"/"error" 收尾），忠實呈現「規則式掃描先跑、結果是什麼、
LLM 二次複核有沒有跑、跑了多久、結論是什麼」這個完整過程，而不是只給一句
「通過安全審查」的結論——呼應 Architect/ThoughtPanelStep.md 顯示原則
「後端控制揭露內容」：可以公開的過程資訊（跑了哪些層、耗時多久、粗分類）
放進 delta／meta 讓使用者看到；只有可能被拿來當繞過探針的細節（命中的
確切關鍵字字串，見 Guardrails/rules.py 的 RejectionReason.internal_detail）
不外顯，只寫進 log。

攔截粒度是「單一 tool_call」，不是整輪：被擋下的 tool_call 交由呼叫端
（LLMReasoning/reasoning.py）合成一筆拒絕的 FinalToolResult，其餘沒被
擋下的 tool_call 照常送進工具執行管道——跟既有 PermissionError 的處理
方式一致（見 reasoning.py 該段落說明），不需要另外的「整輪中止」分支；
若這一輪剛好全部被擋，第二輪推理會拿到全是拒絕訊息的 tool_results，
自然生成「無法為您執行」風格的最終回覆，等同循序圖「不調用任何工具，
直接回覆拒絕訊息」的效果，不需要為此再寫一條特殊分支。

使用者授權子流程（⚠️請求批准／✅確認）刻意不在本次範圍內，維持
Architect/ThoughtPanelStep.md §3 備註所述的 stub 狀態，見 TODO.md
「使用者授權子流程」條目（規格書本身標注暫不實做）。
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Tuple

from Guardrails.llm_judge import llm_review
from Guardrails.rules import RejectionReason, rule_review
from Trace.step_events import make_step_event

Event = Tuple[str, Any]


def _tool_name(call: Dict[str, Any]) -> str:
    return call.get("function", {}).get("name", "?")


def _arguments(call: Dict[str, Any]) -> Dict[str, Any]:
    function = call.get("function", {}) or {}
    arguments = function.get("arguments") or {}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except (TypeError, ValueError):
            arguments = {}
    return arguments


def _tool_call_id(call: Dict[str, Any], index: int) -> str:
    # 跟 LLMReasoning/reasoning.py 的 _build_tool_execution_request() 用同一套
    # 「模型給的 id 優先，缺漏時退回 call_{index}」規則，讓步驟⑨跟步驟⑩～⑬
    # 的 tool_call_id 對得上，前端才能用同一個 id 把同一個工具呼叫的完整
    # 審查過程（步驟⑨）跟執行過程（步驟⑩～⑬）串起來看。
    return call.get("id") or f"call_{index}"


def precheck(
    tool_calls: List[Dict[str, Any]],
    reason_content: str = "",
) -> Iterator[Event]:
    """
    步驟⑨：對本輪即將執行的 tool_calls 逐一做前置審查。

    Args:
        tool_calls: 本輪已通過 §5/§6 結構與白名單檢查、即將交付工具執行
            管道的 tool_calls 列表（見 LLMReasoning/reasoning.py process()）。
        reason_content: 模型這一輪的推理草稿（原始思考內容），供
            Guardrails/llm_judge.py 判斷工具呼叫背後的意圖；只影響 LLM
            二次複核，不影響規則式檢查。

    Yields:
        ("step", StepEvent) — 步驟⑨的即時進度事件，每個 tool_call 會依序
            發射多則（開始審查／規則式掃描結果／LLM 複核進行中／最終結論），
            見模組說明的 AI Transparency 段落（無工具呼叫時發射一則
            status="skipped"）。
        ("result", dict) — {"blocked": {index: RejectionReason, ...}}，
            key 是 tool_calls 的原始索引；呼叫端據此決定每個 tool_call
            要正常執行還是合成拒絕結果，不在 blocked 裡的視為放行。
    """
    blocked: Dict[int, RejectionReason] = {}

    if not tool_calls:
        yield "step", make_step_event(
            "guardrails_precheck", status="skipped", delta="本輪無工具呼叫，略過審查。"
        )
        yield "result", {"blocked": blocked}
        return

    for index, call in enumerate(tool_calls):
        name = _tool_name(call)
        arguments = _arguments(call)
        tool_call_id = _tool_call_id(call, index)
        base_meta = {"tool_call_id": tool_call_id, "tool_name": name}

        yield "step", make_step_event(
            "guardrails_precheck",
            status="running",
            delta=f"開始審查「{name}」…\n",
            meta=dict(base_meta),
        )

        rule_reason = rule_review(call)
        if rule_reason is not None:
            # 規則式已攔截：不再多打一次 LLM，直接收尾。
            blocked[index] = rule_reason
            yield "step", make_step_event(
                "guardrails_precheck",
                status="error",
                delta=(
                    f"規則式掃描（敏感詞／權限規則）：命中規則，分類「{rule_reason.category}」，"
                    "不予執行；本次不再進行 LLM 二次複核。\n"
                    f"結論：「{name}」遭安全審查攔截，不予執行。\n"
                ),
                meta={**base_meta, "verdict": "blocked", "category": rule_reason.category, "source": "rule"},
            )
            continue

        yield "step", make_step_event(
            "guardrails_precheck",
            status="running",
            delta="規則式掃描（敏感詞／權限規則）：未命中任何規則，通過。\nLLM 二次複核：審查中…\n",
            meta=dict(base_meta),
        )

        outcome = llm_review(name, arguments, reason_content)

        if not outcome.available:
            # LLM 複核本次不可用：優雅降級為維持規則式的放行結論（見
            # Guardrails/llm_judge.py 模組說明），但仍誠實告知使用者這一層
            # 沒有真的跑到，而不是靜靜略過。
            yield "step", make_step_event(
                "guardrails_precheck",
                status="success",
                delta=(
                    f"LLM 二次複核：本次無法使用（{outcome.degrade_reason}，"
                    f"耗時 {outcome.elapsed_seconds:.1f} 秒），維持規則式結論。\n"
                    f"結論：「{name}」通過安全審查，予以放行。\n"
                ),
                meta={**base_meta, "verdict": "allowed", "source": "rule_only_degraded"},
            )
            continue

        if outcome.rejection is not None:
            blocked[index] = outcome.rejection
            yield "step", make_step_event(
                "guardrails_precheck",
                status="error",
                delta=(
                    f"LLM 二次複核：判定違規（分類「{outcome.rejection.category}」，"
                    f"耗時 {outcome.elapsed_seconds:.1f} 秒）。\n"
                    f"結論：「{name}」遭安全審查攔截，不予執行。\n"
                ),
                meta={
                    **base_meta,
                    "verdict": "blocked",
                    "category": outcome.rejection.category,
                    "source": "llm_judge",
                },
            )
        else:
            yield "step", make_step_event(
                "guardrails_precheck",
                status="success",
                delta=(
                    f"LLM 二次複核：通過（模型判定放行，耗時 {outcome.elapsed_seconds:.1f} 秒）。\n"
                    f"結論：「{name}」通過安全審查，予以放行。\n"
                ),
                meta={**base_meta, "verdict": "allowed", "source": "llm_judge"},
            )

    yield "result", {"blocked": blocked}


__all__ = ["precheck"]
