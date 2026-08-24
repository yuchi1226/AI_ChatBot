好的，這是一份根據您的需求撰寫的專業系統規格書，採用繁體中文，並針對 **Agent 第二輪推理（Agent Loop）** 的「工具結果綜合與最終應答」階段進行詳細規範。

---

# 系統規格書：第二輪推理機制（Agent Loop）規格書
**文件版本：** v2.0
**制定日期：** 2026-08-24
**負責單位：** AI 核心架構組 / 推理引擎團隊

---

## 1. 概述 (Overview)
### 1.1 目標
本規格書定義 Agent 系統中「第二輪推理（Agent Loop）」的具體實作規範。此階段旨在將**第一輪工具呼叫（Tool Call）所返回的原始數據**，與**初始階段的思考草稿（Draft Thought）** 進行上下文融合，透過再次送入模型進行深度語意分析與綜合推理，最終生成高質量、貼近事實且符合用戶意圖的最終自然語言回復。

### 1.2 適用範圍
本規範適用於所有需進行外部工具查詢（如資料庫檢索、API 呼叫、網頁爬蟲）並需對結果進行篩選、校正或總結的對話互動場景。

---

## 2. 輸入規格 (Input Specification)
第二輪推理引擎的輸入由兩大核心資料源組成，必須於進入該階段前完成封裝。

| 輸入參數 | 型別 | 說明 |
| :--- | :--- | :--- |
| **原始思考草稿**<br>`original_draft` | String / JSON | 第一輪推理時模型產生的初始思維鏈（CoT）。包含原始問題拆解、假設條件、以及預期的工具查詢參數。 |
| **工具結果集**<br>`tool_results` | List[ToolResponse] | 一個或多個工具執行完畢後所回傳的結構化或非結構化原始資料。需附帶工具來源標記（Tool ID）及執行狀態（成功/失敗）。 |
| **系統指令**<br>`system_prompt` | String | 定義 Agent 角色、輸出格式限制（如 JSON/Markdown）及語氣規範。 |

---

## 3. 處理邏輯規格 (Processing Logic)
本階段的核心是「綜合分析引擎」，必須依序執行以下四個子模組（Pipeline），不得跳躍或並行（Sequential）。

### 3.1 上下文重組與注入 (Context Reassembly)
- **動作**：將 `original_draft` 與 `tool_results` 依據時間戳記與邏輯關聯性重新排序。
- **規範**：建立一個「增強脈絡（Enhanced Context）」區塊，明確標示「用戶提問」、「初步假設」、「實際查詢結果」三個分區，確保模型能清楚區分**推測**與**事實**。

### 3.2 資料清理與特徵萃取 (Data Cleansing & Extraction)
- **動作**：對 `tool_results` 中的冗餘資訊（如 HTML 標籤、系統日誌、重複數據）進行語法層面的過濾。
- **規範**：萃取「關鍵實體（Entities）」、「數值指標（Metrics）」與「衝突點（Conflicts）」。若多個工具返回矛盾數據，必須將**矛盾標記**顯式寫入提示詞（Prompt）中，作為下一階段的分析重點。

### 3.3 邏輯校準與二次推理 (Logical Calibration)
- **動作**：將重組後的「增強脈絡」**再次送入 LLM**（第二輪 Forward Pass）。
- **提示詞工程規範**：
  - 強制要求模型對照 `original_draft` 的意圖，驗證 `tool_results` 是否足以回答問題。
  - 若數據不足，須在此步驟生成**「部分回答 + 缺失清單」**，但基於本規格書定義（最終輸出），若缺失嚴重需標記為「無法回答」。
  - 必須進行**來源引用（Citation）**，將回應內容錨定至特定的工具返回片段。

### 3.4 自然語言生成編排 (NLG Orchestration)
- **動作**：將校準後的邏輯事實轉化為流暢、簡潔且具有邏輯連貫性的中文（繁體）草稿。
- **規範**：
  - 禁止使用「根據工具回傳...」等機械式開場，應改為「經查詢相關數據顯示...」或「目前的情況是...」。
  - 若原始資料包含數值，必須轉換為易讀的單位（如將秒數轉為「幾分鐘」）。

---

## 4. 輸出規格 (Output Specification)
最終輸出為單一的回應物件，需包含後設資料（Metadata）以便前端展示或除錯。

| 輸出欄位 | 型別 | 必填 | 描述 |
| :--- | :--- | :--- | :--- |
| `final_answer` | String | 是 | 最終要呈現給使用者的自然語言回復。字數限制依場景設定（預設 500 字內）。 |
| `confidence_score` | Float (0.0~1.0) | 是 | 模型對於回答內容與工具事實相符程度的信心指數（低於 0.6 時建議前端顯示免責聲明）。 |
| `cited_sources` | List[String] | 否 | 引用來源的簡短標記（例如：工具 A 的 ID）。 |
| `reasoning_summary` | String | 否 | 供開發者檢視的第二輪推理濃縮摘要（用於 Log 除錯）。 |

---

## 5. 例外處理與邊界條件 (Edge Cases)
| 情境 | 處理機制 |
| :--- | :--- |
| **工具結果為空 (Empty Set)** | 第二輪推理需辨識此狀況，並輸出引導性回覆（例如：「目前未查詢到相關資料，建議調整篩選條件」），不得隨意捏造數據。 |
| **原始草稿與結果嚴重衝突** | 強制觸發 `confidence_score` 降級（-0.3），並在 `final_answer` 中明確指出前後差異，使用「然而」、「但根據實際數據」等轉折詞。 |
| **結果超過 Token 限制** | 啟動「壓縮摘要（Summarization）」子程序，先將過長的工具結果濃縮為 300 tokens 內的關鍵摘要，再進入 3.3 邏輯校準。 |
| **時間敏感資訊** | 必須比對工具返回的時間戳與當前系統時間，若過期（如超過 1 小時），須在回覆中註明時效性。 |

---

## 6. 效能指標 (Performance Metrics)
為確保使用者體驗，第二輪推理階段（從輸入到輸出）必須滿足以下非功能性需求：

| 指標 | 目標值 | 備註 |
| :--- | :--- | :--- |
| **端對端延遲 (E2E Latency)** | ≤ 5 秒 (P95) | 包含模型推論時間 |
| **事實準確率 (Factual Accuracy)** | ≥ 92% | 人工抽檢比對工具原始資料 |
| **Token 總消耗** | ≤ 4,096 tokens | 避免昂貴的長上下文成本，超出者觸發 5.3 壓縮機制 |

---

## 7. 流程圖邏輯偽代碼 (Pseudo-Code)
```python
def second_round_inference(original_draft, tool_results, system_prompt):
    # 1. 上下文重組
    enhanced_context = merge_with_timeline(original_draft, tool_results)
    
    # 2. 清理與萃取
    clean_data, conflicts = extract_entities_and_detect_conflicts(tool_results)
    
    # 3. 構建最終提示詞
    final_prompt = build_prompt(
        sys=system_prompt,
        context=enhanced_context,
        conflict_note=conflicts,
        instruction="請綜合以上工具回饋與原始思維，進行第二輪校準並生成最終回覆。"
    )
    
    # 4. 再次送入模型
    llm_output = model.generate(final_prompt)
    
    # 5. 解析與包裝輸出
    return {
        "final_answer": llm_output.content,
        "confidence_score": llm_output.confidence,
        "cited_sources": extract_citations(llm_output),
        "reasoning_summary": llm_output.short_reason
    }
```