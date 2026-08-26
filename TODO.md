# AI_ChatBot 架構落差 TODO 清單

> 產生時間：2026-08-26
> 依據：`Architect/Architect.md` 循序圖（步驟①～⑰）以及其餘 8 份規格書
> （`AgentLoop.md`／`FrontendUIUX.md`／`Harness.md`／`LLMReasoning.md`／
> `PreparatoryPhase.md`／`ThoughtPanelStep.md`／`ToolCalling.md`／`ToolExecution.md`），
> 逐一比對 `Harness/`、`LLMReasoning/`、`Backend/`、`Tool/`、`Prompt/`、`LLM/`、
> `Guardrails/`、`Trace/`、`Frontend/` 現有程式碼後整理。

## 結論先講

`Architect/ThoughtPanelStep.md`（步驟化即時串流思考區）這份最新規格書所定義的骨架
**已經完整落地**：`Trace/step_events.py`、`Harness.handle_turn()`、
`Backend.execute_tool()`、`LLMReasoning.process()`／`resume_with_tool_result()`、
`Frontend/app.py` 都已改成 generator + `StepEvent`，①～⑰ 全數即時發射，短路徑／
長路徑、錯誤狀態呈現、頭尾截斷、重試機制等細節也都對得上規格書文字。

真正的缺口集中在三類：**(1) 規格書已計算好但前端沒有顯示出來的資料**、
**(2) 規格書寫了但明確標注「暫不實作」的子流程**、**(3) 兩個完全沒有底層能力
支撐的工具（沙箱執行、資料庫連線）**。以下依優先級列出。

---

## P0：功能缺口（已算出資料但沒有出口 / 使用者實際會卡住的地方）

- [ ] **步驟⑰的 `confidence_score`／`cited_sources`／`reasoning_summary`／免責聲明沒有顯示在思考區**
  `LLMReasoning/agent_loop.py` 算好這四個欄位，`reasoning.py` 也確實把它們塞進
  `StepEvent.meta`（見 `resume_with_tool_result()` 尾端），但 `Frontend/app.py` 的
  `_apply_step_event()` 只把 `event.meta` 整包存進 `view["meta"]`，
  `render_thought_html()` 從頭到尾**只讀 `title`／`content`／`status`，從未讀取
  `meta`**——確認過整個 `Frontend/app.py` 沒有任何一處出現
  `confidence`／`disclaimer`／`免責` 字樣。等於白算了一輪信心分數與引用來源，
  使用者完全看不到。直接違反 `ThoughtPanelStep.md` §11 驗收標準第 9 條「步驟⑰顯示
  confidence_score／cited_sources／reasoning_summary；confidence_score < 0.6 時
  額外顯示免責聲明樣式」。
  影響檔案：`Frontend/app.py`（`render_thought_html`、`_apply_step_event`）。

- [ ] **Guardrails 安全審查尚未實作，一律放行**
  `Guardrails/precheck.py` 目前恆回傳 `status="skipped"` + `("result", True)`，
  沒有任何實際的權限／敏感詞審查邏輯，也沒有「攔截後直接回覆拒絕訊息」的分支
  （`Architect.md` 循序圖「安全紅線優先」那條路徑目前無法真正觸發）。README 已
  自陳此為已知限制，但仍是循序圖步驟⑨的核心缺口。

- [ ] **使用者授權子流程（⚠️ 請求批准／✅ 確認）完全沒有程式碼路徑**
  `Trace/step_events.py` 已登錄 `step_key="guardrails_user_authorization"`，但
  全專案搜尋不到任何模組真的 `yield` 過這個事件；`Harness/session.py` 的
  `tool_auth_status` 欄位也從頭到尾沒有被讀寫過。`PermissionError` 目前的處理方式
  是直接判定該次工具呼叫失敗（見 `LLMReasoning/reasoning.py` 的
  `except PermissionError`），並不會真的走「詢問使用者、等待確認」這條路——前端也
  沒有對應的授權對話框 UI。（規格書本身標注「暫不實做」，但既然要做完整功能盤點，
  仍列在此處）

- [ ] **`code_interpreter`、`database_query` 兩個工具是空殼**
  `Backend/adapters/code_interpreter.py`、`Backend/adapters/database_query.py`
  的 `execute()` 直接回傳 `NOT_IMPLEMENTED` 錯誤訊息，沒有沙箱執行環境、沒有資料庫
  連線邏輯。`Tool/catalog.py` 白名單、系統提示詞都已經告訴模型「這兩個工具存在」，
  模型呼叫後只會拿到「工具尚未上線」的降級回覆。

- [ ] **使用者沒有任何管道把檔案放進白名單目錄，`file_read`／`file_write` 形同無米之炊**
  `Backend/config.py` 的 `WHITELISTED_DIRS`（預設 `./workspace`）是 `file_read`／
  `file_write` 唯一能存取的範圍，但 `Frontend/app.py` 完全沒有檔案上傳元件
  （`gr.File`／`gr.UploadButton` 均未使用），使用者無法透過對話介面產生一個
  `file_id` 給這兩個工具用。`Harness.md` §2.2「檔案轉 Markdown」雖標注暫不實作，
  但更根本的問題是：目前系統設計上使用者**沒有任何方式**把本機檔案交給對話流程，
  這兩個工具在實際使用情境下等於打不開。

---

## P1：規格保留了欄位／設計，但尚未串接或只做了一半

- [ ] **多模式系統提示詞（mode）未實作**
  `PreparatoryPhase.md` 設計了 `default`／`coding`／`research`／`safe` 等多套模式
  可切換，但 `Prompt/system_prompt_cache.py` 的 `_PROMPTS` 字典目前**只有
  `"default"` 一組**；`Harness.handle_turn(mode: str = DEFAULT_MODE)` 雖然預留了
  參數，`Frontend/app.py` 卻從未傳入非預設值，UI 上也沒有模式選擇器。等於「多模式」
  這個設計目前只是個沒有第二個選項的參數。

- [ ] **實際串接的是本機 Ollama，不是規格書指定的 DeepSeek-V3**
  `LLMReasoning.md`／`AgentLoop.md` 全篇以 DeepSeek-V3 API
  （`reasoning_effort`／`tool_choice`／`max_reasoning_tokens` 等參數）為藍本，
  但 `LLM/ollama_client.py` 實際呼叫本機 Ollama（預設模型
  `LLM/config.py: OLLAMA_MODEL = "gemma4:26b"`）。`LLMReasoning/config.py` 裡的
  `REASONING_EFFORT`、`MAX_FINAL_TOKENS` 等欄位只是定義好常數，**因為 Ollama 沒有
  對應 API 尚未真正傳給模型**（程式碼註解已自陳）；`confidence_score` 也因此改用
  規則式估算（是否成功＋是否有矛盾），而非規格書設想的模型自報信心值。這是目前
  整個系統與規格書「目標模型」最大的落差，會影響後續任何跟 DeepSeek-V3 專屬能力
  對齊的驗收。

- [ ] **RAG 知識庫沒有匯入介面**
  `Backend/rag/ingest.py` 提供了 `ingest_document()`，但沒有 CLI 工具、管理頁面，
  也沒有接到 Frontend 的檔案上傳自動建庫流程——README 的「已知限制」已提到這點，
  目前只能手動寫 Python 呼叫。`knowledge_base_search` 工具因此在一個全新環境裡
  永遠回傳「無相關結果」（collection 不存在）。

- [ ] **讚／踩回饋沒有任何持久化**
  `Frontend/app.py` 的 `on_like`／`on_copy` 只 `print()` 到 console，沒有寫入
  log 檔、資料庫或任何可回收分析的管道。UI 互動（按鈕變色）都做了，但資料本身
  即用即丟，無法用於後續模型/提示詞調校。

- [ ] **多工具「同時發起」與「換工具重試」未落地**
  `ToolCalling.md` §4.2 提到可以在同一輪同時發起多個 `tool_calls`，§7 提到失敗後
  允許模型撤回、重新選擇其他工具（上限 3 次）。目前 `LLMReasoning/reasoning.py`
  對多個 `tool_calls` 是**逐一序列執行**（`for index, call in enumerate(tool_calls)`），
  並沒有真正的並行處理；失敗後也沒有「换一個工具再試」的邏輯，只有白名單/型態驗證
  失敗時才會要求模型重新生成（§6 的重試，這部分已實作）。（這兩點規格書本身也標注
  「暫不實做」，僅供完整盤點）

---

## P2：技術債／文件化的已知限制

- [ ] **完全沒有自動化測試**
  專案 66 個檔案中沒有任何 `test_*.py`／`*_test.py`。9 份規格書都各自定義了明確的
  「測試驗證點／驗收標準」章節（例如 `ThoughtPanelStep.md` §11 共 9 條、
  `FrontendUIUX.md` §7 共 5 條），但目前沒有任何機制能驗證這些驗收標準是否持續
  成立，全靠人工測試。

- [ ] **稽核日誌（audit log）實際上沒有任何輸出目的地**
  `PreparatoryPhase.md` §7、`Harness/payload.py`、`LLMReasoning/reasoning.py`
  都呼叫了 `logging.getLogger("audit.system_prompt")`／`"audit.agent_loop")`
  記錄稽核資訊，但**整個專案沒有任何一處呼叫 `logging.basicConfig()` 或設定
  handler**（已確認 grep 不到 `basicConfig`／`addHandler`／`FileHandler`）。
  Python 的 root logger 預設層級是 WARNING，這些 `logger.info(...)` 呼叫在
  目前的部署方式下實際上會被靜默丟棄，等於規格書要求的稽核軌跡目前並不存在，
  只是「呼叫了 logging API」而已。

- [ ] **Session 僅行程內記憶體，重啟即全部遺失**
  `Harness/session.py` 的 `SessionStore` 是純 in-memory dict。規格書允許
  Redis／Memory 兩種選項，目前選擇了較簡單的一種——這是程式碼註解已言明的刻意
  取捨而非疏漏，但列出以利評估是否需要在多使用者／需要重啟不中斷對話的場景下
  升級。

---

## 附註：以下規格條文經確認「已完整實作」，不列入 TODO

- ①～⑰ 步驟化即時串流思考區（`Trace/`、`Harness/harness.py`、
  `Backend/pipeline.py`、`LLMReasoning/reasoning.py`／`agent_loop.py`、
  `Frontend/app.py`）。
- Session 管理（Header/Body 解析、UUID 產生、30 分鐘 TTL、歷史壓縮）。
- System Prompt 準備階段（`{{current_date}}` 佔位符替換、`Fallback` 降級、
  §6 大小截斷）。
- 純文字輸入前處理（編碼標準化、控制字元過濾、空白壓縮、頭尾雙向截斷）。
- 工具白名單／JSON Schema 驗證與 §6 重試機制（`Tool/`）。
- 工具執行管道（HTTP 30s／本地 60s 逾時、白名單目錄、頭尾截斷、
  檔案摘要規則、來源標記）：`web_search`（DuckDuckGo）、`file_read`、
  `file_write`、`http_request`、`knowledge_base_search`（BGE-M3 +
  Qdrant，embedded 模式）。
- 第二輪推理 Agent Loop（上下文重組、矛盾偵測、時效性檢查、
  confidence_score／cited_sources／reasoning_summary 計算——僅前端顯示
  這一步未接上，見 P0 第一項）。
- 對話框複製／讚／踩 UI（`gr.Chatbot` 原生按鈕，取代規格書建議的手刻 JS 注入，
  屬等價實作方式的差異，非功能缺口）。