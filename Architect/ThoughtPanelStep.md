# 規格書：前端思考區 – 步驟化即時串流輸出規格（Thought Panel Step Output）

| 文件版本 | 1.0 |
| :--- | :--- |
| 撰寫日期 | 2026-08-25 |
| 目標框架 | Python Gradio (>= 4.0 / 5.0) |
| 核心目標 | 對應 `Architect/Architect.md` 循序圖步驟 **①～⑰**，定義前端「思考區」以**步驟化、逐步、即時串流**方式呈現後端事件的顯示規格，並規範 `Harness/`、`LLMReasoning/`、`Backend/`、`Guardrails/`、`Frontend/` 五個模組**真即時**發射步驟事件（`StepEvent`）的實作方式，取代目前思考區僅將 `thought_chunk` 串接成單一長文字的做法。 |

---

## 1. 概述

### 1.1 目標
目前 `Frontend/app.py` 的思考區只把 `LLM.stream_answer()` 吐出的 `thought_chunk` 累加成一整段純文字顯示，使用者看不到②～⑤、⑦～⑭、⑰這些步驟，`resume_with_tool_result()` 已經算好的 `confidence_score`／`cited_sources`／`reasoning_summary`（`metadata` 事件）目前也因為 Frontend 的 if/elif 沒有對應分支而被靜默丟棄。本規格書要解決的問題：把 `Architect.md` 循序圖①～⑰的**每一步**都轉成前端可獨立渲染、可即時串流、可標示錯誤狀態的區塊，且每一步的內容都由後端**真即時**發射（發生當下就送出事件），不是等整輪跑完再一次補發。

### 1.2 與既有規格書的關係
本文件是 `Architect/FrontendUIUX.md` §3 FR-02（思考過程逐步吐字）的**取代與擴充版**：FR-02 原本只要求「思考內容逐字顯示、有結構時用清單呈現」，本文件把這個要求具體化為「以 `Architect.md` 的①～⑰為固定骨架，每個步驟一個獨立區塊，區塊內文字仍然逐字/逐 token 串流」。FR-01／FR-03（對話互動、複製/讚/踩按鈕）不受影響。本文件同時對應：

- `Architect/Harness.md`（步驟②～⑥的前處理與請求建構）
- `Architect/PreparatoryPhase.md`（步驟③④的 System Prompt 拉取）
- `Architect/LLMReasoning.md`（步驟⑤⑥⑦的推理與工具判斷）
- `Architect/ToolCalling.md`（步驟⑦的工具呼叫決策）
- `Architect/ToolExecution.md`（步驟⑩～⑬的工具執行管道）
- `Architect/AgentLoop.md`（步驟⑭～⑰的第二輪推理）

### 1.3 適用範圍
適用於 `Frontend/app.py` 思考區（`#thought_panel`）的渲染邏輯，以及 `Harness/`、`LLMReasoning/`、`Backend/`、`Guardrails/`（新建）用來發射步驟事件的所有函式介面變更。不涉及左側對話框氣泡樣式、複製/讚踩按鈕（`Architect/FrontendUIUX.md` FR-03 已規範）。

---

## 2. 設計原則對照

| 使用者提出的顯示原則 | 本規格書的對應設計 |
| :--- | :--- |
| 1. 依序顯示，嚴格按①～⑰ | §3 步驟登錄表固定編號與標題；前端只依 `step_no` 遞增渲染，不自行排序 |
| 2. 即時更新，不等整體完成 | §4 事件契約的 `("step", StepEvent)` 逐步 yield；§6 規範①～⑰**全數**真即時發射，不批次補發 |
| 3. 內容透明 | §3 每步都定義「建議顯示內容」；§8 明訂**不做遮蔽** |
| 4. 後端控制揭露內容 | `StepEvent.title` 與內容一律由後端組好，前端只負責渲染，不解析中文字串、不判斷這段文字屬於哪一步 |
| 5. 錯誤也需呈現 | §9 例外對照表，每個例外都掛在明確的 `step_no` 上，`status="error"`，不跳過該步驟 |
| 6. 支援 Streaming | §6：`Harness.handle_turn()`、`Backend.execute_tool()` 均改為 generator，①～⑰無一例外皆為即時事件，非事後回放 |

---

## 3. 步驟登錄表（Step Registry）

Architect.md 的循序圖是**兩條路徑共用⑦⑧編號**：⑦⑧在「無需工具」與「需要工具」分支意義不同；⑨～⑯只有長路徑才出現。前端**只渲染這一輪實際發生的步驟**，短路徑停在⑧，不預先畫出 17 個空格子。

`mirrors_to_chat = true` 代表這個步驟的 `delta` 除了進思考區，也要同步追加到左側對話框的 AI 回覆氣泡（取代現在的 `response_chunk` 用途）。

| # | step_key | 步驟名稱 | 負責模組／函式 | mirrors_to_chat | 建議顯示內容 |
| :-: | :--- | :--- | :--- | :-: | :--- |
| ① | `receive_input` | 輸入提問＋上下文（文件） | `Frontend/app.py: user_submit()` | 否 | 使用者提問原文；若有上傳檔案，附檔名清單 |
| ② | `build_request` | 構建請求（攜帶 Session ID） | `Harness/harness.py: handle_turn()` 起始 | 否 | `session_id`（新建/沿用）、清理後文字長度、是否觸發截斷 |
| ③ | `fetch_prompt_mode` | 拉取當前模式（System Prompt） | `Prompt/system_prompt_cache.py: get_system_prompt()` 呼叫前 | 否 | `mode` 名稱、快取查詢中 |
| ④ | `prompt_ready` | 返回結構化 Prompt | 同上，回傳值 | 否 | 完整 System Prompt 文字、`template_id`/`version`，若觸發 fallback 需註明 |
| ⑤ | `send_to_llm_r1` | 發送完整 Prompt＋歷史對話＋提問 | `LLMReasoning/reasoning.py: process()` 呼叫 `LLM.stream_answer()` 前 | 否 | 歷史訊息則數、`thinking_mode`、`tools` 清單 |
| ⑥ | `llm_thinking_r1` | 深度思考（Thinking Mode），生成 `reason_content` | 同上，第一輪 `thought_chunk` | 否 | 逐 token 串流的推理草稿全文 |
| ⑦A | `llm_final_answer_direct` | 直接返回 final answer（無需工具） | `actions.decide_action()` → `FINAL_ANSWER` | **是** | 逐 token 串流的最終回覆內容 |
| ⑧A | `deliver_final_answer` | 輸出最終回覆（結束，短路徑到此為止） | `Harness.append_assistant_message` + 迴圈結束 | 否 | 完成確認、耗時統計 |
| ⑦B | `llm_tool_calls` | 返回 tool_calls 指令（需要工具） | `actions.decide_action()` → `TOOL_CALL` | 否 | 工具名稱＋完整參數（JSON，見 §8 不遮蔽） |
| ⑧B | `dispatch_tool_pipeline` | 交付工具調用請求 | `reasoning.py` 組 `Backend.ToolExecutionRequest` | 否 | 本輪要執行的工具清單 |
| ⑨ | `guardrails_precheck` | 執行前置鉤子（權限/敏感詞審查） | `Guardrails/`（新建 stub） | 否 | 審查結果；目前為 stub，見 §6.5 |
| ⑩ | `tool_execute` | 執行具體工具（HTTP/本地） | `Backend/pipeline.py: execute_tool()` 內 | 否 | 執行模式（http/local）、逾時設定 |
| ⑪ | `tool_raw_result` | 返回原始結果 | 同上，`RawToolResponse` | 否 | 原始資料（依 content_type 顯示 JSON/純文字摘要）、`execution_time_ms` |
| ⑫ | `tool_post_process` | 後執行處理（截斷/格式化） | `Backend/processor.py: process_response()` | 否 | 截斷比例、`truncation_ratio` |
| ⑬ | `tool_result_ready` | 返回工具結果 | `pipeline.execute_tool()` 回傳前 | 否 | 處理後的 `content` 全文、`is_success` |
| ⑭ | `send_to_llm_r2` | 工具結果＋原始草稿再次送入模型 | `resume_with_tool_result()` 組 `second_round_payload` 前 | 否 | 增強脈絡三分區摘要（用戶提問/初步假設/實際查詢結果）、`conflict_note`、`stale` |
| ⑮ | `llm_thinking_r2` | 綜合分析工具返回的信息 | 同上，第二輪 `thought_chunk` | 否 | 逐 token 串流的第二輪推理內容 |
| ⑯ | `llm_final_answer_r2` | 生成最終自然語言回覆 | 同上，第二輪 `response_chunk` | **是** | 逐 token 串流的最終回覆內容 |
| ⑰ | `deliver_final_answer_r2` | 輸出最終答案（結束） | `yield("end")` 前 | 否 | `confidence_score`／`cited_sources`／`reasoning_summary`（原 `metadata` 事件內容併入本步） |

> ⑨後方「⚠️請求批准／✅確認」屬於可選子流程，只有真的觸發使用者授權時才出現。設計上不佔用固定編號，實作時以 `step_key="guardrails_user_authorization"`、`meta.parent_step=9` 標記為⑨的附屬事件，前端渲染為⑨區塊內的子狀態列，而非獨立編號格子。目前 `Guardrails/` 尚未實作此子流程，見 §6.5。

---

## 4. 事件契約（Event Schema）

### 4.1 StepEvent 資料結構

新建共用模組 `Trace/step_events.py`（不依賴 `Harness/`、`Backend/`、`LLMReasoning/` 任何一方，避免循環依賴——`Backend/pipeline.py` 現有註解已明確表示不願反向依賴 `Harness/`，故此模組必須獨立）：

```python
# Trace/step_events.py
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

@dataclass
class StepEvent:
    step_no: int              # 1-17，對應①~⑰
    step_key: str              # 見 §3 表格第二欄，前端用來對映固定樣式/圖示，不比對中文字串
    title: str                  # 中文步驟標題，直接來自 STEP_REGISTRY，前端原樣顯示
    status: str                 # "running" | "success" | "error" | "skipped"
    delta: str = ""             # 本次新增的內容片段（逐字/逐 token 串流用，前端直接 append）
    meta: Dict[str, Any] = field(default_factory=dict)
    branch: Optional[str] = None   # 僅 step_no 7、8 使用："final_direct" | "tool_call"
    timestamp: str = ""          # ISO 8601，發射當下時間（UTC+8，沿用 Harness 慣例）

STEP_REGISTRY: Dict[str, Dict[str, Any]] = {
    "receive_input":              {"step_no": 1,  "title": "輸入提問＋上下文（文件）"},
    "build_request":               {"step_no": 2,  "title": "構建請求（攜帶 Session ID）"},
    "fetch_prompt_mode":           {"step_no": 3,  "title": "拉取當前模式（System Prompt）"},
    "prompt_ready":                 {"step_no": 4,  "title": "返回結構化 Prompt"},
    "send_to_llm_r1":               {"step_no": 5,  "title": "發送完整 Prompt＋歷史對話＋提問"},
    "llm_thinking_r1":              {"step_no": 6,  "title": "深度思考（Thinking Mode）"},
    "llm_final_answer_direct":      {"step_no": 7,  "title": "直接返回最終回答"},
    "deliver_final_answer":         {"step_no": 8,  "title": "輸出最終回覆"},
    "llm_tool_calls":               {"step_no": 7,  "title": "返回工具調用指令"},
    "dispatch_tool_pipeline":       {"step_no": 8,  "title": "交付工具調用請求"},
    "guardrails_precheck":          {"step_no": 9,  "title": "執行前置鉤子（權限/敏感詞審查）"},
    "tool_execute":                  {"step_no": 10, "title": "執行具體工具"},
    "tool_raw_result":               {"step_no": 11, "title": "返回原始結果"},
    "tool_post_process":             {"step_no": 12, "title": "後執行處理"},
    "tool_result_ready":             {"step_no": 13, "title": "返回工具結果"},
    "send_to_llm_r2":                {"step_no": 14, "title": "工具結果＋原始思考草稿再次送入模型"},
    "llm_thinking_r2":               {"step_no": 15, "title": "綜合分析工具返回的信息"},
    "llm_final_answer_r2":           {"step_no": 16, "title": "生成最終自然語言回覆"},
    "deliver_final_answer_r2":       {"step_no": 17, "title": "輸出最終答案"},
}

MIRRORS_TO_CHAT = {"llm_final_answer_direct", "llm_final_answer_r2"}
```

所有發射事件的模組一律 `from Trace.step_events import StepEvent, STEP_REGISTRY, MIRRORS_TO_CHAT`，禁止各模組自行手刻步驟標題字串，避免顯示原則 4「後端控制揭露內容」在多處實作中跑掉。

### 4.2 事件型別（沿用 `LLMReasoning/reasoning.py` 既有的 `Event = Tuple[str, Optional[Any]]` pattern）

| event | data | 說明 |
| :--- | :--- | :--- |
| `"step"` | `StepEvent` | 思考區要顯示的每一次步驟更新，可對同一 `step_no` 連續發射多次（先 `running` 開格子，中間多次 `delta` 累加，最後 `success`/`error`/`skipped` 收尾） |
| `"result"` | 依函式而定 | **僅供內部子 generator 使用**：`Harness.handle_turn()`、`Backend.execute_tool()` 改成 generator 後，用這個事件把原本的回傳值帶出來，呼叫端收到後即知道該子 generator已結束（見 §6） |
| `"end"` | `None` | 整輪對話結束（沿用現有語意），觸發輸入框/送出鈕重新啟用 |

原本的 `"thought_chunk"`／`"response_chunk"`／`"metadata"` 事件**全數移除**：`thought_chunk`／`response_chunk` 併入對應步驟的 `StepEvent.delta`；`metadata`（`SecondRoundResult`）併入步驟⑰的 `StepEvent.meta`。

### 4.3 status 狀態機

`pending`（尚未開始，前端不主動顯示，僅供內部使用）→ `running`（已開始，內容持續以 `delta` 累加）→ 終態 `success` / `error` / `skipped`。同一 `step_no` 收到終態事件後不應再收到該 `step_no` 的事件；若後端邏輯上需要「重試」（如 `ToolCalling.md` §6 的重試機制），視為同一 `step_no` 的內容延伸，不開新格子，`meta.retry_count` 遞增即可。

---

## 5. 分支呈現規則

前端依 `StepEvent.branch` 決定路徑長度：

- 收到 `step_no=7` 且 `branch="final_direct"` → 該輪只會再收到 `step_no=8` 一次，之後即 `"end"`，思考區固定 8 格，末端加註「【思考流程完成】」。
- 收到 `step_no=7` 且 `branch="tool_call"` → 後續會持續收到 8～17 的事件，思考區最終 17 格（若同輪呼叫多個工具，⑨～⑬會依工具數量重複出現，`meta.tool_call_id` 用來區分是哪一個工具，前端渲染時以子區塊列出，仍計為一組⑨～⑬）。
- ⑨若因 `Guardrails/` 目前僅為 stub 而直接放行，仍顯示該格，`status="skipped"`，見 §6.5，符合顯示原則 5。

---

## 6. 各模組真即時發射規格

### 6.1 `Frontend/app.py`

- `user_submit()`：組完使用者訊息後立即產生 `step_no=1` 的 `StepEvent`（`status="success"`，`delta` 為提問原文），連同既有的 `history` 更新一起 yield。
- `bot_response()`：把原本判斷 `event in ("thought_chunk","response_chunk","end")` 的 if/elif 改成：
  - `event == "step"`：把 `StepEvent` append／更新進 `gr.State` 存放的 `list[StepEvent]`，呼叫 `render_thought_html(steps)` 重新渲染；若 `data.step_key in MIRRORS_TO_CHAT`，額外把 `data.delta` 累加進 `response_acc` 並更新左側聊天氣泡（取代原本 `response_chunk` 分支）。
  - `event == "end"`：沿用現行邏輯重新啟用輸入框/送出鈕，並在思考區末端加註「【思考流程完成】」。

### 6.2 `Harness/harness.py`

`handle_turn()` 由「同步回傳 `(session_id, payload)`」改為 **generator**：

```python
def handle_turn(raw_text, session_id=None, ...) -> Iterator[Tuple[str, Any]]:
    # 步驟②：構建請求
    yield "step", StepEvent(**STEP_REGISTRY["build_request"], step_key="build_request",
                             status="running", delta=f"session_id={session_id or '（新建）'}")
    resolved_id, session, _is_new = SESSION_STORE.resolve(header_session_id, session_id)
    cleaned_text = clean_plain_text(raw_text)
    if not cleaned_text.strip():
        raise empty_content_error()
    yield "step", StepEvent(..., status="success", delta=f"已解析 session_id={resolved_id}")

    # 步驟③：拉取當前模式
    yield "step", StepEvent(**STEP_REGISTRY["fetch_prompt_mode"], status="running", delta=f"mode={mode}")
    try:
        prompt_block = get_system_prompt(mode)
        # 步驟④：返回結構化 Prompt
        yield "step", StepEvent(**STEP_REGISTRY["prompt_ready"], status="success",
                                 delta=render_prompt_text(prompt_block))
    except PromptFetchFailed as exc:
        prompt_block = copy.deepcopy(FALLBACK_PROMPT_BLOCK)
        yield "step", StepEvent(**STEP_REGISTRY["prompt_ready"], status="error",
                                 delta=f"System Prompt 拉取失敗，已切換備援提示詞：{exc}")

    payload = assemble_request(...)
    session.append_user_message(cleaned_text)
    yield "result", (resolved_id, payload)
```

呼叫端（`Frontend/app.py`）改為：

```python
resolved = None
for event, data in Harness.handle_turn(user_message, session_id=session_id):
    if event == "step":
        ... 更新思考區 ...
    elif event == "result":
        session_id, request_payload = data
```

### 6.3 `LLMReasoning/reasoning.py`

- `process()` 在呼叫 `LLM.stream_answer()` 前先 yield 步驟⑤（`send_to_llm_r1`）。
- 原本轉發 `thought_chunk` 的地方改為包成 `StepEvent(step_key="llm_thinking_r1", status="running", delta=data)`（步驟⑥）。
- `decide_action()` 判定後：
  - `FINAL_ANSWER`：把原本轉發 `response_chunk` 的地方改為 `StepEvent(step_key="llm_final_answer_direct", branch="final_direct", delta=data)`（步驟⑦A），結束時補一個步驟⑧A（`deliver_final_answer`，`status="success"`）再 `yield "end", None`。
  - `TOOL_CALL`：驗證通過後，先 yield 步驟⑦B（`llm_tool_calls`，內容為完整 `tool_calls` JSON，見 §8 不遮蔽）與步驟⑧B（`dispatch_tool_pipeline`），再進入 §6.4 的工具執行迴圈。
- 呼叫 `Backend.execute_tool(request)` 改為迭代其 generator（見 §6.4），把其中 `"step"` 事件原樣 `yield from` 往上轉發，`"result"` 事件取出 `FinalToolResult` 加進 `tool_results`。

### 6.4 `Backend/pipeline.py`（真即時串流的核心改動）

這是唯一原本「整個函式同步執行完才回傳」的模組，改成 generator，在每個子步驟**發生的當下**立即 yield，而不是執行完畢後一次補發：

```python
def execute_tool(request: ToolExecutionRequest) -> Iterator[Tuple[str, Any]]:
    adapter = ADAPTER_REGISTRY.get(request.tool_name)
    max_result_length = request.max_result_length or MAX_RESULT_LENGTH_DEFAULT

    if adapter is None:
        yield "step", StepEvent(**STEP_REGISTRY["tool_execute"], status="error",
                                 delta=f"找不到工具「{request.tool_name}」對應的 adapter")
        final = process_response(_unknown_tool_raw(request), max_result_length)
        final.metadata["completed_at"] = _completed_at_iso()
        yield "result", final
        return

    # 步驟⑩：執行具體工具 —— 呼叫 adapter 前先送出「開始執行」
    yield "step", StepEvent(**STEP_REGISTRY["tool_execute"], status="running",
                             delta=f"執行「{request.tool_name}」（{request.execution_mode}）…")
    t0 = time.perf_counter()
    raw = adapter(request)  # 實際 HTTP/本地呼叫，仍是阻塞的，但事件已在呼叫前送出
    elapsed_ms = (time.perf_counter() - t0) * 1000
    raw.metadata.setdefault("execution_time_ms", round(elapsed_ms, 1))
    yield "step", StepEvent(**STEP_REGISTRY["tool_execute"], status="success",
                             delta=f"耗時 {elapsed_ms:.0f}ms")

    # 步驟⑪：返回原始結果 —— adapter 一回傳就立即送出，不等後續處理
    yield "step", StepEvent(**STEP_REGISTRY["tool_raw_result"], status="success",
                             delta=_preview_raw(raw))

    # 步驟⑫：後執行處理
    yield "step", StepEvent(**STEP_REGISTRY["tool_post_process"], status="running",
                             delta="結構提取／截斷／格式化中…")
    final = process_response(raw, max_result_length)
    final.metadata["completed_at"] = _completed_at_iso()
    yield "step", StepEvent(**STEP_REGISTRY["tool_post_process"], status="success",
                             delta=f"截斷比例：{final.metadata.get('truncation_ratio', '無')}")

    # 步驟⑬：返回工具結果
    yield "step", StepEvent(**STEP_REGISTRY["tool_result_ready"],
                             status="success" if final.is_success else "error",
                             delta=final.content)

    logger.info("tool_execution_duration tool=%s ...", request.tool_name, ...)  # 原有 log 不變
    yield "result", final
```

呼叫端（`LLMReasoning/reasoning.py`）：

```python
for tool_call_index, call in enumerate(tool_calls):
    request = _build_tool_execution_request(call, tool_call_index)
    for event, data in Backend.execute_tool(request):
        if event == "step":
            yield "step", data
        elif event == "result":
            tool_results.append(data)
```

`PermissionError` 的既有處理邏輯（`Backend.execute_tool` 拋出、呼叫端 catch 後包成失敗的 `FinalToolResult`）不變，只是 catch 之後同樣要補發對應 `step_no=10~13`、`status="error"` 的事件，確保錯誤也走完整的四格顯示，不是直接跳過（顯示原則 5）。

### 6.5 `Guardrails/`（新建 stub，對應步驟⑨）

```python
# Guardrails/precheck.py
def precheck(tool_calls) -> Iterator[Tuple[str, Any]]:
    """
    步驟⑨ stub：目前僅記錄「尚未實作、直接放行」，不做任何實際審查。
    真正的權限/敏感詞審查邏輯完成後，於此函式內補上判斷，並依結果送出
    status="success"（通過）或 status="error"（攔截，連同攔截原因）；
    若判定需要使用者授權，改送 step_key="guardrails_user_authorization"
    （meta.parent_step=9）等待前端呼叫對應的授權 API 後再繼續。
    """
    yield "step", StepEvent(**STEP_REGISTRY["guardrails_precheck"], status="skipped",
                             delta="安全守衛尚未啟用，本次未執行審查，直接放行。")
    yield "result", True  # True = 放行；False = 攔截（尚未實作攔截邏輯）
```

`LLMReasoning/reasoning.py` 在步驟⑧B之後、進入 §6.4 工具執行迴圈之前，插入對 `Guardrails.precheck()` 的呼叫並轉發其 `"step"` 事件，取代目前程式碼中「TODO: Guardrails 尚未實作，直接跳過」的註記。

### 6.6 `LLMReasoning/agent_loop.py` + `resume_with_tool_result()`

- 組 `second_round_payload` 前，yield 步驟⑭（`send_to_llm_r2`），`delta` 用 `reassemble_context()` 的三分區摘要（用戶提問／初步假設／實際查詢結果），若 `conflict_note`／`stale` 非空，一併附進 `meta`。
- 原本轉發第二輪 `thought_chunk` 的地方改為 `StepEvent(step_key="llm_thinking_r2", ...)`（步驟⑮）。
- 原本轉發第二輪 `response_chunk` 的地方改為 `StepEvent(step_key="llm_final_answer_r2", branch=None, delta=data)`（步驟⑯，`mirrors_to_chat=True`）。
- 收尾時，原本 `yield ("metadata", result)` 改為併入步驟⑰：

```python
yield "step", StepEvent(**STEP_REGISTRY["deliver_final_answer_r2"], status="success",
                         meta={"confidence_score": result.confidence_score,
                               "cited_sources": result.cited_sources,
                               "reasoning_summary": result.reasoning_summary})
yield "end", None
```

`confidence_score < LOW_CONFIDENCE_THRESHOLD`（0.6）時，前端在步驟⑰區塊內額外顯示免責聲明樣式（`AgentLoop.md` §4 既有建議，目前完全沒有 UI 呈現，此規格書一併補上出口）。

---

## 7. 前端渲染規格

`gr.State` 的思考區狀態由「一個字串」改為 `list[StepEvent]`（實務上可用 dict 存放，key 為 `step_no`，方便同一步驟疊代更新，再依 `step_no` 排序渲染）。

`render_thought_html(steps)` 渲染規則：

- 依 `step_no` 由小到大輸出，每格格式對齊使用者提供的範例：`①{title}` → `│` → 內容（`delta` 累加後的全文，逐字效果由 Gradio `gr.HTML` 既有的更新頻率自然呈現，不需額外打字機動畫）→ `▼`。
- `status="running"`：內容區尾端加一個游標樣式（如 `▍`），視覺上表示仍在串流。
- `status="error"`：整格改紅色系邊框，標題前加 `⚠️`。
- `status="skipped"`：整格灰階，標題前加 `⏭️`。
- 收到 `"end"` 事件時，在最後一格之後加一行置中文字「【思考流程完成】」。
- 新問題送出時（沿用既有 `user_submit()` 清空邏輯），`list[StepEvent]` 清空重置。
- 捲動沿用既有 `gr.HTML(min_height="100%", max_height="100%", autoscroll=True)` 機制，不需改動。

---

## 8. 資料揭露政策

依需求方決定：**①～⑰的所有步驟內容一律原樣呈現，不做任何遮蔽或脫敏處理**，包含步驟⑦B/⑧B的工具呼叫參數（可能含檔案路徑）、步驟⑪/⑬的工具原始結果與處理後內容、步驟④的完整 System Prompt。既有的長度截斷機制（`Backend/processor.py` 的頭尾截斷、`Harness/text_preprocessing.py` 的智慧截斷）屬於「內容長度控制」，不是遮蔽，內容仍會透過既有的 `...[已省略 X 字元]...`／`...[前文已截斷]...` 標記如實反映截斷發生過。此政策為需求方明確決定，若日後系統提示詞或工具參數涉及機密資訊（如 API Key），需另行在對應模組（`Prompt/system_prompt_cache.py`、`Tool/catalog.py`）的資料來源層面避免把機密寫入會被顯示的欄位，而不是在思考區顯示層做遮蔽。

---

## 9. 例外處理與錯誤呈現對照

| 例外 | 掛在 step_no | status | 顯示文案來源 |
| :--- | :-: | :--- | :--- |
| `HarnessError(EMPTY_CONTENT)` | 2 | error | 現有 `exc.user_message`（"請輸入有效內容"） |
| `HarnessError(INVALID_SESSION)` | 2 | error | 現有 `exc.user_message`，並重置 `session_id` |
| `PromptFetchFailed` → fallback | 4 | error（已降級，非中斷） | 「System Prompt 拉取失敗，已切換備援提示詞」 |
| `HistoryCorrupted` | 2 | error（已降級） | 「歷史紀錄已重置」 |
| `ToolCallFormatError` | 7B | error | 現有 `"⚠️ 工具呼叫指令格式有誤..."` |
| `Tool.ToolError`（重試 2 次後仍失敗） | 7B | error | 現有 `"⚠️ 工具呼叫指令內容有誤..."`，`meta.retry_count=2` |
| `PermissionError`（工具執行遭拒） | 10~13 | error | 現有 `"抱歉，執行「{tool}」需要額外授權..."` |
| 工具逾時/連線錯誤 | 11 | error | `Architect/ToolExecution.md` §4 例外矩陣既有文案 |
| 原始結果非合法 JSON | 12 | success（降級為純文字，非錯誤） | 「非合法 JSON，已轉為純文字處理」 |
| 第二輪推理無輸出 | 16 | success（引導性回覆，非錯誤） | 現有 `"目前查詢到的資料不足以完整回答..."` |

---

## 10. 效能與可觀測性

| 指標 | 目標值 | 備註 |
| :--- | :--- | :--- |
| 步驟事件發射延遲 | 事件對應動作完成後 ≤ 50ms 內送出 | 確保「真即時」，不是批次回放 |
| 單一 `StepEvent` 序列化/渲染耗時 | ≤ 5ms | 沿用現有 Gradio `yield` 機制，無需額外序列化格式 |
| 步驟事件總數（長路徑，單一工具） | 約 17~21 個 `StepEvent`（含中間 running/success 狀態變化） | 供前端效能測試基準 |
| 日誌 | 每個 `StepEvent` 皆可選擇性寫入既有 `logger`（`harness`／`llm_reasoning`／`backend.pipeline`），不強制 | 供除錯與稽核，與思考區顯示解耦 |

---

## 11. 測試驗證點／驗收標準

- [ ] 短路徑（無需工具）思考區固定顯示①～⑧，結尾出現「【思考流程完成】」。
- [ ] 長路徑（需要工具）思考區顯示①～⑰，⑨～⑬ 隨工具呼叫數量正確重複。
- [ ] 每個步驟區塊在後端實際執行到該步驟的當下就出現，而非整輪結束後一次跳出（可用人工計時或 log 時間戳驗證步驟②與步驟⑰之間確實有明顯時間間隔）。
- [ ] 步驟⑥／⑮／⑯的內容確實逐字/逐 token 串流，非一次貼上完整文字。
- [ ] 步驟⑦A／⑯的內容同步出現在左側聊天氣泡（`mirrors_to_chat` 邏輯）。
- [ ] 人為觸發 `PromptFetchFailed`（如暫時停用系統提示詞快取）時，步驟④顯示為 `error` 狀態且不中斷對話。
- [ ] 人為觸發工具逾時，步驟⑩～⑬顯示為 `error` 狀態且第二輪推理仍正常產出降級回覆。
- [ ] 步驟⑦B／⑪／⑬顯示的內容為完整原文，未做任何遮蔽或省略字樣以外的處理。
- [ ] 步驟⑰顯示 `confidence_score`／`cited_sources`／`reasoning_summary`；`confidence_score < 0.6` 時額外顯示免責聲明樣式。
- [ ] 發送新問題時思考區正確清空重置，重新從①開始。

---

## 12. 附錄：完整事件序列範例

### 12.1 短路徑（8 步）

```
("step", StepEvent(1, receive_input, "輸入提問＋上下文（文件）", success, "為什麼很多 AI 工具都用 Python 開發？"))
("step", StepEvent(2, build_request, "構建請求（攜帶 Session ID）", success, "session_id=a1b2c3d4-..."))
("step", StepEvent(3, fetch_prompt_mode, "拉取當前模式（System Prompt）", running, "mode=default"))
("step", StepEvent(4, prompt_ready, "返回結構化 Prompt", success, "你是一個智慧助理...（完整內容）"))
("step", StepEvent(5, send_to_llm_r1, "發送完整 Prompt＋歷史對話＋提問", success, "歷史 3 則，thinking_mode=true"))
("step", StepEvent(6, llm_thinking_r1, "深度思考", running, "使用者想了解 Python 生態..."))  # 多次 delta 累加
("step", StepEvent(7, llm_final_answer_direct, "直接返回最終回答", running, "Python 之所以..."))  # branch=final_direct，多次 delta，同步進左側聊天
("step", StepEvent(8, deliver_final_answer, "輸出最終回覆", success, "已完成，耗時 2.3s"))
("end", None)
```

### 12.2 長路徑（17 步，含一次 `web_search` 呼叫）

```
①～⑥ 同上
("step", StepEvent(7, llm_tool_calls, "返回工具調用指令", success, '{"tool_calls":[{"function":{"name":"web_search","arguments":{"query":"台北市 今日天氣"}}}]}'))  # branch=tool_call
("step", StepEvent(8, dispatch_tool_pipeline, "交付工具調用請求", success, "web_search x1"))
("step", StepEvent(9, guardrails_precheck, "執行前置鉤子", skipped, "安全守衛尚未啟用，直接放行"))
("step", StepEvent(10, tool_execute, "執行具體工具", running, "執行「web_search」（http）…"))
("step", StepEvent(10, tool_execute, "執行具體工具", success, "耗時 812ms"))
("step", StepEvent(11, tool_raw_result, "返回原始結果", success, '{"results":[...]}（原始 JSON）'))
("step", StepEvent(12, tool_post_process, "後執行處理", success, "截斷比例：無"))
("step", StepEvent(13, tool_result_ready, "返回工具結果", success, "[Source: web_search] 台北市今日多雲...（完整內容）"))
("step", StepEvent(14, send_to_llm_r2, "再次送入模型", success, "[用戶提問]...\n[初步假設]...\n[實際查詢結果]..."))
("step", StepEvent(15, llm_thinking_r2, "綜合分析工具返回的信息", running, "查詢結果顯示..."))
("step", StepEvent(16, llm_final_answer_r2, "生成最終自然語言回覆", running, "根據最新資料，台北..."))  # 同步進左側聊天
("step", StepEvent(17, deliver_final_answer_r2, "輸出最終答案", success, meta={confidence_score:0.9, cited_sources:["call_abc123"], reasoning_summary:"tool_results=1項（成功1）、conflict=無、stale=否"}))
("end", None)
```

---

## 13. 後續實作待辦

| 檔案 | 變更類型 |
| :--- | :--- |
| `Trace/step_events.py`（新建） | 新增 `StepEvent`、`STEP_REGISTRY`、`MIRRORS_TO_CHAT` |
| `Guardrails/precheck.py`（新建） | 新增步驟⑨ stub generator |
| `Harness/harness.py` | `handle_turn()` 同步函式 → generator |
| `Backend/pipeline.py` | `execute_tool()` 同步函式 → generator（§6.4 為核心改動） |
| `LLMReasoning/reasoning.py` | `process()` 全面改用 `StepEvent`，插入 Guardrails 呼叫，改用 `Backend.execute_tool()` 新介面 |
| `LLMReasoning/agent_loop.py` / `resume_with_tool_result()` | 步驟⑭～⑰改用 `StepEvent`，移除獨立 `metadata` 事件 |
| `Frontend/app.py` | `render_thought_html()` 全面重寫（string → `list[StepEvent]`），`bot_response()` 事件迴圈改為單一 `"step"`/`"end"` 分支，新增 `mirrors_to_chat` 判斷 |
