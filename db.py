"""資料庫連線與資料表。

兩張表：
- documents：一份文件一列，content_hash 用來擋重複上傳。
- chunks：文件切出來的每一塊，含原文和向量。
  刪除文件時，ON DELETE CASCADE 會一起刪掉它的所有塊。
"""
import psycopg
from pgvector.psycopg import register_vector

from config import DB_URL, EMBED_DIM

# VECTOR(1024) 是 pgvector 提供的欄位型別，長度要和向量模型的輸出一致
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS documents (
    id           BIGSERIAL PRIMARY KEY,
    filename     TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id          BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    page        INT,
    content     TEXT NOT NULL,
    embedding   VECTOR({EMBED_DIM}) NOT NULL
);

CREATE INDEX IF NOT EXISTS chunks_document_id_idx ON chunks (document_id);

-- 問答紀錄。不關聯 documents：文件刪掉後，過去的問答和來源檔名仍保留
-- status：done 完成、error 出錯、stopped 使用者中途停止
-- 時間單位是毫秒，從後端收到問題開始算；沒走到那一步的是 NULL
CREATE TABLE IF NOT EXISTS questions (
    id             BIGSERIAL PRIMARY KEY,
    question       TEXT NOT NULL,
    answer         TEXT NOT NULL,
    backend        TEXT NOT NULL,
    model          TEXT NOT NULL,
    status         TEXT NOT NULL,
    error          TEXT,
    sources        JSONB NOT NULL DEFAULT '[]',
    search_ms      INT,
    first_token_ms INT,
    total_ms       INT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def init_db() -> None:
    """啟用 pgvector 並建立資料表；已經存在就略過，所以每次啟動都可以呼叫。"""
    with psycopg.connect(DB_URL, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(SCHEMA)


def connect() -> psycopg.Connection:
    """開一條連線。register_vector 讓 numpy 陣列可以直接當成向量參數傳進 SQL。"""
    conn = psycopg.connect(DB_URL)
    register_vector(conn)
    return conn
