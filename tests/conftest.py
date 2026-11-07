"""測試用假的模型，不需要 GPU 和 Ollama；資料庫用獨立的 rag_test，不動到正式資料。

需要先啟動 Docker 的資料庫：docker compose up -d
"""
import hashlib
import math
import os
from types import SimpleNamespace

import psycopg
import pytest

ADMIN_URL = "postgresql://rag:rag_dev_only@127.0.0.1:5432/rag"
TEST_URL = "postgresql://rag:rag_dev_only@127.0.0.1:5432/rag_test"

# 必須在匯入專案程式之前設定
os.environ["RAG_DB_URL"] = TEST_URL
os.environ["LLM_BACKEND"] = "ollama"

import api  # noqa: E402
from config import EMBED_DIM  # noqa: E402
from db import connect, init_db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def fake_vector(text: str) -> list[float]:
    """用字元雜湊產生向量：共用的字越多，向量越接近。"""
    vector = [0.0] * EMBED_DIM
    for char in text:
        vector[int(hashlib.md5(char.encode()).hexdigest(), 16) % EMBED_DIM] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


class FakeOllama:
    def __init__(self):
        self.answer = ["這是", "測試回答 [1]"]
        self.chat_error = None
        self.embed_error = None
        self.chats = []

    def embed(self, model, input):
        if self.embed_error:
            raise self.embed_error
        texts = [input] if isinstance(input, str) else input
        return SimpleNamespace(embeddings=[fake_vector(text) for text in texts])

    def chat(self, model, messages, **options):
        if self.chat_error:
            raise self.chat_error
        self.chats.append(messages)
        return (SimpleNamespace(message=SimpleNamespace(content=text)) for text in self.answer)


@pytest.fixture(scope="session", autouse=True)
def test_database():
    try:
        with psycopg.connect(ADMIN_URL, autocommit=True, connect_timeout=3) as conn:
            exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = 'rag_test'").fetchone()
            if not exists:
                conn.execute("CREATE DATABASE rag_test")
    except psycopg.OperationalError:
        pytest.exit("連不到資料庫，請先執行 docker compose up -d", returncode=2)
    init_db()


@pytest.fixture
def fake_ollama(monkeypatch):
    fake = FakeOllama()
    monkeypatch.setattr("ollama.embed", fake.embed)
    monkeypatch.setattr("ollama.chat", fake.chat)
    return fake


@pytest.fixture
def client(fake_ollama):
    with connect() as conn:
        conn.execute("TRUNCATE documents, questions CASCADE")
    with TestClient(api.app) as test_client:
        yield test_client
