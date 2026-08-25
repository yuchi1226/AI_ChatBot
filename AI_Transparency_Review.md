# AI_ChatBot 透明度（AI Transparency）審查報告

審查範圍：以「揭露 AI 決策/推理過程給使用者」為核心目標，比對 `Architect/` 規格書（尤其是 `ThoughtPanelStep.md`、`AgentLoop.md`）與 `Harness/`、`LLMReasoning/`、`Backend/`、`Frontend/`、`Trace/`、`Guardrails/` 的實際程式碼。整體架構設計得相當扎實——步驟①～⑰的事件契約、"不遮蔽"政策、稽核日誌埋點都已經在規格書中明確定義；但**規格與實作之間有幾個關鍵斷點，導致目前系統實際「說到但沒做到」的透明度承諾比想像中多**。以下依影響程度排序。

---

## 一、高優先：直接削弱「透明」承諾的缺口

### 1. 信心分數／引用來源／免責聲明——算出來了，但畫面上完全看不到

- **證據**：`LLMReasoning/reasoning.py` 第 578–588 行，步驟⑰（`deliver_final_answer_r2`）的 `StepEvent.meta` 確實帶了 `confidence_score`、`cited_sources`、`reasoning_summary`、`needs_disclaimer`。
- **問題**：`Frontend/app.py` 的 `render_thought_html()`（第 487–514 行）只讀取每個 step 的 `title`、`status`、`content`，**從未讀取 `view["meta"]`**。`_apply_step_event()`（第 480–481 行）雖然把 `meta` 存進 `step_views`，但沒有任何程式碼把它渲染出來。
- **後果**：`AgentLoop.md` §4 明訂「`confidence_score < 0.6` 時建議前端顯示免責聲明」、`ThoughtPanelStep.md` 驗收標準第 8 條也白紙黑字要求「步驟⑰顯示 confidence_score／cited_sources／reasoning_summary」——這是整個透明度機制裡最貼近「使用者最終要不要相信這個答案」的訊號，目前完全沒有出現在 UI 上。使用者只會看到「已完成，回覆已送出」這句固定文字。
- **建議**：在 `render_thought_html()` 針對 `step_no == 17` 額外渲染一個信心分數徽章 + 引用來源清單；`needs_disclaimer=True` 時在該訊息的聊天氣泡（不只是思考區）加上明顯的免責聲明樣式，因為使用者不見得會展開思考區去看。

### 2.「軌跡」分頁是空的佔位文字

- **證據**：`Frontend/app.py` 第 696–702 行，`gr.Tab(label="軌跡")` 底下只有一行 `gr.Markdown("待放架構圖")`。
- **問題**：這個分頁的命名（軌跡）強烈暗示它應該是給使用者事後查閱推理軌跡、或至少展示架構圖的地方，但目前完全沒有內容。
- **建議**：短期先放上 `diagram.png`／循序圖說明其運作方式（成本很低，且能立刻兌現「軌跡」這個名稱的一部分承諾）；中期考慮做成第 3 點所述的歷史軌跡瀏覽器。

### 3. 思考鏈只存在於「這一輪回覆的當下」，結束就消失

- **證據**：`bot_response()`（`Frontend/app.py` 第 549–619 行）裡的 `step_views` 是函式內的區域變數，只在 generator 存活期間存在；沒有寫進 `gr.State`、`Harness.SessionState`，也沒有任何落地儲存。
- **後果**：
  - 使用者問完下一個問題、或重新整理頁面，前一輪完整的①～⑰步驟軌跡就永久遺失，無法回頭查閱。
  - `Harness/session.py` 的 `SessionStore` 本身也是純記憶體（`_sessions: Dict`），連對話歷史都在行程重啟後歸零，遑論推理軌跡。
  - 對一個以「透明」為賣點的產品而言，透明度目前只有「即時」這個維度，完全沒有「事後可稽核」這個維度。
- **建議**：至少把每一輪的 `list[StepEvent]` 序列化後掛在 `SessionState`（例如 `session.turn_traces: List[List[StepEvent]]`），並在聊天氣泡旁提供「查看這則回覆的完整推理過程」的按鈕/展開區，而不是只能看當下這一輪。

### 4. 稽核日誌（audit log）已寫好，但從未真正輸出到任何地方

- **證據**：
  - `Harness/payload.py` 第 34、164–174 行：`_audit_logger = logging.getLogger("audit.system_prompt")`，`assemble_request()` 每次都會用 `_audit_logger.info(...)` 記錄完整的渲染後系統提示詞，註解明確寫著「供合規審查」。
  - `LLMReasoning/reasoning.py` 第 73、565–571 行：`_audit_logger = logging.getLogger("audit.agent_loop")`，同樣以 `.info()` 記錄 `confidence_score`／`cited_sources`／`reasoning_summary`。
  - `Prompt/system_prompt_cache.py` 第 48、156–161 行：`get_system_prompt()` 也用 `.info()` 記錄每次範本拉取。
  - 全專案（含 `main.py`、`Frontend/app.py`）搜尋 `basicConfig`／`addHandler`／`FileHandler` **完全沒有任何結果**。
- **問題**：Python `logging` 模組在沒有明確設定的情況下，root logger 預設層級是 `WARNING`；所有這些 `.info()` 等級的稽核紀錄，在目前的執行方式下（`python main.py`）**實際上不會輸出到任何地方**——不是終端機、不是檔案，什麼都沒有。也就是說，程式碼裡寫得很仔細的「稽核日誌供合規審查」，目前是一個看起來存在、但實際上是空的功能。
- **建議**：這是最容易修、CP 值最高的一項——加一個 `logging.basicConfig()`（或更完整的 `logging.config.dictConfig`），把 `audit.*` 這幾個 logger 導向獨立的稽核日誌檔案（並與一般除錯日誌分開，方便之後做存取控管），同時把層級明確設為 `INFO`。

### 5. 讚／踩／複製只是 `print()`，沒有落地、也沒有連回對應的推理軌跡

- **證據**：`Frontend/app.py` 第 621–626 行：
  ```python
  def on_like(data: gr.LikeData):
      feedback = "讚" if data.liked else "踩"
      print(f"[feedback] index={data.index} value={feedback} message={data.value!r}")

  def on_copy(data: gr.CopyData):
      print(f"[copy] value={data.value!r}")
  ```
- **問題**：`FrontendUIUX.md` 原始規格只要求按鈕本身要能動作，但既然專案的核心價值是「透明可稽核」，讚／踩訊號如果沒有被保存、也沒有跟第 3 點所述的推理軌跡建立關聯，就失去了「讓使用者的信任回饋能夠回溯到是哪一段推理/工具結果造成問題」這個最有價值的用途——目前連重開一次網頁，這些回饋紀錄就完全消失。
- **建議**：至少把回饋寫進與第 4 點同一套稽核日誌；理想狀況是連同該則回覆對應的 `step_views`／`confidence_score`／`cited_sources` 一起記錄，未來才能做「使用者標記為錯誤的回答，信心分數/引用來源分布是什麼樣子」這類分析。

---

## 二、中優先：與「不遮蔽」政策相關的安全／一致性落差

### 6. `http_request` 工具沒有網域白名單，等於 LLM 可自主觸發任意對外連線

- **證據**：`Backend/adapters/http_request.py` 第 32–57 行，直接依模型給的 `url` 發出請求，沒有任何 allowlist／私網位址檢查；對照 `file_read`／`file_write` 有 `resolve_whitelisted_path()`（`Backend/adapters/base.py` 第 65–85 行）做目錄白名單，`http_request` 明顯少一層對等的防護。
- **後果**：搭配第 8 點「Guardrails 全放行」，代表模型只要判斷需要呼叫 `http_request`，就能無審查地打任何內外部網址（含理論上的 SSRF 風險），而使用者只有在事後的思考區才看得到這件事發生過，無法事前阻止。這跟循序圖裡原本設計的「⚠️ 請求批准／✅ 確認」使用者授權子流程的精神是衝突的——那個子流程目前完全沒有實作（見下一點）。
- **建議**：至少加上網域白名單/黑名單（尤其排除內網位址段），或要求 `http_request` 一律落入「需要使用者授權」分支。

### 7. 循序圖裡「使用者授權」子流程有畫、有寫規格，但零實作

- **證據**：`Architect/Architect.md` 循序圖明確畫出「⚠️ 請求批准／✅ 確認」分支；`Guardrails/precheck.py` 第 8–23 行的 docstring 也承認「使用者授權子流程，留待本套件後續實作」；`Trace/step_events.py` 第 67 行雖然已經預留了 `guardrails_user_authorization` 這個 step_key，但沒有任何模組會發出這個事件。
- **後果**：目前不存在「敏感操作前先讓使用者按確認」這件事——所有工具呼叫（含寫檔、外部 HTTP 請求）都是全自動放行。對透明度而言，"發生後才讓你看到" 和 "發生前先讓你同意" 是完全不同等級的透明——現在只做到前者。

### 8. Guardrails 是純 stub（一律放行），但系統提示詞的 `safety_guardrails` 卻寫著具體的安全紅線

- **證據**：`Prompt/system_prompt_cache.py` 第 72–75 行，系統提示詞明確告訴 LLM「禁止提供暴力、非法或有害內容…」，但 `Guardrails/precheck.py`（第 35–58 行）對所有工具呼叫一律 `status="skipped"` 放行，沒有任何機制真的檢查內容。
- **問題**：這是規則本身而非執行面的落差——系統提示詞讓 LLM（以及間接地讓使用者）以為有安全審查機制在運作，但程式碼層面完全沒有對應的強制力。對「透明」的定義而言，若要誠實，這句安全紅線的措辭應該更明確地反映「這是提示詞層級的軟性約束，尚無程式碼層級的強制審查」，或者儘快把 Guardrails 從 stub 補上最基本的規則式審查（例如敏感詞黑名單）。

### 9. `confidence_score` 是規則式啟發法，不是模型真實信心；一旦補上 UI（見第 1 點），措辭需要誠實標註

- **證據**：`LLMReasoning/agent_loop.py` 第 235–251 行，`compute_confidence_score()` 只是「基準 1.0，工具全部失敗封頂 0.4，偵測到數字集合不重疊就 -0.3」的簡單規則，跟模型本身的不確定性完全無關（本機 Ollama 也沒有官方信心 API，程式碼註解裡也承認了這一點）。
- **建議**：修好第 1 點的顯示缺口之後，UI 上的標籤務必寫清楚「基於工具執行成功率與衝突偵測的粗略指標」，不要讓使用者誤以為這是模型自評的信心值——否則等於用一個看似精確的數字製造虛假的確定感，反而傷害透明度。

### 10. 矛盾偵測（`detect_conflicts`）非常粗糙，會漏掉大部分真實語意矛盾

- **證據**：`LLMReasoning/agent_loop.py` 第 121–160 行，只比對成功結果裡「數字集合是否完全不重疊」，日期、頁碼等雜訊已被迴避，但同時也代表任何非數值型的矛盾（例如兩個來源對同一件事給出不同的文字結論）完全偵測不到。
- **影響**：這個訊號會餵進 confidence_score 與（未來要顯示的）免責聲明判斷，偵測力不足會讓「低信心」警告出現得比實際情況少，等於系統在不知不覺中對使用者「過度自信」。此項目前優先度可放在第 1、4 點之後。

---

## 三、低優先：完整性與一致性缺口（會間接影響透明度的可信度）

### 11. 系統提示詞宣稱 7 個工具都能用，但 `code_interpreter`、`database_query` 其實尚未實作

- **證據**：`Tool/catalog.py` 定義了完整的 7 個工具 JSON Schema 並塞進系統提示詞；但 `Backend/adapters/code_interpreter.py`、`Backend/adapters/database_query.py`（各自第 21–27、16–22 行）一律直接回傳「尚未上線」錯誤。
- **這不是嚴重的誠實問題**（因為執行失敗時確實有老實告知使用者「尚未上線」，符合不捏造的原則），**但會製造無意義的推理彎路**：模型可能規劃了一整串依賴這兩個工具的思路，繞了一圈才發現此路不通，這段過程雖然會誠實地顯示在思考區，但對使用者體驗與可信度觀感都不理想。
- **建議**：在工具描述末尾加註「（目前尚未上線，請避免規劃依賴此工具的步驟）」，或乾脆從 `get_tool_definitions()` 回傳清單中先移除未實作的工具，等真正實作後再加回去。

### 12. `knowledge_base_search` 沒有匯入介面，預設集合大概率是空的

- **證據**：`Backend/rag/ingest.py` 的 docstring 自己承認「目前 Frontend/ 沒有檔案上傳後自動建庫的流程接到這裡」；`ingest_document()` 只能被程式碼直接呼叫，沒有 CLI 或 UI。
- **影響**：跟第 11 點類似——工具白名單裡存在、系統提示詞也會教模型何時使用它，但實際呼叫多半會得到空結果，屬於「能力清單」與「實際能力」的落差。

### 13. 對話歷史／Session 純記憶體，行程重啟即全部遺失

- 見第 3 點的延伸：這不只影響推理軌跡，連對話本身的長期可稽核性都不存在。若「透明」的目標包含「使用者或稽核者事後能重建當時發生了什麼」，這是比 UI 顯示更基礎的一層缺口。

---

## 建議優先順序（若要在下一輪開發聚焦在「AI Transparency」）

1. **第 1 點**（顯示 confidence_score／cited_sources／免責聲明）＋**第 4 點**（把稽核日誌真正接上 handler）——兩者都是「後端資料已經算好/寫好，只差最後一哩路沒接上」，投入產出比最高。
2. **第 3 點**（推理軌跡持久化＋可回顧）＋**第 5 點**（回饋落地並與軌跡關聯）——把「透明」從「這一刻看得到」升級為「事後也能查」，是這個專案要真正兌現「AI Transparency」定位的關鍵一步。
3. **第 6、7 點**（`http_request` 白名單、使用者授權子流程）——補上「事前同意」這一層，否則「不遮蔽」的透明度政策在高風險操作上反而顯得矛盾（做了才讓你知道）。
4. 其餘（Guardrails 實質審查、confidence 措辭誠實化、矛盾偵測精進、工具清單與實際能力對齊）可視開發資源逐步排入。
