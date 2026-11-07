"""確認環境：向量模型、pgvector、回答模型都能動。"""
import time

import numpy as np
import ollama
import psycopg
from pgvector.psycopg import register_vector

EMBED_MODEL = "bge-m3"
CHAT_MODEL = "qwen3:8b"
DB_URL = "postgresql://rag:rag_dev_only@127.0.0.1:5432/rag"

texts = ["員工每年有十四天特休假", "公司地址在台中市西屯區", "報銷差旅費需要附上發票"]
question = "一年可以請幾天休假？"

# 1. 文字轉向量
start = time.time()
vectors = ollama.embed(model=EMBED_MODEL, input=texts + [question]).embeddings
print(f"[向量] {len(vectors)} 筆，維度 {len(vectors[0])}，{time.time() - start:.1f} 秒")

# 2. 存進 pgvector，用餘弦距離找最接近的句子
with psycopg.connect(DB_URL, autocommit=True) as conn:
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    conn.execute(f"CREATE TEMP TABLE t (content text, embedding vector({len(vectors[0])}))")
    for text, vector in zip(texts, vectors):
        conn.execute("INSERT INTO t VALUES (%s, %s)", (text, np.array(vector)))
    rows = conn.execute(
        "SELECT content, embedding <=> %s AS distance FROM t ORDER BY distance",
        (np.array(vectors[-1]),),
    ).fetchall()
for content, distance in rows:
    print(f"[搜尋] 距離 {distance:.3f}  {content}")

# 3. 回答模型
start = time.time()
reply = ollama.chat(
    model=CHAT_MODEL,
    think=False,
    messages=[
        {"role": "system", "content": "只根據資料回答，使用繁體中文。"},
        {"role": "user", "content": f"資料：{rows[0][0]}\n\n問題：{question}"},
    ],
)
print(f"[回答] {time.time() - start:.1f} 秒：{reply.message.content.strip()}")

# 4. 模型實際跑在哪裡
for model in ollama.ps().models:
    print(f"[載入] {model.model} 總共 {model.size / 1e9:.1f} GB，GPU 上 {model.size_vram / 1e9:.1f} GB")
