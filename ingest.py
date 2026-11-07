"""把文件解析、切塊、向量化後存進資料庫。

RAG 的「匯入」半段：
1. 算檔案雜湊值，內容一樣的檔案不重複匯入。
2. parse_file 取出文字（PDF 保留頁碼）。
3. chunk_text 切成小塊。
4. embed_texts 把每塊轉成向量。
5. 文件和所有塊在同一個交易裡寫進資料庫。

用法：python ingest.py 檔案1 [檔案2 ...]
"""
import hashlib
import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np
import ollama

from chunker import chunk_text
from config import CHUNK_OVERLAP, CHUNK_SIZE, EMBED_BATCH_SIZE, EMBED_MODEL
from db import connect, init_db
from document_parser import parse_file


class IngestResult(NamedTuple):
    """匯入結果。duplicate 為 True 代表資料庫已有相同內容，這次沒有寫入。"""
    document_id: int
    filename: str
    chunks: int
    duplicate: bool


def embed_texts(texts: list[str]) -> list[np.ndarray]:
    """把多段文字轉成向量，每次送 EMBED_BATCH_SIZE 段給 Ollama。"""
    # 分批送：一次送太多段會占用大量記憶體，一段一段送又太慢
    vectors = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start:start + EMBED_BATCH_SIZE]
        vectors.extend(np.array(v) for v in ollama.embed(model=EMBED_MODEL, input=batch).embeddings)
    return vectors


def ingest_file(path: Path, filename: str | None = None) -> IngestResult:
    """匯入一個檔案。filename 是要顯示的名稱，網頁上傳時暫存檔的名字不一樣。"""
    filename = filename or path.name
    # 用內容算雜湊，不用檔名：改過檔名的同一份檔案也認得出來
    content_hash = hashlib.sha256(path.read_bytes()).hexdigest()

    with connect() as conn:
        existing = conn.execute(
            "SELECT d.id, d.filename, count(c.id) FROM documents d "
            "LEFT JOIN chunks c ON c.document_id = d.id "
            "WHERE d.content_hash = %s GROUP BY d.id",
            (content_hash,),
        ).fetchone()
    if existing:
        return IngestResult(existing[0], existing[1], existing[2], duplicate=True)

    # 每一塊都記住它來自哪一頁，回答時才能顯示頁碼
    pieces = [
        (section.page, chunk)
        for section in parse_file(path, filename)
        for chunk in chunk_text(section.text, CHUNK_SIZE, CHUNK_OVERLAP)
    ]
    # 向量化最花時間，放在開資料庫交易之前，避免交易拖太久
    vectors = embed_texts([chunk for _, chunk in pieces])

    # with 區塊正常結束才 commit，中途出錯不會留下只寫一半的文件
    with connect() as conn:
        document_id = conn.execute(
            "INSERT INTO documents (filename, content_hash) VALUES (%s, %s) RETURNING id",
            (filename, content_hash),
        ).fetchone()[0]
        with conn.cursor() as cursor:
            # executemany 一次寫入所有塊；chunk_index 記錄順序，預覽時才能照原文排回去
            cursor.executemany(
                "INSERT INTO chunks (document_id, chunk_index, page, content, embedding) "
                "VALUES (%s, %s, %s, %s, %s)",
                [
                    (document_id, index, page, chunk, vector)
                    for index, ((page, chunk), vector) in enumerate(zip(pieces, vectors))
                ],
            )
    return IngestResult(document_id, filename, len(pieces), duplicate=False)


if __name__ == "__main__":
    # 命令列版本，可一次匯入多個檔案；任一個失敗時結束碼為 1
    if len(sys.argv) < 2:
        sys.exit("用法：python ingest.py 檔案1 [檔案2 ...]")

    init_db()
    failed = False
    for name in sys.argv[1:]:
        path = Path(name)
        try:
            result = ingest_file(path)
            status = f"略過，內容和 {result.filename} 相同" if result.duplicate else f"完成，{result.chunks} 塊"
            print(f"{path.name}：{status}")
        except (OSError, ValueError) as error:
            failed = True
            print(f"{path.name}：失敗，{error}")
    sys.exit(1 if failed else 0)
