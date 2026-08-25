# AI_ChatBot

具備 **透明思考鏈（Chain-of-Thought）** 的本機 Agent 聊天機器人。以 Gradio 打造左右雙欄介面：左側是一般對話，右側即時、逐步顯示 AI 的推理過程；後端串接本機 [Ollama](https://ollama.com/)（gemma4 系列模型），並具備工具呼叫（網路搜尋、RAG 知識庫檢索、程式碼執行等）與「第二輪推理（Agent Loop）」——把工具結果與初始思考草稿融合，產生附信心分數與引用來源的最終回答。

整個專案採「先寫規格書、再實作」的開發方式：`Architect/` 資料夾內有 9 份規格書，逐一對應下方循序圖中的每一個步驟；`AGENTS.md` 則定義了程式碼撰寫的共同原則。

## 特色

- **透明思考鏈 UI**：右側思考區以步驟化事件（`Trace.StepEvent`）即時串流顯示 Harness／LLMReasoning 內部各步驟的進度，而非等到生成完畢才一次跳出。
- **Agent Loop（第二輪推理）**：模型呼叫工具後，會將工具回傳結果與第一輪的思考草稿重新送入模型，做語意校準與衝突偵測，最終產生 `final_answer`、`confidence_score`（信心分數 < 0.6 時建議顯示免責聲明）、`cited_sources` 等結構化輸出。
- **7 種內建工具**：`web_search`、`file_read`、`code_interpreter`、`database_query`、`file_write`、`http_request`、`knowledge_base_search`，皆以 JSON Schema 定義於 `Tool/catalog.py`，是系統提示詞與參數驗證的唯一資料來源。
- **RAG 知識庫檢索**：BGE-M3 embedding（透過本機 Ollama `/api/embed`）+ Qdrant 向量資料庫（embedded 本地模式，資料寫在本機磁碟，不需另外起 Qdrant 服務或 Docker）。
- **免金鑰網路搜尋**：透過 `ddgs` 套件呼叫 DuckDuckGo，不需申請 API Key。
- **安全守衛（Guardrails）**：預留 pre-execution hook 架構（步驟⑨），目前為最小可用 stub——一律放行，但仍會誠實地在思考區顯示「尚未審查」的狀態。

## 專案結構

```
AI_ChatBot/
├── main.py              進入點：啟動 Gradio 伺服器（預設 http://127.0.0.1:7860）
├── requirements.txt      套件相依清單
├── AGENTS.md             開發原則（模組化、簡單優先、不做向下相容等）
├── diagram.png           架構循序圖（渲染版）
├── Architect/            規格書：對應循序圖每個步驟的詳細設計文件
│   ├── Architect.md          循序圖總覽
│   ├── PreparatoryPhase.md   準備階段：系統提示詞注入（步驟③④）
│   ├── Harness.md             核心調度：輸入前處理與請求建構（步驟①～⑥）
│   ├── LLMReasoning.md        LLM 推理與工具呼叫判斷（步驟⑤⑥⑦）
│   ├── ToolCalling.md         工具調用判斷模組（步驟⑦）
│   ├── ToolExecution.md       工具執行與結果處理（步驟⑩～⑬）
│   ├── AgentLoop.md           第二輪推理機制（步驟⑭～⑰）
│   ├── FrontendUIUX.md        前端 UI/UX 規格
│   └── ThoughtPanelStep.md    思考區步驟化即時串流規格
├── Frontend/             Gradio UI：左右雙欄、步驟化思考區、複製/讚/踩按鈕
│   └── app.py
├── Harness/              核心調度器：Session 管理、輸入前處理、Payload 組裝
├── Prompt/               系統提示詞快取（角色 / 工具定義 / 安全紅線 / 當前日期）
├── LLM/                  串接本機 Ollama `/api/chat`（gemma4:26b模型），逐段串流輸出
├── LLMReasoning/         判斷是否需呼叫工具、驅動 Agent Loop 第二輪推理
├── Tool/                 工具白名單與 JSON Schema 定義、參數驗證
├── Backend/              工具執行管道
│   ├── adapters/             各工具的執行 adapter（web_search、file_read、code_interpreter…）
│   ├── rag/                  RAG 子系統：BGE-M3 embedding + Qdrant 向量檢索
│   └── websearch/             DuckDuckGo 網路搜尋（ddgs）
├── Guardrails/           安全守衛 pre-execution hook（目前為 stub，一律放行）
└── Trace/                思考區步驟事件（StepEvent）共用資料結構
```

## 系統需求

- Python 3（依 `.venv` 建置）
- 已安裝並啟動 [Ollama](https://ollama.com/)，且已拉取以下模型：

  ```bash
  ollama pull gemma4:26b   # 對話模型（可依 LLM_OLLAMA_MODEL 換成其他 gemma 系列 tag）
  ollama pull bge-m3         # Embedding 模型（RAG 知識庫檢索功能需要）
  ```

## 安裝

```bash
git clone <本專案 repo>
cd AI_ChatBot

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

主要相依套件（詳見 `requirements.txt`）：

| 套件 | 用途 |
| --- | --- |
| `gradio` | 前端 Web UI 框架 |
| `httpx` | 呼叫 Ollama `/api/chat`、`/api/embed` 的 HTTP 用戶端 |
| `qdrant-client` | RAG 向量資料庫（embedded 本地模式） |
| `ddgs` | DuckDuckGo 網路搜尋 |

## 執行

先確認 Ollama 服務正在執行（`ollama serve`，或執行 `ollama run <model>` 時會自動在背景啟動），接著：

```bash
python main.py
```

預設會在 `http://127.0.0.1:7860` 開啟網站。

## 環境變數

以下環境變數皆為選填，未設定時使用程式內建的預設值。

| 變數 | 預設值 | 說明 |
| --- | --- | --- |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama 服務位址 |
| `LLM_OLLAMA_MODEL` | `gemma4:26b` | 對話所使用的 Ollama 模型 tag |
| `BACKEND_FILE_WHITELIST_DIRS` | `./workspace` | 本地檔案 I/O 工具允許存取的白名單目錄（多個以 `os.pathsep` 分隔） |
| `RAG_QDRANT_STORAGE_PATH` | `./Backend/rag/.qdrant_data` | Qdrant 向量資料庫的本地儲存目錄 |
| `RAG_DEFAULT_COLLECTION` | `knowledge_base` | 預設檢索的知識庫集合名稱 |
| `RAG_EMBEDDING_MODEL` | `bge-m3` | Embedding 使用的 Ollama 模型 |
| `RAG_DEFAULT_TOP_K` | `5` | 知識庫檢索預設回傳筆數 |
| `RAG_SCORE_THRESHOLD` | `0.0` | 檢索結果的相似度分數門檻（0 = 不過濾） |
| `RAG_CHUNK_SIZE_CHARS` / `RAG_CHUNK_OVERLAP_CHARS` | `500` / `50` | 建置知識庫時的切塊大小與重疊字元數 |
| `WEBSEARCH_TIMEOUT_SECONDS` | `30` | DuckDuckGo 搜尋逾時秒數 |
| `WEBSEARCH_DEFAULT_REGION` | `wt-wt` | 搜尋預設地區（如 `tw-tzh` 為台灣繁中） |

## 內建工具一覽

| 工具 | 觸發時機 |
| --- | --- |
| `web_search` | 問題涉及即時資訊、新聞、天氣、股價等模型內建知識無法回答的事實 |
| `knowledge_base_search` | 需要根據已匯入知識庫做語意（向量）相似度檢索 |
| `file_read` | 讀取使用者已上傳檔案的特定段落 / 統計數據 |
| `file_write` | 產生報告、修改檔案內容、匯出結果 |
| `code_interpreter` | 執行程式碼以進行計算、數據分析或繪圖 |
| `database_query` | 查詢結構化資料庫（SQL 或自然語言查詢） |
| `http_request` | 呼叫第三方 API（如天氣、翻譯） |

## 現況與已知限制

- **Guardrails 尚未實作**：`Guardrails/precheck.py` 目前一律放行工具呼叫，真正的權限／敏感詞審查邏輯尚待開發。
- **RAG 知識庫建置**：`Backend/rag/ingest.py` 提供切塊與寫入 Qdrant 的功能，但目前尚無專屬的匯入介面／CLI，需自行呼叫。
