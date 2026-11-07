"""HTTP API。啟動：uvicorn api:app --host 127.0.0.1 --port 8000

端點：
- GET    /api/health            檢查資料庫、Ollama、模型是否就緒
- GET    /api/models            可選的回答模型
- GET    /api/documents         文件清單
- POST   /api/documents         上傳並匯入文件
- GET    /api/documents/{id}    預覽文件內容
- DELETE /api/documents/{id}    刪除文件
- POST   /api/chat              問答，用 SSE 串流回傳，並把問答和花費時間存進 questions 表
- GET    /api/questions         問答紀錄，可用關鍵字搜尋

只綁定 127.0.0.1，同網路的其他裝置連不到；這個專案沒有登入驗證。
"""
import json
import logging
import re
import shutil
import tempfile
import time
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import ollama
import psycopg
from fastapi import FastAPI, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from config import EMBED_MODEL, LLM_BACKEND, MAX_UPLOAD_BYTES, OLLAMA_MODEL
from db import connect, init_db
from document_parser import SUPPORTED_SUFFIXES
from ingest import ingest_file
from llm import OLLAMA_ERRORS, LLMError, available_models, default_model
from rag import relevant_hits, search, stream_answer

READ_CHUNK_BYTES = 1024 * 1024
MODEL_ERRORS = (LLMError, *OLLAMA_ERRORS)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """伺服器啟動時先建好資料表。"""
    init_db()
    yield


app = FastAPI(title="RAG 文件問答", lifespan=lifespan)


class ChatRequest(BaseModel):
    """問答請求。Pydantic 會自動檢查長度，不符合時回 422。

    backend 和 model 可以不填，不填就用預設模型。
    """
    question: str = Field(min_length=1, max_length=2000)
    backend: Literal["ollama", "claude_cli"] | None = None
    model: str | None = Field(default=None, max_length=100)


def _with_tag(model: str) -> str:
    """Ollama 的模型名稱沒寫版本時預設是 :latest，比對前先補上。"""
    return model if ":" in model else f"{model}:latest"


def _missing_models() -> list[str]:
    """列出設定要用、但 Ollama 還沒下載的模型。"""
    required = {_with_tag(EMBED_MODEL)}
    # 用 Claude CLI 回答時，Ollama 只需要向量模型
    if LLM_BACKEND == "ollama":
        required.add(_with_tag(OLLAMA_MODEL))
    installed = {model.model for model in ollama.list().models}
    return sorted(required - installed)


@app.get("/api/health")
def health() -> JSONResponse:
    """檢查各項服務；有任何一項不正常就回 503，並說明哪裡有問題。"""
    try:
        with connect() as conn:
            conn.execute("SELECT 1")
        database = True
    except psycopg.Error:
        database = False

    try:
        missing = _missing_models()
        ollama_ok = True
    except OLLAMA_ERRORS:
        missing = []
        ollama_ok = False

    claude_ok = LLM_BACKEND != "claude_cli" or shutil.which("claude") is not None
    healthy = database and ollama_ok and not missing and claude_ok
    return JSONResponse(
        {
            "status": "ok" if healthy else "degraded",
            "database": database,
            "ollama": ollama_ok,
            "missing_models": missing,
            "llm_backend": LLM_BACKEND,
            "claude_cli": claude_ok,
        },
        status_code=200 if healthy else 503,
    )


@app.get("/api/models")
def list_models() -> dict:
    """前端下拉選單用：預設模型和所有可選的回答模型。"""
    return {"default": default_model(), "models": available_models()}


@app.get("/api/documents")
def list_documents() -> list[dict]:
    """所有文件和各自的塊數，最新上傳的排前面。"""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.filename, d.created_at, count(c.id)
            FROM documents d
            LEFT JOIN chunks c ON c.document_id = d.id
            GROUP BY d.id
            ORDER BY d.created_at DESC
            """
        ).fetchall()
    return [
        {"id": row[0], "filename": row[1], "created_at": row[2], "chunks": row[3]}
        for row in rows
    ]


@app.post("/api/documents", status_code=201)
def upload_document(file: UploadFile) -> dict:
    """上傳一個檔案：先存成暫存檔，再交給 ingest_file 匯入，暫存檔用完就刪。"""
    # 只取檔名，瀏覽器送來的路徑不可信
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(415, f"不支援的檔案類型：{suffix or filename}")

    # 暫存檔用固定名稱，不用使用者的檔名，同名檔案不會互相覆蓋
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / f"upload{suffix}"
        size = 0
        with path.open("wb") as output:
            # 每次讀 1 MB，邊讀邊算大小，超過上限立刻停止，不會先把大檔整個讀進記憶體
            while data := file.file.read(READ_CHUNK_BYTES):
                size += len(data)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, f"檔案不能超過 {MAX_UPLOAD_BYTES // 1024 // 1024} MB")
                output.write(data)

        try:
            result = ingest_file(path, filename)
        except ValueError as error:
            # 檔案本身的問題，例如讀不到文字、編碼無法判斷
            raise HTTPException(422, str(error)) from error
        except MODEL_ERRORS as error:
            # 伺服器端的問題，例如 Ollama 沒開
            raise HTTPException(503, f"模型服務無法使用：{error}") from error

    return result._asdict()


def _merge_overlap(previous: str, current: str) -> str:
    """接回相鄰文字塊，去掉切塊時重複的部分。

    從最長的可能重疊開始試：previous 的結尾等於 current 的開頭，就只接上不重複的部分。
    """
    for length in range(min(len(previous), len(current)), 1, -1):
        if previous.endswith(current[:length]):
            return previous + current[length:]
    return f"{previous}\n{current}"


@app.get("/api/documents/{document_id}")
def preview_document(document_id: int) -> dict:
    """把文件的所有塊依順序接回原文，同一頁的塊合併成一段。"""
    with connect() as conn:
        document = conn.execute(
            "SELECT filename FROM documents WHERE id = %s", (document_id,)
        ).fetchone()
        if not document:
            raise HTTPException(404, "找不到這份文件")
        chunks = conn.execute(
            "SELECT page, content FROM chunks WHERE document_id = %s ORDER BY chunk_index",
            (document_id,),
        ).fetchall()

    sections: list[dict] = []
    for page, content in chunks:
        if sections and sections[-1]["page"] == page:
            sections[-1]["text"] = _merge_overlap(sections[-1]["text"], content)
        else:
            sections.append({"page": page, "text": content})
    return {"id": document_id, "filename": document[0], "sections": sections}


@app.delete("/api/documents/{document_id}", status_code=204)
def delete_document(document_id: int) -> None:
    """刪除文件；它的所有塊會因為 ON DELETE CASCADE 一起刪除。"""
    with connect() as conn:
        deleted = conn.execute(
            "DELETE FROM documents WHERE id = %s RETURNING id", (document_id,)
        ).fetchone()
    if not deleted:
        raise HTTPException(404, "找不到這份文件")


def _event(payload: dict) -> str:
    """SSE 格式：每個事件是「data: JSON」加一個空行。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _save_question(record: dict) -> int | None:
    """把一次問答存進 questions 表，回傳紀錄編號。

    存檔失敗只記 log，不影響使用者看到的回答。
    """
    try:
        with connect() as conn:
            row = conn.execute(
                """
                INSERT INTO questions (question, answer, backend, model, status, error,
                                       sources, search_ms, first_token_ms, total_ms)
                VALUES (%(question)s, %(answer)s, %(backend)s, %(model)s, %(status)s, %(error)s,
                        %(sources)s, %(search_ms)s, %(first_token_ms)s, %(total_ms)s)
                RETURNING id
                """,
                {**record, "sources": Jsonb(record["sources"])},
            ).fetchone()
        return row[0]
    except psycopg.Error:
        logger.exception("問答紀錄存檔失敗")
        return None


def _chat_events(question: str, backend: str | None, model: str | None) -> Iterator[str]:
    """問答的事件流，前端依 type 處理。

    1. sources：先送出找到的段落，前端可以先顯示來源。
    2. token：回答的文字片段，前端一段一段接上，看起來像打字。
    3. done：回答結束，附上回答裡實際標註的來源編號、花費時間和紀錄編號。
    出錯時改送 error，不讓連線直接中斷。

    不論完成、出錯或使用者按停止，都會存一筆紀錄到 questions 表。
    """
    # 沒指定模型時，記錄實際使用的預設模型
    choice = {"backend": backend, "model": model} if backend else default_model()
    started = time.perf_counter()

    def elapsed_ms() -> int:
        return round((time.perf_counter() - started) * 1000)

    record = {
        "question": question, "answer": "", **choice, "status": "stopped", "error": None,
        "sources": [], "search_ms": None, "first_token_ms": None, "total_ms": 0,
    }
    saved = False

    def timing() -> dict:
        return {key: record[key] for key in ("search_ms", "first_token_ms", "total_ms")}

    try:
        hits = relevant_hits(search(question))
        record["search_ms"] = record["total_ms"] = elapsed_ms()
        yield _event({
            "type": "sources",
            "sources": [
                {"id": number, "filename": hit.filename, "page": hit.page,
                 "content": hit.content, "distance": round(hit.distance, 3)}
                for number, hit in enumerate(hits, start=1)
            ],
        })

        for text in stream_answer(question, hits, backend, model):
            if record["first_token_ms"] is None:
                record["first_token_ms"] = elapsed_ms()
            record["answer"] += text
            # 使用者中途停止時，用最後收到文字的時間當作總時間
            record["total_ms"] = elapsed_ms()
            yield _event({"type": "token", "text": text})

        # 從回答找出 [1]、[2] 這類標註，只保留真的存在的編號，
        # 前端就只列實際引用的來源，不列搜到但沒用到的段落
        numbers = {int(number) for number in re.findall(r"\[(\d+)\]", record["answer"])}
        cited = sorted(n for n in numbers if 1 <= n <= len(hits))
        record.update(
            status="done", total_ms=elapsed_ms(),
            sources=[{"filename": hits[n - 1].filename, "page": hits[n - 1].page} for n in cited],
        )
        saved = True
        question_id = _save_question(record)
        yield _event({"type": "done", "cited": cited, "timing": timing(), "question_id": question_id})
    except MODEL_ERRORS as error:
        message = f"模型服務無法使用：{error}"
        record.update(status="error", error=message, total_ms=elapsed_ms())
        saved = True
        _save_question(record)
        yield _event({"type": "error", "message": message, "timing": timing()})
    finally:
        # 走到這裡還沒存，代表使用者按了停止，連線被中斷
        if not saved:
            _save_question(record)


@app.get("/api/questions")
def list_questions(
    limit: int = Query(default=50, ge=1, le=500),
    q: str = Query(default="", max_length=200),
) -> list[dict]:
    """最近的問答紀錄，最新的排前面。q 有值時只回傳問題或回答包含這段文字的紀錄。"""
    # ILIKE 裡 % 和 _ 是萬用字元，使用者輸入的要先跳脫，才會照字面比對
    keyword = q.strip().replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, question, answer, backend, model, status, error, sources,
                   search_ms, first_token_ms, total_ms, created_at
            FROM questions
            WHERE %(keyword)s = '' OR question ILIKE %(pattern)s OR answer ILIKE %(pattern)s
            ORDER BY id DESC
            LIMIT %(limit)s
            """,
            {"keyword": keyword, "pattern": f"%{keyword}%", "limit": limit},
        ).fetchall()
    keys = ("id", "question", "answer", "backend", "model", "status", "error", "sources",
            "search_ms", "first_token_ms", "total_ms", "created_at")
    return [dict(zip(keys, row)) for row in rows]


@app.post("/api/chat")
def chat(request: ChatRequest) -> StreamingResponse:
    """問答。回傳 text/event-stream，前端用 fetch 逐段讀取。"""
    question = request.question.strip()
    if not question:
        raise HTTPException(422, "問題不能是空白")
    # 有指定模型時，只接受 available_models() 列出的，避免叫 Ollama 去下載任意模型
    if request.backend or request.model:
        choice = {"backend": request.backend, "model": request.model}
        if choice not in available_models():
            raise HTTPException(422, f"這個模型目前無法使用：{request.model}")
    return StreamingResponse(
        _chat_events(question, request.backend, request.model), media_type="text/event-stream",
    )
