# 規格書：LLM 推理與工具呼叫判斷模組

| 文件版本 | 1.0 |
| :--- | :--- |
| 撰寫日期 | 2026-08-24 |
| 目標框架 | Python Gradio (>= 4.0 / 5.0) |
| 核心目標 | 對應架構圖步驟 **⑤、⑥、⑦** ，聚焦於「完整 Prompt 建構」、「深度思考（Thinking Mode）」、「內部推理草稿生成」及「是否呼叫工具的判定」等核心邏輯。 |

---

## 1. 模組概述
組裝完整請求（系統指令 + 歷史對話 + 使用者提問）；<br>② 呼叫 LLM 並啟用「深度思考」模式，獲取內部推理草稿（`reason_content`）；<br>③ 基於模型輸出判定是否需要呼叫外部工具，若無需呼叫則直接回傳最終回答，若需呼叫則提取工具呼叫指令並流轉至工具管道。 |

---

## 2. 輸入資料

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `session_id` | string | ✅ | 會話唯一識別碼，用於關聯歷史對話 |
| `user_query` | string | ✅ | 使用者本次輸入的文字提問（已由前端預處理） |
| `attachments` | list[Attachment] | ❌ | 使用者上傳的檔案（已轉為 Markdown 並截斷，若超長） |
| `history` | list[Message] | ❌ | 從會話儲存中載入的歷史訊息（按時間升序），若無則為空列表 |
| `system_prompt` | string | ✅ | 由 System 模組回傳的目前模式系統指令（含角色、工具定義、安全紅線、目前日期） |
| `max_reason_tokens` | int | ✅ | 深度思考階段允許的最大 token 數（預設 4096） |
| `max_final_tokens` | int | ✅ | 最終回答允許的最大 token 數（預設 2048） |

---

## 3. 處理流程（詳細步驟）

### 3.1 組裝完整 Prompt

**輸入**：系統提示詞、歷史對話、使用者提問（及附件內容）

**步驟**：
1. **系統指令區塊**：將 `system_prompt` 原樣置於訊息列表首位，角色為 `system`。
2. **歷史訊息區塊**：從 `history` 中提取最近 N 條（受上下文視窗限制，例如 20 條），每條保持 `role`（`user`/`assistant`）和 `content` 結構。
3. **使用者提問區塊**：建立一條 `role="user"` 的訊息，`content` 為使用者提問及附件文字（若有）。
4. **Token 預算檢查**：若總 token 數超過模型上下文視窗（例如 128K），按「重要度 → 時間近」截斷歷史訊息（優先保留系統指令和目前提問）。

**輸出**：符合 DeepSeek‑V3 API 格式的訊息陣列 `messages = [system, ..., user]`。

---

### 3.2 呼叫 LLM 並啟用深度思考（Thinking Mode）

**目標**：讓模型在生成最終回答前，先產生內部推理草稿（`reason_content`），用於支撐後續的工具呼叫決策。

**呼叫參數**：

```json
{
  "model": "deepseek-v3",
  "messages": [...],               // 來自 3.1
  "reasoning_effort": "medium",    // 或 "high"，控制推理深度
  "max_reasoning_tokens": 4096,    // 由配置傳入
  "max_tokens": 2048,              // 最終輸出 token 數
  "tool_choice": "auto",           // 允許模型自主決定是否呼叫工具
  "tools": [                       // 系統提示詞中已包含工具定義，此處亦顯式傳遞
    { "type": "function", "function": { "name": "web_search", ... } },
    { "type": "function", "function": { "name": "read_file", ... } },
    ...
  ]
}
```

**處理細節**：
- 模型會先進行內部推理（`reasoning` 階段），生成 `reason_content`（此內容不直接輸出給使用者，僅用於內部邏輯）。
- 推理結束後，模型產生兩種可能的結果類型：
  - **類型 A**：最終回答（`content` 欄位有值，無 `tool_calls`）
  - **類型 B**：工具呼叫指令（`tool_calls` 陣列有值，`content` 可為空或僅包含簡短引導）

---

### 3.3 判斷是否無須呼叫工具（僅作判斷）

**觸發時機**：接收到 LLM 回應後，立即執行決策分支。

**判斷邏輯**：

```python
def decide_action(llm_response):
    if llm_response.get("tool_calls") is None or len(llm_response["tool_calls"]) == 0:
        # 無需呼叫工具
        return Action.FINAL_ANSWER
    else:
        # 需要呼叫工具
        return Action.TOOL_CALL
```

**關鍵約束**：
- 該判斷**僅基於模型輸出**，不額外進行規則兜底（除非安全模組攔截）。
- 若模型同時回傳了 `content` 和 `tool_calls`，仍視為**需呼叫工具**，`content` 可作為工具呼叫前的提示語暫存，但最終回覆將由工具結果結合推理草稿重新生成（見第 4 節）。

---

## 4. 輸出與後續流轉

| 判定結果 | 輸出動作 |
|---------|----------|
| **無需呼叫工具** | ① 將 `llm_response.content` 作為最終回覆；<br>② 記錄本次會話歷史（使用者提問 + 最終回答）；<br>③ 透過 Harness 直接回傳給前端（步驟⑧）。 |
| **需呼叫工具** | ① 提取 `tool_calls` 列表，傳遞給工具執行管道（步驟⑧）；<br>② 將本次 `reason_content` 及原始 `tool_calls` 暫存於會話上下文，待工具結果回傳後用於第二輪回合（步驟⑭～⑯）；<br>③ 等待工具管道回傳結果後，進行第二輪推理，結合 `reason_content` 和工具結果生成最終答案。 |

---

## 5. 異常處理與容錯

| 異常場景 | 處理方式 |
|---------|----------|
| LLM API 逾時 | 重試最多 2 次（指數退避），逾時後回傳友善降級回答，並記錄錯誤日誌。 |
| 推理內容截斷（`reason_content` 被截斷） | 記錄警告，仍使用現有推理草稿繼續流程，但標註可能影響決策品質。 |
| 工具呼叫格式錯誤（如缺少必填參數） | 不執行工具，立即回傳錯誤提示給使用者，要求重新提問。 |
| 歷史訊息過長導致上下文溢位 | 智慧截斷：優先移除最早的非系統訊息，並記錄截斷操作於除錯日誌。 |
| 安全守衛生成功阻斷（如偵測到敏感內容） | 拒絕執行工具呼叫，直接回傳安全攔截提示，不進行後續推理。 |

---

## 6. 效能指標與監控

| 指標 | 目標值 | 採集點 |
|------|--------|--------|
| 首次推理延遲（含思考時間） | ≤ 5s (P95) | LLM 呼叫開始至回應回傳 |
| 推理草稿 token 使用率 | ≤ 80% 的 `max_reasoning_tokens` | 模型回應的 `usage` 欄位 |
| 工具呼叫判定準確率 | ≥ 98%（人工抽查） | 對比使用者期望行為 |
| 上下文組裝耗時 | ≤ 100ms | 訊息列表建構與截斷邏輯 |

---

## 7. 介面定義（偽代碼）

```python
class LLMReasoningOrchestrator:
    def __init__(self, llm_client, system_cache, session_store):
        self.llm_client = llm_client
        self.system_cache = system_cache
        self.session_store = session_store

    def process(self, session_id: str, user_query: str, attachments: list = None):
        # 1. 獲取系統提示
        system_prompt = self.system_cache.get_prompt(session_id)
        # 2. 載入歷史
        history = self.session_store.load_history(session_id)
        # 3. 組裝訊息
        messages = self._assemble_messages(system_prompt, history, user_query, attachments)
        # 4. 呼叫 LLM（啟用推理模式）
        response = self.llm_client.chat_completion(
            messages=messages,
            reasoning_effort="medium",
            max_reasoning_tokens=4096,
            tools=TOOLS_DEFINITION
        )
        # 5. 判定動作
        if self._has_tool_calls(response):
            # 暫存推理草稿，進入工具呼叫流程
            self._handle_tool_call(session_id, response)
        else:
            # 直接回傳最終回答
            return response.content
```

> **附註**：本規格書與工具執行管道（步驟⑧～⑬）及第二輪推理（⑭～⑯）緊密配合，實際開發時需確保 `reason_content` 在會話上下文中的持久化，以便後續綜合推理時重複使用。