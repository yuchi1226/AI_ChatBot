# -*- coding: utf-8 -*-
"""
LLMReasoning/agent_loop.py
-----------------------------
第二輪推理（Agent Loop）本體，對應 Architect/AgentLoop.md §3.1–3.4、§4、§5：
把第一輪工具呼叫的結果（Backend.FinalToolResult 列表）與第一輪的內部思考
草稿（reason_content，即規格書所說的 original_draft）融合，組出送給模型
做第二次 forward pass 的提示詞，並計算 §4 輸出規格所需的中繼資料
（confidence_score／cited_sources／reasoning_summary）。

真正「呼叫 LLM 做第二次 forward pass」這件事留在
LLMReasoning/reasoning.py 的 resume_with_tool_result()（跟 process() 呼叫
LLM.stream_answer() 用同一套「累積串流片段」寫法一致，不在這裡重複一份）。
本檔案只放純函式子步驟：不呼叫 LLM、不碰 Session，方便單獨測試，對應：

  §3.1 reassemble_context()                  上下文重組
  §3.2 format_tool_results() / detect_conflicts()   資料清理與特徵萃取
  §5   （壓縮摘要子程序，內嵌在 format_tool_results 內）
  §3.3 build_final_prompt()                    邏輯校準的提示詞工程
                                                （§3.4 NLG 措辭要求也寫在
                                                這裡的指令文字中，不另外
                                                做後處理）
  §4   compute_confidence_score() / cited_sources() / build_reasoning_summary()
       輸出規格所需的中繼資料
  §5   is_stale()                              時間敏感資訊檢查

跨工具結果的矛盾偵測（detect_conflicts）與時效性檢查（is_stale）都是規則式
的粗略啟發法，不是語意理解——精確的語意衝突判斷留給第二輪 LLM 本身在
§3.3 的指令中處理（「強制要求模型對照 original_draft 的意圖，驗證
tool_results 是否足以回答問題」）。這裡只負責把「看起來有疑慮」的線索
顯式標記出來，降低模型自己漏看的機率，不是要取代模型的語意判斷。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from Backend.models import FinalToolResult
from Harness.text_preprocessing import approx_token_count, truncate_keep_head
from LLMReasoning.config import (
    AGENT_LOOP_MAX_CONTEXT_TOKENS,
    AGENT_LOOP_SUMMARY_TARGET_TOKENS,
    CONFLICT_CONFIDENCE_PENALTY,
    LOW_CONFIDENCE_THRESHOLD,
    STALE_RESULT_SECONDS,
)

logger = logging.getLogger("llm_reasoning.agent_loop")

# 粗略數值萃取：整數／小數，含負號。用來做 detect_conflicts() 的保守啟發法。
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass
class SecondRoundResult:
    """
    §4 輸出規格：第二輪推理的最終輸出物件。

    - final_answer：最終要呈現給使用者的自然語言回覆。
    - confidence_score：模型回答內容與工具事實相符程度的信心指數（0.0～1.0）。
    - cited_sources：引用來源的簡短標記（此專案採 tool_call_id 當標記）。
    - reasoning_summary：供開發者檢視的第二輪推理濃縮摘要（用於 Log 除錯）。

    confidence_score 低於 LOW_CONFIDENCE_THRESHOLD（0.6）時，§4 建議前端
    顯示免責聲明——見下方 needs_disclaimer()。目前 Frontend/ 尚未消費這個
    欄位，由呼叫端（LLMReasoning.reasoning.resume_with_tool_result）透過
    新的 "metadata" 事件往上傳，供未來 UI／稽核日誌使用。
    """

    final_answer: str
    confidence_score: float
    cited_sources: List[str] = field(default_factory=list)
    reasoning_summary: str = ""


def needs_disclaimer(confidence_score: float) -> bool:
    """§4：confidence_score 低於門檻時，建議前端顯示免責聲明。"""
    return confidence_score < LOW_CONFIDENCE_THRESHOLD


def format_tool_results(
    tool_results: List[FinalToolResult],
    budget_tokens: float = AGENT_LOOP_MAX_CONTEXT_TOKENS,
) -> str:
    """
    §3.2＋§5：把 tool_results 轉成一段文字，供 §3.1「實際查詢結果」分區使用。

    每個工具結果各自的清理／截斷已經在 Backend/processor.py 做完（結構提取、
    頭尾截斷、格式轉換），這裡只負責標上 tool_call_id 與成功/失敗狀態、
    串接起來，不重複做一次截斷。

    §5「結果超過 Token 限制」：若串接後的總 token 數仍超過 budget_tokens
    （例如同時附了多個工具結果），啟動壓縮摘要子程序——用
    Harness/text_preprocessing.py 既有的頭部保留截斷，壓縮到
    AGENT_LOOP_SUMMARY_TARGET_TOKENS（300 tokens）內，再進入 §3.3。
    """
    if not tool_results:
        return ""

    parts = []
    for result in tool_results:
        status_tag = "成功" if result.is_success else "失敗"
        parts.append(f"[工具結果 tool_call_id={result.tool_call_id}，狀態：{status_tag}]\n{result.content}")
    combined = "\n\n".join(parts)

    if approx_token_count(combined) > budget_tokens:
        logger.warning(
            "工具結果總長度超過 %.0f tokens，啟動壓縮摘要子程序，壓縮至 %.0f tokens 內。",
            budget_tokens,
            AGENT_LOOP_SUMMARY_TARGET_TOKENS,
        )
        combined = truncate_keep_head(combined, AGENT_LOOP_SUMMARY_TARGET_TOKENS)

    return combined


def detect_conflicts(tool_results: List[FinalToolResult]) -> Optional[str]:
    """
    §3.2：「若多個工具返回矛盾數據，必須將矛盾標記顯式寫入提示詞中」的粗略
    啟發法——只比較「成功」結果中萃取出的數字集合：兩個成功結果的數字集合
    完全不重疊時，才視為潛在矛盾（刻意用「完全不重疊」這個保守門檻，避免把
    日期、頁碼等常見雜訊誤判為衝突；代價是可能漏掉「部分重疊但語意矛盾」的
    情況——這正是留給 §3.3 模型自己語意判斷的部分，這裡只做粗篩）。

    Returns:
        矛盾標記文字（每對疑似矛盾各一行）；沒有偵測到潛在矛盾則回傳 None。
    """
    successful = [r for r in tool_results if r.is_success]
    if len(successful) < 2:
        return None

    number_sets = []
    for result in successful:
        numbers = set(_NUMBER_RE.findall(result.content))
        if numbers:
            number_sets.append((result.tool_call_id, numbers))

    if len(number_sets) < 2:
        return None

    conflicting_pairs = []
    for i in range(len(number_sets)):
        for j in range(i + 1, len(number_sets)):
            id_a, numbers_a = number_sets[i]
            id_b, numbers_b = number_sets[j]
            if numbers_a.isdisjoint(numbers_b):
                conflicting_pairs.append((id_a, id_b))

    if not conflicting_pairs:
        return None

    logger.warning("偵測到潛在的工具結果矛盾：%s", conflicting_pairs)
    return "\n".join(
        f"- {id_a} 與 {id_b} 回報的數值指標完全不重疊，可能存在矛盾，請優先查證後再作答。"
        for id_a, id_b in conflicting_pairs
    )


def is_stale(tool_results: List[FinalToolResult], max_age_seconds: float = STALE_RESULT_SECONDS) -> bool:
    """
    §5「時間敏感資訊」：比對工具結果的完成時間（Backend.execute_tool() 寫入
    metadata["completed_at"] 的 UTC ISO 時間戳，見 Backend/pipeline.py）與
    目前系統時間，超過 max_age_seconds（預設 1 小時）視為過期。

    沒有 completed_at 的結果（理論上不會發生，Backend/pipeline.py 一律會
    寫入；這裡是防呆）不列入判斷。
    """
    now = datetime.now(timezone.utc)
    for result in tool_results:
        completed_at = result.metadata.get("completed_at")
        if not completed_at:
            continue
        try:
            completed_dt = datetime.fromisoformat(completed_at)
        except ValueError:
            continue
        if (now - completed_dt).total_seconds() > max_age_seconds:
            return True
    return False


def reassemble_context(user_query: str, original_draft: str, tool_results_text: str) -> str:
    """
    §3.1 上下文重組：建立「增強脈絡（Enhanced Context）」區塊，明確標示
    「用戶提問」、「初步假設」、「實際查詢結果」三個分區，確保模型能清楚
    區分推測與事實。
    """
    return (
        "[用戶提問]\n"
        f"{user_query or '（無）'}\n\n"
        "[初步假設／原始思考草稿]\n"
        f"{original_draft or '（本輪無內部推理草稿）'}\n\n"
        "[實際查詢結果]\n"
        f"{tool_results_text or '（工具未返回任何結果）'}"
    )


def build_final_prompt(enhanced_context: str, conflict_note: Optional[str], stale: bool) -> str:
    """
    §3.3＋§3.4：組出送給模型做第二次 forward pass 的完整指令文字。

    §3.4 的 NLG 措辭要求（禁止機械式開場白、數值轉易讀單位、來源引用）直接
    寫進指令本身，由模型產出時就一併滿足，不另外做字串後處理去比對黑名單
    ——比對規則容易誤傷合法內容，也違反 LLMReasoning.md 既有「判斷僅基於
    模型輸出，不額外規則兜底」的原則。
    """
    instructions = [
        "請綜合以上工具回饋與原始思維，進行第二輪校準並生成最終回覆。",
        "驗證工具查詢結果是否足以回答用戶提問；若明顯不足，誠實告知缺少哪些資訊，不可捏造數據。",
        "回覆需附帶來源引用，將內容錨定至對應的工具結果（tool_call_id）。",
        "禁止使用「根據工具回傳...」等機械式開場白，改用「經查詢相關數據顯示...」或「目前的情況是...」等自然說法。",
        "原始資料中的數值請轉換為易讀單位（例如將秒數轉為「幾分鐘」）。",
        "以簡潔、有邏輯連貫性的繁體中文作答，字數盡量控制在 500 字以內。",
    ]
    if conflict_note:
        instructions.insert(
            1,
            "以下標記了工具結果之間可能存在的矛盾，請於回覆中以「然而」「但根據實際數據」等"
            "轉折詞明確指出差異。",
        )
    if stale:
        instructions.append("部分工具結果的查詢時間已超過 1 小時，請於回覆中註明資訊可能已過期。")

    parts = [enhanced_context]
    if conflict_note:
        parts.append(f"[矛盾標記]\n{conflict_note}")
    parts.append("[指令]\n" + "\n".join(f"- {line}" for line in instructions))
    return "\n\n".join(parts)


def compute_confidence_score(tool_results: List[FinalToolResult], conflict_note: Optional[str]) -> float:
    """
    §4／§5：規則式信心指數計算（本機 Ollama 沒有官方信心分數 API，無法採用
    模型自報的機率值）。

    - 基準 1.0。
    - 有 tool_results 但沒有任何一個成功 -> 封頂在 0.4（落在 §4「低於 0.6
      建議顯示免責聲明」的門檻內）。
    - 偵測到跨工具矛盾（detect_conflicts 非 None）-> §5「原始草稿與結果嚴重
      衝突」強制觸發的降級量 CONFLICT_CONFIDENCE_PENALTY（-0.3）。
    """
    score = 1.0
    if tool_results and not any(r.is_success for r in tool_results):
        score = min(score, 0.4)
    if conflict_note:
        score -= CONFLICT_CONFIDENCE_PENALTY
    return max(0.0, min(1.0, score))


def cited_sources(tool_results: List[FinalToolResult]) -> List[str]:
    """§4：`cited_sources` —— 引用來源的簡短標記，取成功工具結果的 tool_call_id。"""
    return [r.tool_call_id for r in tool_results if r.is_success]


def build_reasoning_summary(tool_results: List[FinalToolResult], conflict_note: Optional[str], stale: bool) -> str:
    """§4：`reasoning_summary` —— 供開發者檢視的第二輪推理濃縮摘要（用於 Log 除錯）。"""
    success_count = sum(1 for r in tool_results if r.is_success)
    return (
        f"tool_results={len(tool_results)}項（成功 {success_count}）、"
        f"conflict={'有' if conflict_note else '無'}、stale={'是' if stale else '否'}"
    )


__all__ = [
    "SecondRoundResult",
    "build_final_prompt",
    "build_reasoning_summary",
    "cited_sources",
    "compute_confidence_score",
    "detect_conflicts",
    "format_tool_results",
    "is_stale",
    "needs_disclaimer",
    "reassemble_context",
]
