# 前端UIUX專案規格書

| 文件版本 | 1.0 |
| :--- | :--- |
| 撰寫日期 | 2026-08-21 |
| 目標框架 | Python Gradio (>= 4.0 / 5.0) |
| 核心目標 | 實現「對話」與「思考邏輯」分離顯示，並提供回饋機制。 |

---

## 1. 概述
建置一款具備**透明思維鏈 (CoT)** 的問答聊天機器人。使用者提問後，系統不僅回覆最終答案，亦需在獨立區塊中**逐步展示** AI 的推理過程，以提升 AI 回覆的可信度與可調試性。

---

## 2. 版面配置 (UI Layout)
採用 **左右雙欄** (Two-Column) 佈局，佔滿全視口高度 (100vh)。

| 區域 | 比例 | 元件類型 (Gradio Element) | 內容描述 |
| :--- | :--- | :--- | :--- |
| **左側 (對話區)** | `scale=2` (約 66%) | `gr.Chatbot()` | 顯示使用者與 AI 的歷史問答記錄。頭像區分（User / AI）。 |
| **右側 (思考區)** | `scale=1` (約 34%) | `gr.Markdown()` 或 `gr.HTML()` | 顯示當前（或最新）回覆對應的**完整思考鏈**。需支援自動滾動至底部。 |

> **UI 容器**：整體置入 `gr.Blocks()` 中，使用 `gr.Row()` 進行左右分割。

---

## 3. 核心功能需求 (Functional Requirements)

### FR-01：對話互動 (Chat Interface)
- **輸入**：頁面底部設有 `gr.Textbox()` 作為訊息輸入框（支援 Enter 發送）。
- **輸出**：使用者訊息立即顯示於左側 Chatbot 區；AI 回覆流式生成於左側。

### FR-02：思考過程逐步吐字 (Step-by-Step Streaming)
- **觸發時機**：當 AI 開始生成回覆時，**右側思考區**必須同步開始更新。
- **視覺風格**：思考過程需有別於一般文字（例如：使用灰色背景區塊、縮排、或加上 🤔 圖示前綴）。
- **流式行為 (Streaming)**：
  - 文字必須**逐字（或逐 Token）** 顯示，不可等待完整生成後才一次跳出。
  - 若思考過程有結構（如步驟 1, 2, 3），建議使用 Markdown 有序/無序列表渲染。
- **狀態管理**：當新問題發送時，右側思考區需**清空重置**，再開始顯示新思維鏈。

### FR-03：單則回覆互動按鈕 (每條回復專屬)
左側 `gr.Chatbot()` 中的 **每一則 AI 回覆氣泡** 下方，必須固定顯示三個操作圖示按鈕：

| 按鈕 | 圖示 | 功能描述 |
| :--- | :--- | :--- |
| **複製 (Copy)** | 📋 | 點擊後將**該則 AI 回覆的純文字內容**複製到系統剪貼簿。需觸發瀏覽器 Copy 事件。 |
| **讚 (Like)** | 👍 | 點擊後按鈕變色（如藍色），代表正面回饋。再次點擊可取消。 |
| **踩 (Dislike)** | 👎 | 點擊後按鈕變色（如紅色），代表負面回饋。再次點擊可取消。 |

> **重要限制**：Gradio 原生 `gr.Chatbot()` 並不支援在每個氣泡下方自訂按鈕。**技術實現必須**透過 `gr.HTML` 自訂元件，或使用 Gradio 的 `JavaScript` 事件監聽 (`js` 參數) 來攔截 DOM 節點進行注入，以實現「每則回覆」專屬的按鈕。

---

## 4. 非功能性需求 (Non-Functional Requirements)

| 項目 | 規格要求 |
| :--- | :--- |
| **響應速度** | 按下 Enter 後，右側思考區必須在 **500ms 內** 開始顯示第一個字元。 |
| **思考區滾動** | 當思考內容超過可視區域時，右側區塊需**自動滾動至底部**，確保使用者始終看到最新推理步驟。 |
| **按鈕反饋** | 點擊讚/踩時，需有即時視覺狀態變化（無需等待後端回傳），避免 UI 延遲感。 |
| **資料格式** | 後端串接時，預期 WebSocket 或 Server-Sent Events (SSE) 傳輸格式為 JSON：`{"response": "最終答案", "thought": "逐步思考..."}`。 |

---

## 5. 技術實現規範 (Implementation Guidelines for Gradio)

### 5.1 雙欄流式更新策略
- 使用 `gr.Chatbot()` 的 `value` 參數結合 `gr.State()` 管理對話歷史。
- 在 `@gr.on(submit)` 或 `.then()` 鏈中，使用 **Python Generator (`yield`)** 來達成雙輸出更新：
  - `yield [ 更新後的對話歷史, 更新後的思考Markdown ]`
- *範例程式碼結構*：
  ```python
  def respond(message, chat_history, thought_history):
      # 初始化思考區
      thought = "🤔 步驟 1: 分析問題...\n"
      yield chat_history + [[message, None]], thought
      
      # 模擬逐步思考與最終回覆
      full_response = ""
      for chunk in get_ai_stream(message):
          thought += chunk # 假設思考與回答交織，或分開處理
          # 逐步更新右側
          yield updated_chat_history, thought 
  ```

### 5.2 自訂按鈕實現 (因應 FR-03)
由於 `gr.Chatbot` 的侷限性，建議以下實作路徑：
1.  **路徑 A (純前端 JS 注入)**：在 `gr.Blocks` 載入完成時，透過 `js` 函數監聽 `gr.Chatbot` 的 DOM 變化，動態在每個 `.message-wrap` 下新增按鈕 Div。
2.  **路徑 B (自訂元件)**：放棄 `gr.Chatbot`，改為使用 `gr.HTML` 配合 CSS 完全自訂對話氣泡與按鈕結構（靈活性最高）。
3.  **回饋數據傳遞**：按鈕點擊後，透過 `gr.Number` (隱藏) 或 `gr.State` 儲存 `(message_index, feedback_type)`，並呼叫後端 API 進行記錄。

### 5.3 剪貼簿複製
- 複製功能不依賴後端，完全由前端 JavaScript 執行 `navigator.clipboard.writeText(text)`。

---

## 6. 使用者流程 (User Flow)
1.  使用者於輸入框鍵入問題。
2.  左側對話區顯示使用者頭像與問題。
3.  **右側思考區**瞬間清空，並開始以打字機效果逐字輸出 AI 的推理步驟。
4.  左側對話區 AI 頭像開始輸出最終回覆（亦支援逐字輸出）。
5.  當 AI 生成完畢（Streaming 結束），該則 AI 回覆下方**浮現** 👍 / 👎 / 📋 按鈕組。
6.  使用者點擊讚/踩，按鈕狀態變更；點擊複製，系統 Toast 提示「已複製」。

---

## 7. 驗收標準 (Acceptance Criteria)
- [ ] 版面確實為左 66%、右 34% 之雙欄設計。
- [ ] 右側思考過程在 AI 回應期間確實為「逐步顯示」，而非一次跳轉。
- [ ] 每則 AI 回覆皆獨立擁有複製、讚、踩按鈕，且點擊讚/踩僅影響該則訊息。
- [ ] 點擊複製能成功將該則回覆文字存入剪貼簿。
- [ ] 發送新問題時，右側思考區會重置為空白，並重新開始增量寫入。

---

## 8. 附錄：後端 API 接口建議
為確保前端規格順利運行，後端 Streaming API 建議規格如下：

```json
// Server-Sent Events (SSE) 或 WebSocket 傳輸格式
{
  "event": "thought_chunk",
  "data": "步驟 1：計算 1+1..." // 推送至右側
}
{
  "event": "response_chunk", 
  "data": "結果是" // 推送至左側
}
{
  "event": "end",
  "data": null // 觸發按鈕顯示
}
```