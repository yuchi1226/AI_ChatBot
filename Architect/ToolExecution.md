# 規格書：工具執行與結果處理模組 (Tool Execution & Result Processing Module)

| 文件版本 | 1.0 |
| :--- | :--- |
| 撰寫日期 | 2026-08-24 |
| 目標框架 | Python Gradio (>= 4.0 / 5.0) |
| 核心目標 | 定義步驟⑩至⑬ |

---

## 1. 概述 (Overview)
本模組隸屬於「工具執行管道 (Tool Pipeline)」，負責接收來自核心調度器 (Agent Harness) 的具體工具呼叫請求，執行底層操作，並將雜亂的原始回饋標準化為大語言模型 (LLM) 易於理解的結構化資料。本模組是銜接 AI 推理能力與真實世界資料的關鍵橋樑。

## 2. 輸入與前置條件 (Input & Preconditions)
- **輸入物件**：`ToolExecutionRequest`
  ```json
  {
    "tool_call_id": "call_abc123",
    "tool_name": "web_search | file_reader | calculator | ...",
    "arguments": { "query": "台北天氣", "file_path": "/data/report.pdf" },
    "execution_mode": "http" | "local",
    "max_result_length": 8000  // 由 Harness 動態注入
  }
  ```
- **前置條件**：已通過安全守衛 (Guardrails) 的權限審查（步驟⑨），必要時已取得使用者授權確認。

## 3. 詳細規格說明 (Detailed Specifications)

### 3.1 步驟⑩：執行具體工具 (Execute Tool)
此步驟根據 `execution_mode` 採用不同適配器 (Adapter) 執行底層調用。

| 執行模式 | 適用情境 | 實作規範 | 逾時設定 (Timeout) |
| :--- | :--- | :--- | :--- |
| **HTTP 請求** | 第三方 API (搜尋引擎、資料庫查詢) | 使用非同步 HTTP Client。須遵循工具定義中的 OpenAPI 規範，自動帶入 API Key 或 OAuth Token（由 Secrets Manager 注入）。 | 30 秒 (可配置) |
| **本地執行** | 內部函數、檔案 I/O、Shell 指令 | 運行於隔離的沙箱 (Sandbox) 環境中。檔案操作須限制於白名單目錄內，禁止系統層級危險指令。 | 60 秒 (可配置) |

**錯誤處理策略**：
- 若發生網路超時或連線錯誤，應立即中斷重試（最多重試 1 次），避免堵塞 Agent Loop。
- 本地執行若權限不足，直接拋回 `PermissionError` 至 Harness，不進行重試。

---

### 3.2 步驟⑪：返回原始結果 (Return Raw Result)
工具執行完畢後，必須統一封裝為 `RawToolResponse` 結構，保留原始資料的完整性與 Metadata。

```json
{
  "tool_call_id": "call_abc123",
  "status": "success" | "error",
  "raw_data": {
    "content_type": "application/json" | "text/plain" | "binary",
    "body": { ... } 或 "[Raw Text Content]"
  },
  "metadata": {
    "execution_time_ms": 152,
    "http_status_code": 200 (若適用),
    "size_bytes": 24500
  },
  "error": null (或 ErrorDetail 物件)
}
```

**規範重點**：
- 對於 **JSON** 回應，須保留完整結構，不預先進行欄位刪減。
- 對於 **文字** 回應，須偵測編碼 (Encoding)，強制統一轉換為 UTF-8。
- 對於 **二進位** 資料（如圖片、PDF），原則上不直接傳遞原始 blob，僅回傳檔案路徑或 Base64 編碼之摘要（須配合後續處理）。

---

### 3.3 步驟⑫：後執行處理 (Post-Execution Processing)
為了防止原始資料過大消耗 LLM 的 Token 配額，並確保資料可讀性，`ToolResponseProcessor` 將執行以下三階段處理：

1.  **結構提取 (Structured Extraction)**：
    - 若原始資料為 JSON，自動扁平化 (Flatten) 深層巢狀結構，或提取關鍵陣列前 N 筆（例如搜尋結果僅保留前 5 個連結）。
    - 若為純文字，保留完整段落，但移除多餘的換行符與控制字符。

2.  **內容截斷 (Truncation Strategy)**：
    - 採用 **「頭尾保留法 (Head-Tail Truncation)」**。保留內容的開頭（通常包含主旨）與結尾（通常包含結論），中間過長部分以 `...[已省略 X 字元]...` 代替。
    - **硬性限制**：最終輸出至 Harness 的字串長度不得超過 `max_result_length`（預設 8000 字元）。若工具為檔案讀取且超過限制，則僅回傳檔案摘要（如行數、檔案大小）與前 100 行內容。

3.  **格式轉換 (Format Normalization)**：
    - 將處理後的資料標準化為純文字（Plain Text）或 Markdown 格式，因為 LLM 對此兩種格式的讀取效率最佳。
    - 附加 **「資料來源標記 (Provenance Tagging)」**：在結果頂部插入 `[Source: URL]` 或 `[File: path]`，便於 LLM 生成答案時附帶引用。

---

### 3.4 步驟⑬：返回工具結果 (Return Tool Result)
處理完成後，封裝為最終交付給核心調度器 (Harness) 的 `FinalToolResult` 物件。此即為序列圖中傳遞給 Harness 的標準格式。

```json
{
  "tool_call_id": "call_abc123",
  "is_success": true,
  "content": "[此處為經截斷/格式化後的字串內容，LLM 將直接讀取此欄位]",
  "metadata": {
    "original_size": 24500,
    "truncated": true,
    "truncation_ratio": "67%"
  },
  "attachments": [] // 預留欄位，若為圖片分析，可放置 256x256 的縮圖 Base64
}
```

**錯誤回傳規範**：
- 若執行失敗（如 API 金鑰失效），`is_success` 為 `false`，`content` 欄位改為填充 **「使用者友善錯誤訊息」**（而非直接顯示系統堆疊追蹤），例如：`"抱歉，搜尋服務暫時無法連線，請稍後重試。"`，使 LLM 能以此為據進行對答。

## 4. 例外處理矩陣 (Exception Matrix)

| 異常情境 | 系統行為 (步驟⑫應對) | 返回給 Harness 的內容 |
| :--- | :--- | :--- |
| 原始結果為空 (null/空字串) | 直接返回 `"無相關結果"`，不觸發截斷邏輯。 | `is_success: true`, `content: "無相關結果"` |
| 原始結果超出限制 (Overflow) | 執行頭尾截斷，並在結尾加入 `... (資料過長已縮減)`。 | `is_success: true`, `truncated: true` |
| 原始結果非合法 JSON 結構 | 放棄 JSON 解析，直接將其視為純文字字串處理。 | 轉為純文字格式，保留原始換行。 |
| 連線逾時 (Timeout) | 不再進行格式化，直接覆寫內容。 | `is_success: false`, `content: "工具執行逾時，請檢查網路狀態"` |

## 5. 效能與監控指標 (Performance & Observability)
為確保 Agent Loop 的流暢度，本模組在步驟 ⑫ 與 ⑬ 之間須埋入以下 Log 指標：

- `tool_execution_duration`：步驟⑩開始至步驟⑬結束的總耗時。
- `tool_result_compression_ratio`：壓縮後大小 / 原始大小，若比值過低（< 5%）需發出 Warning，代表原始資料可能有過多無用雜訊。
- `truncation_occurred`：布林值，用於監控未來是否需要加大 LLM 的 Context Window 設定。
