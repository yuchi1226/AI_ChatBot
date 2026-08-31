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

- [✓] **Guardrails 安全審查尚未實作，一律放行**（已修復：`Guardrails/rules.py`
  新增規則式（關鍵字/正則）審查——敏感詞分類黑名單、`database_query` 寫入型
  SQL 攔截、`http_request` SSRF 網址攔截、`code_interpreter` 高風險程式碼樣式
  攔截；`Guardrails/llm_judge.py` 新增規則放行後的 LLM 二次複核，呼叫本機
  Ollama 抓換句話說/委婉包裝手法，逾時或解析失敗時優雅降級為維持規則式結論；
  `Guardrails/precheck.py` 改為逐一審查每個 `tool_call`，攔截粒度是單一
  `tool_call` 而非整輪；`LLMReasoning/reasoning.py` 步驟⑨之後的迴圈改為讀取
  攔截結果，被攔截的 `tool_call` 比照既有 `PermissionError` 分支合成拒絕結果
  （不呼叫 `Backend.execute_tool`），其餘照常執行，等同循序圖「不調用任何
  工具，直接回覆拒絕訊息」的效果。新增 `Tests/test_guardrails_rules.py`／
  `test_guardrails_llm_judge.py`／`test_guardrails_precheck.py` 涵蓋放行/攔截
  案例。使用者授權子流程（⚠️請求批准／✅確認）維持 stub，不在此次範圍內，
  見下一條目。）

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

**一、相同問題是否需要每次重新搜尋**

目前答案是「會」。`Backend/websearch/client.py` 的 `search()` 每次都直接呼叫 `ddgs.text()`，`Backend/adapters/http_request.py` 也是每次都用 `httpx.request()` 現打，兩者都沒有任何結果儲存層——同一個 session 裡問兩次一樣的問題，或不同 session 問同一個問題，都會重新打一次 DuckDuckGo／目標網站。

不需要每次都重搜。建議加一層「查詢層快取」，做法上跟你現有風格一致（`Backend/websearch/config.py` + `client.py` 的分離模式）：

- key 用正規化過的 `(query, region, time_range)`，同一個問題不同大小寫/前後空白要視為同一筆。
- TTL 而非永久快取，因為網路內容會變；先用單一環境變數（如 `WEBSEARCH_CACHE_TTL_SECONDS`）起步，不用一開始就分「新聞類短 TTL、事實類長 TTL」，符合 `AGENTS.md`「選最簡單、完全滿足目前需求的實作」。
- 儲存位置：比照 `Harness/session.py` 的 `SessionStore`（行程內記憶體 dict + lock）即可起步；如果要跨重啟保留（例如常見問題重啟後也不用重搜），比照 `Backend/rag/vector_store.py` 用 Qdrant embedded 磁碟模式的邏輯，改用 stdlib 的 sqlite 落地，不用引入 Redis——你的部署本來就是單一 Gradio 行程，沒有多實例同步的需求。

**二、同一個網站的同一份內容能否用結果識別避免重複查詢**

這其實是兩層不同的快取，值得分開看：

第一層是上面講的「查詢快取」——避免同一個 query 重打。第二層是「內容層快取」，針對 `http_request` 這種直接打 URL 的工具（模型可能先 `web_search` 拿到連結，再用 `http_request` 抓全文），現在完全沒有：

- 條件式請求：對支援的網站存 `ETag`／`Last-Modified`，下次帶 `If-None-Match`／`If-Modified-Since`，對方回 304 就不用重傳內容——省頻寬，但仍要打一次網路。
- 內容雜湊：對回應內容算 sha256，存 `{url: (hash, content, fetched_at)}`。TTL 內直接命中快取、連網路都不用打；就算 TTL 過了要重抓，雜湊沒變也能讓下游（例如要不要重新丟給 LLM、要不要重新 embedding）知道「內容其實沒變」。
- 跨 URL 去重：不同網址內容相同（轉載新聞、AMP 版本、鏡像站）時，用內容雜湊而非 URL 當識別鍵，可以避免同一份內容被當成好幾筆不同資料餵給模型，浪費 context。

這層邏輯可以放在一個共用的 `Backend/http_cache.py`，讓 `http_request` adapter 和未來如果要做「抓網頁全文」的功能共用，介面上不用動 `Backend/adapters/http_request.py` 對外的呼叫方式。

**三、本地資料量過大時的篩選／摘要／分層／檢索**

你其實已經有「檢索」這一層了：`Backend/rag/ingest.py` 固定字元切塊（500/50）+ `Backend/rag/vector_store.py` 向量 top-k 檢索，這就是標準 RAG 做法。但有幾個現成的旋鈕沒轉，加上幾個還沒做的層次：

- 篩選：`RAG_SCORE_THRESHOLD` 預設是 `0.0`（不過濾），代表知識庫變大之後，低相關的雜訊 chunk 一樣會被塞進 LLM 的 context，浪費 token 又可能誤導答案。這是最便宜的第一步——先把門檻調到一個非零值。另外 Qdrant 支援 payload filter（依 `metadata["source"]`、日期等先篩再算相似度），資料量大了之後比單純調高 `top_k` 更省。
- 摘要：現在 `Architect/ToolExecution.md` §「內容截斷」是頭尾截斷（`...資料過長已縮減`），`file_read` 對超長檔案是回傳前 100 行——這兩個都是「砍掉中間」而非「摘要」，資訊會遺失。既然你已經有 Agent Loop 的第二輪推理（`LLMReasoning/agent_loop.py`），可以在超過某個長度門檻時，讓那一輪順便做摘要而不是單純截斷，但這要多一次本地 Ollama 呼叫，等於用延遲換品質，建議只在明顯超長時才觸發，不要每次都做。
- 分層：兩段式檢索是常見做法——先用較大的 `top_k` 做便宜的粗篩，再做一次精篩（rerank 或直接讓 LLM 自己判斷相關性，你的 agent loop 已經有「矛盾偵測」「時效性檢查」的雛形，某種程度上已經在做這件事）。如果知識庫繼續長大，也可以考慮把常用/新資料放進一個較小的「熱」collection 先查，查不到才 fallback 到完整 collection，減少每次查詢都要掃全部向量的成本。
- 檢索/建置面的去重：`ingest_document()` 目前沒有防止同一份內容被重複 ingest 兩次（例如使用者上傳同一份文件兩次，或不同來源其實是同一段文字）。可以在切塊後、embedding 前先算內容雜湊，Qdrant 裡已存在同雜湊就跳過——同時省了 embedding 呼叫（本地 Ollama 算 embedding 也是要吃運算資源的）和儲存空間。
- 這個「資料太大」的問題其實也發生在對話歷史上：`Harness/session.py` 的壓縮策略是「超過 `MAX_HISTORY_MESSAGES` 則數就砍最舊的」，是很粗的分層（按則數而非按 token 預算，砍掉的內容也是直接消失、沒有摘要保留）。之後如果對話變長、User 抱怨「AI 忘記前面說過的」，這裡會是下一個要處理的點。

**優先順序建議**：照 `AGENTS.md`「先做最小可行、逐層長」的原則，我會先做這三件事再看效果：(1) 把 `RAG_SCORE_THRESHOLD` 開起來、(2) 幫 `web_search`／`http_request` 加一個簡單的 TTL 記憶體快取、(3) ingest 時加內容雜湊去重。語意快取（用 embedding 判斷「問法不同但意思相同」算命中）、cross-encoder rerank、多層 collection 這些，等你實際觀察到成本/延遲痛點再做，現在做屬於投機性抽象。

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