"""回答模型後端，由環境變數 LLM_BACKEND 切換。

ollama      本機模型，文件不離開電腦
claude_cli  已登入的 Claude Code CLI，檢索到的文字會傳到 Anthropic

兩種後端對外都是 stream_chat(messages)，回傳一段一段的文字，
所以 rag.py 和 api.py 不需要知道現在用的是哪一個。

預設後端和模型來自環境變數；前端也可以每次提問時指定，
可選的模型由 available_models() 列出。
"""
import json
import shutil
import subprocess
import tempfile
from collections.abc import Iterator

import httpx
import ollama

from config import CHAT_NUM_CTX, CLAUDE_MODEL, ENABLE_CLAUDE_CLI, LLM_BACKEND, OLLAMA_MODEL

# 串流時斷線丟的是 httpx 的例外，不是 ConnectionError
OLLAMA_ERRORS = (ollama.ResponseError, ConnectionError, httpx.HTTPError)
CLAUDE_TIMEOUT_SECONDS = 180
# Claude CLI 接受的模型別名
CLAUDE_MODELS = ("haiku", "sonnet", "opus")


class LLMError(RuntimeError):
    """模型無法使用時統一丟這個例外，api.py 再轉成給使用者看的錯誤訊息。"""


def _can_chat(model: str) -> bool:
    """向量模型（例如 bge-m3）不能回答問題，用 Ollama 回報的能力排除。"""
    capabilities = ollama.show(model).capabilities
    # 舊版 Ollama 不回報能力，這時全部列出
    return capabilities is None or "completion" in capabilities


def available_models() -> list[dict]:
    """列出現在能用的回答模型：Ollama 已下載的模型，加上有開啟且已安裝 Claude CLI 時的 Claude 模型。"""
    models = []
    try:
        for item in ollama.list().models:
            if _can_chat(item.model):
                models.append({"backend": "ollama", "model": item.model})
    except OLLAMA_ERRORS:
        pass  # Ollama 沒開時只列 Claude
    if ENABLE_CLAUDE_CLI and shutil.which("claude"):
        models.extend({"backend": "claude_cli", "model": name} for name in CLAUDE_MODELS)
    return models


def default_model() -> dict:
    """環境變數設定的預設模型，前端第一次開啟時選這個。"""
    model = CLAUDE_MODEL if LLM_BACKEND == "claude_cli" else OLLAMA_MODEL
    return {"backend": LLM_BACKEND, "model": model}


def _stream_ollama(messages: list[dict], model: str) -> Iterator[str]:
    """呼叫本機 Ollama，邊產生邊回傳。"""
    try:
        stream = ollama.chat(
            model=model,
            messages=messages,
            think=False,  # 關閉 Qwen3 的思考模式，回答比較快
            stream=True,
            # num_ctx：模型一次能讀的長度；temperature 低，回答比較穩定、不亂發揮
            options={"num_ctx": CHAT_NUM_CTX, "temperature": 0.1},
        )
        for part in stream:
            yield part.message.content
    except OLLAMA_ERRORS as error:
        raise LLMError(f"無法使用 Ollama：{error}") from error


def _stream_claude_cli(messages: list[dict], model: str) -> Iterator[str]:
    """呼叫 Claude Code CLI。CLI 一次回傳整段答案，所以只會 yield 一次。"""
    executable = shutil.which("claude")
    if not executable:
        raise LLMError("找不到 claude 指令，請先安裝並登入 Claude Code。")

    system, user = (message["content"] for message in messages)
    # 文件內容不可信，所以關閉所有工具，並在空資料夾執行，避免讀到專案設定
    command = [
        executable, "-p",               # 非互動模式：問一次、回答一次就結束
        "--tools", "",                  # 關閉讀寫檔案、執行指令等所有工具
        "--system-prompt", system,
        "--output-format", "json",
        "--model", model,
        "--no-session-persistence",     # 不留下對話紀錄
        "--strict-mcp-config",          # 不載入額外的 MCP 外掛
    ]
    try:
        with tempfile.TemporaryDirectory() as folder:
            # 問題從標準輸入送進去，不放在指令參數裡，避免太長或特殊字元出問題
            result = subprocess.run(
                command, input=user, cwd=folder, capture_output=True,
                encoding="utf-8", errors="replace", timeout=CLAUDE_TIMEOUT_SECONDS,
            )
    except subprocess.TimeoutExpired as error:
        raise LLMError("Claude CLI 回應逾時。") from error

    if result.returncode != 0:
        raise LLMError(f"Claude CLI 執行失敗：{(result.stderr or result.stdout).strip()[:300]}")
    output = json.loads(result.stdout)
    if output.get("is_error"):
        raise LLMError(f"Claude CLI 回傳錯誤：{output.get('result')}")
    yield output["result"]


def stream_chat(messages: list[dict], backend: str | None = None, model: str | None = None) -> Iterator[str]:
    """選擇後端並回答。messages 固定是 [系統訊息, 使用者訊息]。

    沒指定 backend、model 時用環境變數的預設值。
    """
    backend = backend or LLM_BACKEND
    if backend == "ollama":
        yield from _stream_ollama(messages, model or OLLAMA_MODEL)
    elif backend == "claude_cli":
        yield from _stream_claude_cli(messages, model or CLAUDE_MODEL)
    else:
        raise LLMError(f"不支援的 LLM_BACKEND：{backend}（可用：ollama、claude_cli）")
