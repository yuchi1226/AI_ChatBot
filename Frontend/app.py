# -*- coding: utf-8 -*-
"""
Frontend/app.py
----------------
左右雙欄 AI 對話網站 (Gradio 實作，後端串接 LLMReasoning/ 模組呼叫本機 Ollama)

Architect/ThoughtPanelStep.md §6.1、§7：思考區改為「步驟化即時串流」呈現，
依 Architect/Architect.md 循序圖①～⑰逐步顯示 Harness／LLMReasoning 發射的
Trace.StepEvent，取代舊版把 thought_chunk 累加成單一長文字的做法。
"""

import html
import os
import sys

import gradio as gr

# 確保專案根目錄（AI_ChatBot/）在 sys.path 上，這樣不論是透過 main.py
# 啟動，還是直接 `python Frontend/app.py` 執行，都能 `import Harness`。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import Harness
import LLMReasoning
from Trace.step_events import MIRRORS_TO_CHAT, circled_step_no, make_step_event


# ----------------------------------------------------------------------------
# 樣式 (CSS) - 經過重新設計與高度對齊
# ----------------------------------------------------------------------------
CUSTOM_CSS = """
/* ================================================================
   整體視覺
   ================================================================ */
.gradio-container {
    max-width: 1440px !important;
    width: min(1440px, calc(100vw - 40px)) !important;
    margin: 0 auto !important;
    padding: 28px 20px 36px !important;
    box-sizing: border-box;
}

body {
    background: var(--background-fill-primary);
}

#app_header {
    margin: 0 0 18px 0;
    padding: 4px 2px 0;
}

#app_title {
    margin: 0 !important;
    font-size: 28px !important;
    line-height: 1.2 !important;
    font-weight: 750 !important;
    letter-spacing: -0.02em;
}

#app_subtitle {
    margin-top: 7px !important;
    color: var(--body-text-color-subdued) !important;
    font-size: 14px !important;
}

/* ================================================================
   主畫面：左右欄採固定 grid，比 scale 更穩定
   左右欄永遠各自佔滿相同的整體高度
   ================================================================ */
#main_layout {
    display: grid !important;
    grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr) !important;
    gap: 18px !important;
    align-items: stretch !important;
    height: 720px !important;
    min-height: 720px !important;
    max-height: 720px !important;
    margin: 0 !important;
    /* 保護整體版面：不管內層（聊天訊息／思考內容）長出什麼奇怪的寬高，
       都不允許撐破這個 720px 的格線容器，避免把輸入框、範例按鈕擠到
       別的欄位去。內層真正需要捲動的地方各自有自己的 overflow-y:auto。 */
    overflow: hidden !important;
}

#main_layout > .gr-column {
    min-width: 0 !important;
    width: auto !important;
    height: 100% !important;
    max-height: 100% !important;
    min-height: 0 !important;
    display: flex !important;
    flex-direction: column !important;
    overflow: hidden !important;
}

#left_panel,
#right_panel {
    min-width: 0 !important;
    min-height: 0 !important;
    height: 100% !important;
    max-height: 100% !important;
    box-sizing: border-box !important;
    /* 真正的破圖成因：Gradio 的 Column 元件（.column class）本身預設
       flex-wrap 是 wrap。平常這是為了讓 Column 在螢幕太窄時能自動換行，
       但這裡是 flex-direction:column，wrap 的方向是「換到旁邊那一欄」
       （cross axis 是水平的）。當第一個子元素（聊天框）回答完後，內容
       實際需要的高度超過欄位可用的 720px，瀏覽器在做 wrap 判斷時，會先
       用「還沒套用 flex-shrink 之前」的原始內容高度去判斷要不要換行，
       發現放不下就把聊天框自己獨立算成第一欄，接著把輸入框、範例問題
       按鈕擠成「第二欄」，畫面上就變成疊在思考欄前面、被推到右邊。
       用 flex-wrap: nowrap 強制鎖成單一欄，聊天框才會真的被同一欄裡的
       輸入框、範例問題按鈕擠壓、乖乖用 min-height:0 縮小，而不是整個
       跑去開新的一欄。 */
    flex-wrap: nowrap !important;
    /* 同上：左／右欄本身也要裁切，這樣即使 gr.Chatbot 內部元件的高度／
       寬度計算跑掉，也只會被裁掉多出來的部分，不會把同一欄後面的
       輸入框、範例問題按鈕，或旁邊的思考欄推擠變形。 */
    overflow: hidden !important;
}

#left_panel {
    display: flex !important;
    flex-direction: column !important;
}

#right_panel {
    display: flex !important;
    flex-direction: column !important;
}

/* ================================================================
   聊天框：固定佔滿左欄剩餘高度，不被輸入區擠壓
   ================================================================ */
#chatbot_main {
    flex: 1 1 auto !important;
    min-width: 0 !important;
    min-height: 0 !important;
    height: 100% !important;
    max-height: 100% !important;
    width: 100% !important;
    max-width: 100% !important;
    /* Gradio Chatbot 內部用 position:absolute 的包裹層把訊息區塊撐滿父層，
       這裡明確給 position:relative 當作那層 absolute 的定位基準，避免它
       找不到夠近的定位祖先、跑去撐滿更外層的容器，把版面撐壞。 */
    position: relative !important;
    border-radius: 16px !important;
    border: 1px solid var(--border-color-primary) !important;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.055) !important;
    overflow: hidden !important;
    background: var(--background-fill-primary) !important;
}

/* Gradio Chatbot 內部的訊息捲動容器（.panel-wrap / .bubble-wrap）：明確
   鎖死高度並交出捲動權，不讓訊息（尤其是回答完後突然變長的那一則）把
   #chatbot_main 的外框撐大，進而擠壓同一欄的輸入框／範例問題按鈕，或
   把版面推到右側思考欄去。 */
#chatbot_main > div,
#chatbot_main .wrap,
#chatbot_main .panel-wrap,
#chatbot_main .bubble-wrap {
    min-width: 0 !important;
    min-height: 0 !important;
    max-width: 100% !important;
    height: 100% !important;
    max-height: 100% !important;
}

#chatbot_main .panel-wrap,
#chatbot_main .bubble-wrap {
    overflow-y: auto !important;
    overflow-x: hidden !important;
}

#chatbot_main .message {
    line-height: 1.7 !important;
}

/* 訊息內文若出現一長串不會換行的文字（網址、程式碼、hash 等），也不能
   撐開整欄的寬度，一律強制換行並限制在欄寬內。 */
#chatbot_main .message-wrap,
#chatbot_main .message,
#chatbot_main pre,
#chatbot_main code {
    min-width: 0 !important;
    max-width: 100% !important;
    overflow-wrap: anywhere !important;
}

#chatbot_main pre {
    overflow-x: auto !important;
}

/* ================================================================
   右側思考區：直接填滿整個右欄，因此與左欄總高度一致
   ================================================================ */
#thought_panel {
    flex: 1 1 auto !important;
    min-height: 0 !important;
    height: 100% !important;
    width: 100% !important;
    overflow: hidden !important;
    box-sizing: border-box !important;
    border: 1px solid var(--border-color-primary) !important;
    border-radius: 16px !important;
    background: var(--background-fill-secondary) !important;
    padding: 0 !important;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.045) !important;
}

.thought-scroll-inner {
    /* 這裡故意不設 overflow-y:auto——真正負責捲動的是 Gradio HTML 元件
       自己的 .html-container（由 gr.HTML(min_height="100%", max_height=
       "100%", autoscroll=True) 這幾個參數驅動，見下方 build_demo()）。
       這一層維持 height:100%（讓 .thought-empty 的置中效果在內容還很短
       時仍然生效），內容一旦變長，會自然撐出這個 100% 的框，交給外層
       .html-container 的 overflow-y:auto 去捲動——Gradio 內建的
       autoscroll 邏輯也是往上找「最近一個 overflow:auto/scroll 的祖先」
       來捲動，如果這裡自己開一個獨立的捲動區，Gradio 反而會找不到真正
       在捲動的地方，導致捲不動或抓不到底部。 */
    width: 100%;
    height: 100%;
    padding: 22px;
    box-sizing: border-box;
    font-size: 14px;
    line-height: 1.75;
    font-family: 'Cascadia Mono', 'SFMono-Regular', Consolas, monospace;
    white-space: normal;
    word-break: break-word;
    overflow-wrap: anywhere;
}

.thought-empty {
    color: var(--body-text-color-subdued);
    font-style: italic;
    display: flex;
    justify-content: center;
    align-items: center;
    text-align: center;
    height: 100%;
    padding: 24px;
    box-sizing: border-box;
}

/* ================================================================
   思考區：步驟化區塊樣式（Architect/ThoughtPanelStep.md §7）
   ================================================================ */
.thought-step {
    margin-bottom: 4px;
    padding: 10px 12px;
    border-radius: 10px;
    border: 1px solid var(--border-color-primary);
    background: var(--background-fill-primary);
}

.thought-step-title {
    font-weight: 700;
    margin-bottom: 4px;
}

.thought-step-body {
    white-space: normal;
    word-break: break-word;
    overflow-wrap: anywhere;
    color: var(--body-text-color);
}

.thought-cursor {
    display: inline-block;
    animation: thought-blink 1s steps(1) infinite;
}

@keyframes thought-blink {
    50% { opacity: 0; }
}

.thought-step-running {
    border-color: var(--primary-500);
}

.thought-step-error {
    border-color: #e05252;
    background: rgba(224, 82, 82, 0.08);
}

.thought-step-skipped {
    opacity: 0.6;
}

.thought-step-divider {
    text-align: center;
    color: var(--body-text-color-subdued);
    font-size: 12px;
    margin: 2px 0 8px;
}

.thought-complete {
    text-align: center;
    font-weight: 700;
    color: var(--body-text-color-subdued);
    padding: 10px 0 4px;
}

/* ================================================================
   輸入區：固定在左欄底部，不改變左欄寬度
   ================================================================ */
.input-group {
    flex: 0 0 auto !important;
    width: 100% !important;
    box-sizing: border-box !important;
    margin-top: 14px !important;
    padding: 5px !important;
    border-radius: 14px !important;
    border: 1px solid var(--border-color-primary) !important;
    background: var(--background-fill-primary) !important;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.05) !important;
}

.input-group > .gr-row {
    width: 100% !important;
    margin: 0 !important;
}

.input-group textarea,
.input-group textarea:focus {
    border: none !important;
    box-shadow: none !important;
    min-height: 48px !important;
}

#send_btn {
    min-width: 52px !important;
    height: 48px !important;
    border: 0 !important;
    border-radius: 10px !important;
    background: var(--primary-600) !important;
    color: white !important;
    font-size: 20px !important;
    font-weight: 700 !important;
    transition: transform .15s ease, filter .15s ease, opacity .15s ease;
}

#send_btn:hover {
    filter: brightness(0.96);
    transform: translateY(-1px);
}

#send_btn:active {
    transform: translateY(0);
}

/* ================================================================
   範例問題：寬度由 grid 決定，按鈕不會把欄位撐變形
   ================================================================ */
#example-row {
    flex: 0 0 auto !important;
    width: 100% !important;
    margin-top: 12px !important;
    display: grid !important;
    grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
    gap: 8px !important;
}

#example-row button {
    width: 100% !important;
    min-width: 0 !important;
    min-height: 42px !important;
    white-space: normal !important;
    overflow-wrap: anywhere !important;
    border-radius: 12px !important;
    padding: 7px 12px !important;
    border: 1px solid var(--border-color-primary) !important;
    background: var(--background-fill-secondary) !important;
    transition: all .15s ease;
}

#example-row button:hover {
    border-color: var(--primary-500) !important;
    transform: translateY(-1px);
}

/* ================================================================
   第二個 Tab：說明內容
   ================================================================ */
#about_panel {
    max-width: 2000px;
    width: 100%;
    margin: 0 auto;
}

/* ================================================================
   RWD：窄螢幕改成上下排列，避免左右欄被壓縮變形
   ================================================================ */
@media (max-width: 900px) {
    .gradio-container {
        width: min(100vw - 24px, 720px) !important;
        padding: 20px 12px 28px !important;
    }

    #main_layout {
        grid-template-columns: 1fr !important;
        height: auto !important;
        min-height: 0 !important;
    }

    #left_panel,
    #right_panel {
        height: auto !important;
        min-height: 0 !important;
    }

    #chatbot_main {
        height: 560px !important;
        flex: none !important;
    }

    #thought_panel {
        height: 420px !important;
        min-height: 420px !important;
        flex: none !important;
    }

    #example-row {
        grid-template-columns: 1fr !important;
    }
}
"""

# ----------------------------------------------------------------------------
# 前端 JavaScript
# ----------------------------------------------------------------------------
# 原本這裡自己刻了一套 MutationObserver 去監控 #thought_panel、手動記錄
# 捲動位置、模擬「黏底」效果。拆掉的原因：實際測試發現完全不會動、
# 也滑不動——追下去才發現 Gradio 的 gr.HTML 元件本身就有 autoscroll 參數
# （見 build_demo() 裡 thought_html = gr.HTML(...) 那段），而且 Gradio
# 自己的實作方式是「往上找最近一個 overflow:auto/scroll 的祖先」來捲動；
# 我們之前塞給 .thought-scroll-inner 的 overflow-y:auto 反而讓真正在捲動
# 的地方變成一個 Gradio 找不到的內層節點，導致內建的 autoscroll 抓不到、
# 我們自己刻的那套也因為節點被整個置換而亂掉——兩套邏輯互相打架。
# 現在直接交給 Gradio 內建機制處理，不需要任何自訂 JS，也不用維護一份
# 容易在節點置換時出錯的手刻捲動邏輯。
HEAD_JS = ""

# ----------------------------------------------------------------------------
# Helper：思考區步驟化渲染（Architect/ThoughtPanelStep.md §6.1、§7）
# ----------------------------------------------------------------------------
# 同一 step_no 收到多次 StepEvent 時，前端把每次的 delta 疊加成完整內容，
# 而不是只顯示最後一次的增量——這裡用一個以 step_no 為鍵的 dict（Python
# 3.7+ 字典保序，天然符合「依 step_no 遞增顯示」的需求）累積每一格的畫面
# 狀態，跟 Trace.StepEvent 本身（只帶「這一次的增量」）分開。
_MULTI_CALL_STEPS = {9, 10, 11, 12, 13}  # 步驟⑨～⑬：同輪多個工具呼叫時會重複出現，
# 用 tool_call_id 分隔不同工具的內容，避免混在一起分不清楚（見
# Guardrails/precheck.py：步驟⑨現在每個 tool_call 會發射多則 StepEvent
# 呈現完整審查過程，這裡讓多個工具呼叫的過程彼此分開顯示）。


def _apply_step_event(step_views: dict, event) -> None:
    """把一個 Trace.StepEvent 疊加進 step_views（key=step_no）。"""
    view = step_views.get(event.step_no)
    if view is None:
        view = {"step_no": event.step_no, "content": "", "meta": {}, "_last_tool_call_id": None}
        step_views[event.step_no] = view

    view["step_key"] = event.step_key
    view["title"] = event.title
    view["status"] = event.status

    delta = event.delta or ""
    if delta:
        tool_call_id = (event.meta or {}).get("tool_call_id")
        # 步驟⑩～⑬同輪呼叫多個工具時共用同一格，用分隔線標示不同的
        # tool_call_id，避免多個工具的內容混在一起分不清楚（見
        # Architect/ThoughtPanelStep.md §5：「⑨～⑬會依工具數量重複出現…
        # 前端渲染時以子區塊列出，仍計為一組⑨～⑬」）。
        if (
            event.step_no in _MULTI_CALL_STEPS
            and tool_call_id
            and tool_call_id != view["_last_tool_call_id"]
        ):
            delta = (f"\n\n── {tool_call_id} ──\n{delta}" if view["content"] else f"── {tool_call_id} ──\n{delta}")
            view["_last_tool_call_id"] = tool_call_id
        view["content"] += delta

    if event.meta:
        view["meta"] = event.meta


_STATUS_PREFIX = {"error": "⚠️ ", "skipped": "⏭️ "}


def render_thought_html(step_views: dict = None, stream_ended: bool = False) -> str:
    """
    依 step_no 由小到大渲染每個步驟區塊，格式對齊
    Architect/ThoughtPanelStep.md 範例：①標題 / 內容 / ▼。
    """
    if not step_views:
        inner = '<span class="thought-empty">等待思考過程…</span>'
        return f'<div class="thought-scroll-inner">{inner}</div>'

    blocks = []
    for step_no in sorted(step_views.keys()):
        view = step_views[step_no]
        status = view.get("status", "running")
        status_class = f"thought-step thought-step-{status}"
        prefix = _STATUS_PREFIX.get(status, "")
        title = html.escape(f"{circled_step_no(step_no)} {prefix}{view.get('title', '')}")
        body = html.escape(view.get("content", "")).replace("\n", "<br>")
        cursor = '<span class="thought-cursor">▍</span>' if status == "running" else ""
        blocks.append(
            f'<div class="{status_class}">'
            f'<div class="thought-step-title">{title}</div>'
            f'<div class="thought-step-body">{body}{cursor}</div>'
            f"</div>"
            '<div class="thought-step-divider">▼</div>'
        )
    if stream_ended:
        blocks.append('<div class="thought-complete">【思考流程完成】</div>')
    return '<div class="thought-scroll-inner">' + "".join(blocks) + "</div>"


def _extract_text(content) -> str:
    if isinstance(content, str): return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return "" if content is None else str(content)

EXAMPLE_QUESTIONS = [
    "今天天氣如何？適合出門嗎？",
    "可以簡單介紹一下 Gradio 嗎？",
    "為什麼很多 AI 工具都用 Python 開發？",
]

# ----------------------------------------------------------------------------
# 對話邏輯
# ----------------------------------------------------------------------------
def user_submit(user_message, history):
    user_message = (user_message or "").strip()
    if not user_message:
        return history, "", render_thought_html()
    history = history + [{"role": "user", "content": user_message}]
    return history, "", render_thought_html()

def disable_inputs():
    """同時停用輸入框與發送按鈕"""
    return gr.update(interactive=False), gr.update(interactive=False)

def bot_response(history, session_id):
    if not history or history[-1]["role"] != "user":
        # 如果無效，立刻重新啟用輸入元件
        yield history, render_thought_html(), gr.update(interactive=True), gr.update(interactive=True), session_id
        return

    user_message = _extract_text(history[-1]["content"])
    # step_views：本輪思考區的步驟狀態（key=step_no），只在這次 bot_response()
    # 呼叫的生命週期內存在，不需要額外的 gr.State（跟舊版 thought_acc／
    # response_acc 區域變數同樣的做法）。
    step_views: dict = {}

    def _current_html(ended: bool = False) -> str:
        return render_thought_html(step_views, stream_ended=ended)

    # 步驟①：輸入提問＋上下文（前端本來就知道使用者問了什麼，不需要等後端）。
    _apply_step_event(
        step_views,
        make_step_event("receive_input", status="success", delta=user_message),
    )
    yield history, _current_html(), gr.update(interactive=False), gr.update(interactive=False), session_id

    # ---- Harness 步驟②～④：Session 管理、前處理、System Prompt 拉取 ----
    request_payload = None
    try:
        for event, data in Harness.handle_turn(user_message, session_id=session_id):
            if event == "step":
                _apply_step_event(step_views, data)
                yield history, _current_html(), gr.update(interactive=False), gr.update(interactive=False), session_id
            elif event == "result":
                session_id, request_payload = data
    except Harness.HarnessError as exc:
        # EMPTY_CONTENT / INVALID_SESSION：拒絕本次請求，於對話中顯示錯誤訊息，
        # 並在思考區步驟②標示錯誤狀態（顯示原則 5：錯誤也需呈現）。
        if exc.code == "INVALID_SESSION":
            session_id = None
        _apply_step_event(
            step_views,
            make_step_event("build_request", status="error", delta=exc.user_message),
        )
        history = history + [{"role": "assistant", "content": f"⚠️ {exc.user_message}"}]
        yield history, _current_html(True), gr.update(interactive=True), gr.update(interactive=True), session_id
        return

    if request_payload is None:
        # 理論上不會發生：Harness.handle_turn() 沒有拋例外就一定會 yield
        # 一次 "result"；這裡是防呆，避免 request_payload 是 None 時繼續
        # 往下呼叫 LLMReasoning.process() 而整個崩潰。
        logger_message = "Harness.handle_turn() 未回傳 result，已中止本輪對話。"
        history = history + [{"role": "assistant", "content": f"⚠️ {logger_message}"}]
        yield history, _current_html(True), gr.update(interactive=True), gr.update(interactive=True), session_id
        return

    # 把 Harness 組好的完整 payload（系統提示詞 + 歷史對話 + 這句清理過的
    # 提問）交給 LLMReasoning/ 模組，而不是只送清理後的使用者文字——這樣
    # 系統提示詞與歷史對話才會真的送進模型，不會被丟掉。LLMReasoning.process()
    # 內部會呼叫 LLM/ 模組取得回應、判定是否需要呼叫工具，並把這一輪的
    # 完整回覆寫回 Session 歷史，Frontend 不用再手動呼叫
    # Harness.append_assistant_message。
    history = history + [{"role": "assistant", "content": ""}]

    for event, data in LLMReasoning.process(session_id, request_payload):
        if event == "step":
            _apply_step_event(step_views, data)
            if data.step_key in MIRRORS_TO_CHAT:
                # 步驟⑦A／⑯：這兩步的內容除了思考區，也同步進左側聊天氣泡
                # （取代舊版 response_chunk 事件的用途）。
                history[-1]["content"] += data.delta or ""
            yield history, _current_html(), gr.update(interactive=False), gr.update(interactive=False), session_id
        elif event == "end":
            yield history, _current_html(True), gr.update(interactive=True), gr.update(interactive=True), session_id

def on_like(data: gr.LikeData):
    feedback = "讚" if data.liked else "踩"
    print(f"[feedback] index={data.index} value={feedback} message={data.value!r}")

def on_copy(data: gr.CopyData):
    print(f"[copy] value={data.value!r}")

# ----------------------------------------------------------------------------
# 建立 Gradio Blocks
# ----------------------------------------------------------------------------
def build_demo() -> gr.Blocks:
    with gr.Blocks(title="127.0.0.1:7860") as demo:
        # 每個瀏覽器分頁各自的 Harness Session ID（記憶體內，不落地儲存）。
        # 初始為 None；第一次呼叫 Harness.handle_turn() 時會自動產生 UUID v4。
        session_id_state = gr.State(value=None)

        # ================================================================
        # 主要對話頁
        # ================================================================
        with gr.Tab(label="對話"):
            with gr.Column(elem_id="app_header"):
                gr.Markdown("# AI 助手", elem_id="app_title")
                gr.Markdown("智慧對話、思考過程與回覆集中在同一個工作區。", elem_id="app_subtitle")

            with gr.Row(elem_id="main_layout"):
                # ---------------- 左側：固定 2/3 寬度 ----------------
                with gr.Column(elem_id="left_panel", scale=2, min_width=0):
                    chatbot = gr.Chatbot(
                        elem_id="chatbot_main",
                        buttons=["copy"],
                        feedback_options=("Like", "Dislike"),
                        like_user_message=False,
                    )

                    with gr.Group(elem_classes="input-group"):
                        with gr.Row():
                            msg_box = gr.Textbox(
                                placeholder="輸入訊息後按 Enter 或點擊發送…",
                                show_label=False,
                                autofocus=True,
                                container=False,
                                scale=8,
                            )
                            send_btn = gr.Button(
                                value="➤",
                                elem_id="send_btn",
                                scale=1,
                                min_width=52,
                            )

                    with gr.Row(elem_id="example-row"):
                        example_btns = [
                            gr.Button(q, size="sm") for q in EXAMPLE_QUESTIONS
                        ]

                # ---------------- 右側：固定 1/3 寬度 ----------------
                with gr.Column(elem_id="right_panel", scale=1, min_width=0):
                    thought_html = gr.HTML(
                        value=render_thought_html(),
                        elem_id="thought_panel",
                        # 鎖死高度 = 一律填滿 #thought_panel（見 CUSTOM_CSS），
                        # 內容變長時交給 Gradio 自己的 overflow-y:auto 捲動；
                        # autoscroll=True 是 Gradio HTML 元件內建的「黏底」
                        # 行為：內容更新時若使用者本來就在底部附近，自動捲到
                        # 新內容；若使用者已經手動往上滑，就不會被拉回去。
                        # 這樣就不用自己刻一套 MutationObserver + 記錄捲動
                        # 位置的邏輯（原本刻的那套已經移除，見 HEAD_JS 說明）。
                        min_height="100%",
                        max_height="100%",
                        autoscroll=True,
                    )

        # ================================================================
        # 說明頁
        # ================================================================
        with gr.Tab(label="軌跡"):
            with gr.Column(elem_id="about_panel"):
                gr.Image("./diagram.png",width="100%")

        # ================================================================
        # 事件綁定
        # ================================================================
        msg_box.submit(
            fn=user_submit,
            inputs=[msg_box, chatbot],
            outputs=[chatbot, msg_box, thought_html],
        ).then(
            fn=disable_inputs,
            outputs=[msg_box, send_btn],
        ).then(
            fn=bot_response,
            inputs=[chatbot, session_id_state],
            outputs=[chatbot, thought_html, msg_box, send_btn, session_id_state],
        )

        send_btn.click(
            fn=user_submit,
            inputs=[msg_box, chatbot],
            outputs=[chatbot, msg_box, thought_html],
        ).then(
            fn=disable_inputs,
            outputs=[msg_box, send_btn],
        ).then(
            fn=bot_response,
            inputs=[chatbot, session_id_state],
            outputs=[chatbot, thought_html, msg_box, send_btn, session_id_state],
        )

        for btn, q in zip(example_btns, EXAMPLE_QUESTIONS):
            btn.click(
                fn=lambda question=q: question,
                outputs=[msg_box],
            ).then(
                fn=user_submit,
                inputs=[msg_box, chatbot],
                outputs=[chatbot, msg_box, thought_html],
            ).then(
                fn=disable_inputs,
                outputs=[msg_box, send_btn],
            ).then(
                fn=bot_response,
                inputs=[chatbot, session_id_state],
                outputs=[chatbot, thought_html, msg_box, send_btn, session_id_state],
            )

        chatbot.like(on_like, inputs=None, outputs=None)
        chatbot.copy(on_copy, inputs=None, outputs=None)

    return demo

demo = build_demo()

if __name__ == "__main__":
    demo.queue()
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        head=HEAD_JS,
        css=CUSTOM_CSS,
    )
