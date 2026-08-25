# -*- coding: utf-8 -*-
"""
Trace/step_events.py
-----------------------
對應 Architect/ThoughtPanelStep.md §4「事件契約」：定義前端思考區用來逐步
顯示 Architect/Architect.md 循序圖步驟①～⑰的共用資料結構 `StepEvent`，以及
①～⑰ 的固定登錄表 `STEP_REGISTRY`（見該文件 §3 步驟登錄表）。

刻意獨立成一個不依賴 Harness/、Backend/、LLMReasoning/ 任一方的小套件：
Backend/pipeline.py 既有慣例是不反向依賴 Harness/（見該檔案 completed_at
時間戳的說明），若把 StepEvent 放進 Harness/ 或 LLMReasoning/ 任一方，
Backend/ 就無法安全匯入，因此另立門戶，供五個模組（Harness/、
LLMReasoning/、Backend/、Guardrails/、Frontend/）共用。

對外只需要：

    from Trace.step_events import make_step_event, StepEvent, MIRRORS_TO_CHAT

    yield "step", make_step_event("llm_thinking_r1", status="running", delta=chunk)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# --- StepEvent 資料結構（ThoughtPanelStep.md §4.1） -----------------------------


@dataclass
class StepEvent:
    """
    思考區要顯示的單一步驟事件。同一個 step_no 可以連續發射多次：第一次
    status="running" 開格子，中間多次 delta 累加，最後一次以終態
    （success/error/skipped）收尾——前端負責把同一 step_no 的 delta 疊加
    成完整內容，本結構本身只帶「這一次的增量」，不是整段內容快照。
    """

    step_no: int  # 1-17，對應循序圖①～⑰
    step_key: str  # 見 STEP_REGISTRY 鍵值，前端用來對映固定樣式，不比對中文字串
    title: str  # 中文步驟標題，直接來自 STEP_REGISTRY，前端原樣顯示
    status: str  # "running" | "success" | "error" | "skipped"
    delta: str = ""  # 本次新增的內容片段（逐字/逐 token 串流用）
    meta: Dict[str, Any] = field(default_factory=dict)
    branch: Optional[str] = None  # 僅 step_no 7、8 使用："final_direct" | "tool_call"
    timestamp: str = ""  # ISO 8601（UTC），發射當下時間


# --- 步驟登錄表（ThoughtPanelStep.md §3） ---------------------------------------
# ⑦⑧ 在「無需工具」與「需要工具」兩條分支意義不同，各自有獨立的 step_key，
# 但共用同一個 step_no（7／8）——前端依 step_no 疊代同一格，依 branch 判斷
# 路徑長度（見 ThoughtPanelStep.md §5）。

STEP_REGISTRY: Dict[str, Dict[str, Any]] = {
    "receive_input": {"step_no": 1, "title": "輸入提問＋上下文（文件）"},
    "build_request": {"step_no": 2, "title": "構建請求（攜帶 Session ID）"},
    "fetch_prompt_mode": {"step_no": 3, "title": "拉取當前模式（System Prompt）"},
    "prompt_ready": {"step_no": 4, "title": "返回結構化 Prompt"},
    "send_to_llm_r1": {"step_no": 5, "title": "發送完整 Prompt＋歷史對話＋提問"},
    "llm_thinking_r1": {"step_no": 6, "title": "深度思考（Thinking Mode）"},
    "llm_final_answer_direct": {"step_no": 7, "title": "直接返回最終回答"},
    "deliver_final_answer": {"step_no": 8, "title": "輸出最終回覆"},
    "llm_tool_calls": {"step_no": 7, "title": "返回工具調用指令"},
    "dispatch_tool_pipeline": {"step_no": 8, "title": "交付工具調用請求"},
    "guardrails_precheck": {"step_no": 9, "title": "執行前置鉤子（權限/敏感詞審查）"},
    "guardrails_user_authorization": {"step_no": 9, "title": "請求使用者授權"},
    "tool_execute": {"step_no": 10, "title": "執行具體工具"},
    "tool_raw_result": {"step_no": 11, "title": "返回原始結果"},
    "tool_post_process": {"step_no": 12, "title": "後執行處理"},
    "tool_result_ready": {"step_no": 13, "title": "返回工具結果"},
    "send_to_llm_r2": {"step_no": 14, "title": "工具結果＋原始思考草稿再次送入模型"},
    "llm_thinking_r2": {"step_no": 15, "title": "綜合分析工具返回的信息"},
    "llm_final_answer_r2": {"step_no": 16, "title": "生成最終自然語言回覆"},
    "deliver_final_answer_r2": {"step_no": 17, "title": "輸出最終答案"},
}

# ThoughtPanelStep.md §3：這兩個步驟的 delta 除了進思考區，也要同步追加到
# 左側對話框的 AI 回覆氣泡（取代舊版 "response_chunk" 事件的用途）。
MIRRORS_TO_CHAT = frozenset({"llm_final_answer_direct", "llm_final_answer_r2"})

# 步驟編號對應的圈碼數字，供前端渲染標題用（Trace/ 集中提供，避免各處各刻一份）。
CIRCLED_DIGITS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰"


def circled_step_no(step_no: int) -> str:
    """把 1-17 轉成對應的圈碼數字；超出範圍時退回 "(n)" 格式，避免前端渲染出錯。"""
    if 1 <= step_no <= len(CIRCLED_DIGITS):
        return CIRCLED_DIGITS[step_no - 1]
    return f"({step_no})"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def make_step_event(
    step_key: str,
    status: str,
    delta: str = "",
    meta: Optional[Dict[str, Any]] = None,
    branch: Optional[str] = None,
) -> StepEvent:
    """
    依 STEP_REGISTRY 查表組出 StepEvent，是所有模組發射步驟事件的唯一入口——
    禁止各模組自行手刻步驟標題字串，確保 ThoughtPanelStep.md 顯示原則 4
    「後端控制揭露內容」在多處實作中不會跑掉（標題永遠只有這一份來源）。

    Args:
        step_key: STEP_REGISTRY 的鍵值，決定 step_no／title。
        status: "running" | "success" | "error" | "skipped"。
        delta: 本次新增的內容片段。
        meta: 可公開的結構化資訊（如 tool_call_id、confidence_score）。
        branch: 僅 step_key 對應 step_no 7、8 時才需要傳入，"final_direct"
            或 "tool_call"，供前端判斷本輪路徑長度（短路徑 8 步／長路徑 17 步）。
    """
    info = STEP_REGISTRY[step_key]
    return StepEvent(
        step_no=info["step_no"],
        step_key=step_key,
        title=info["title"],
        status=status,
        delta=delta,
        meta=meta or {},
        branch=branch,
        timestamp=_now_iso(),
    )


__all__ = [
    "CIRCLED_DIGITS",
    "MIRRORS_TO_CHAT",
    "STEP_REGISTRY",
    "StepEvent",
    "circled_step_no",
    "make_step_event",
]
