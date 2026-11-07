import json
from types import SimpleNamespace

import httpx

import api
import llm
from db import connect
from rag import NO_ANSWER


def upload(client, name="文件.txt", content="第三季專案的預算為八十萬元。"):
    return client.post("/api/documents", files={"file": (name, content.encode("utf-8"))})


def ask(client, question="第三季專案的預算是多少？"):
    response = client.post("/api/chat", json={"question": question})
    assert response.status_code == 200
    return [json.loads(line[6:]) for line in response.text.split("\n\n") if line.startswith("data: ")]


def answer_of(events):
    return "".join(event["text"] for event in events if event["type"] == "token")


def test_upload_then_list(client):
    response = upload(client)
    assert response.status_code == 201
    assert response.json()["chunks"] == 1
    assert [item["filename"] for item in client.get("/api/documents").json()] == ["文件.txt"]


def test_same_content_is_not_added_twice(client):
    first = upload(client).json()
    second = upload(client, name="改名.txt").json()
    assert second["duplicate"] is True
    assert second["document_id"] == first["document_id"]
    assert len(client.get("/api/documents").json()) == 1


def test_unsupported_type_returns_415(client):
    assert upload(client, name="a.exe").status_code == 415


def test_blank_file_returns_422_with_original_name(client):
    response = upload(client, name="空白.txt", content="   ")
    assert response.status_code == 422
    assert "空白.txt" in response.json()["detail"]


def test_too_large_file_returns_413(client, monkeypatch):
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 5)
    assert upload(client).status_code == 413


def test_directory_is_removed_from_filename(client):
    assert upload(client, name="../../evil.txt").json()["filename"] == "evil.txt"


def test_preview_rebuilds_text_without_overlap(client):
    sentences = "".join(f"第{i}句內容在這裡。" for i in range(100))
    document_id = upload(client, content=sentences).json()["document_id"]
    body = client.get(f"/api/documents/{document_id}").json()
    assert body["filename"] == "文件.txt"
    assert [section["text"] for section in body["sections"]] == [sentences]


def test_preview_missing_document_returns_404(client):
    assert client.get("/api/documents/999999").status_code == 404


def test_delete_removes_chunks(client):
    document_id = upload(client).json()["document_id"]
    assert client.delete(f"/api/documents/{document_id}").status_code == 204
    with connect() as conn:
        assert conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == 0


def test_delete_missing_document_returns_404(client):
    assert client.delete("/api/documents/999999").status_code == 404


def test_chat_streams_sources_tokens_and_citations(client, fake_ollama):
    upload(client)
    events = ask(client)
    assert [event["type"] for event in events] == ["sources", "token", "token", "done"]
    assert events[0]["sources"][0]["filename"] == "文件.txt"
    assert answer_of(events) == "這是測試回答 [1]"
    assert events[-1]["cited"] == [1]


def test_retrieved_text_and_question_reach_the_model(client, fake_ollama):
    upload(client)
    ask(client)
    system, user = fake_ollama.chats[0]
    assert "只能根據" in system["content"]
    assert "八十萬元" in user["content"]
    assert "第三季專案的預算是多少？" in user["content"]


def test_citation_outside_sources_is_dropped(client, fake_ollama):
    upload(client)
    fake_ollama.answer = ["回答 [1] [9]"]
    assert ask(client)[-1]["cited"] == [1]


def test_no_relevant_text_skips_the_model(client, fake_ollama):
    upload(client)
    events = ask(client, "xyz qqq 123")
    assert answer_of(events) == NO_ANSWER
    assert fake_ollama.chats == []


def test_blank_question_returns_422(client):
    assert client.post("/api/chat", json={"question": "   "}).status_code == 422
    assert client.post("/api/chat", json={"question": ""}).status_code == 422


def test_upload_returns_503_when_embedding_fails(client, fake_ollama):
    fake_ollama.embed_error = ConnectionError("連不到")
    response = upload(client)
    assert response.status_code == 503
    assert client.get("/api/documents").json() == []


def test_chat_reports_connection_error_during_streaming(client, fake_ollama):
    upload(client)
    fake_ollama.chat_error = httpx.ConnectError("連不到")
    events = ask(client)
    assert events[-1]["type"] == "error"
    assert "模型服務" in events[-1]["message"]


def installed(monkeypatch, *names):
    models = [SimpleNamespace(model=name) for name in names]
    monkeypatch.setattr("ollama.list", lambda: SimpleNamespace(models=models))


def test_health_ok(client, monkeypatch):
    installed(monkeypatch, "bge-m3:latest", "qwen3:8b")
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_reports_missing_model(client, monkeypatch):
    installed(monkeypatch, "bge-m3:latest")
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["missing_models"] == ["qwen3:8b"]


def test_health_reports_ollama_offline(client, monkeypatch):
    def offline():
        raise ConnectionError("連不到")

    monkeypatch.setattr("ollama.list", offline)
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["ollama"] is False


def test_claude_cli_runs_without_tools(client, monkeypatch):
    calls = {}

    def fake_run(command, **options):
        calls.update(command=command, input=options["input"])
        return SimpleNamespace(returncode=0, stdout=json.dumps({"result": "答案 [1]"}), stderr="")

    monkeypatch.setattr(llm, "LLM_BACKEND", "claude_cli")
    monkeypatch.setattr(llm.shutil, "which", lambda name: "claude")
    monkeypatch.setattr(llm.subprocess, "run", fake_run)

    upload(client)
    events = ask(client)
    assert answer_of(events) == "答案 [1]"
    assert calls["command"][calls["command"].index("--tools") + 1] == ""
    assert "八十萬元" in calls["input"]


def test_claude_cli_failure_becomes_error_event(client, monkeypatch):
    monkeypatch.setattr(llm, "LLM_BACKEND", "claude_cli")
    monkeypatch.setattr(llm.shutil, "which", lambda name: "claude")
    monkeypatch.setattr(
        llm.subprocess, "run",
        lambda command, **options: SimpleNamespace(returncode=1, stdout="", stderr="未登入"),
    )
    upload(client)
    assert "未登入" in ask(client)[-1]["message"]


def test_unknown_backend_becomes_error_event(client, monkeypatch):
    monkeypatch.setattr(llm, "LLM_BACKEND", "nope")
    upload(client)
    assert ask(client)[-1]["type"] == "error"


def models_installed(monkeypatch, claude=False, claude_enabled=True):
    """假裝 Ollama 有一個回答模型和一個向量模型；claude 代表有沒有安裝 Claude CLI。"""
    capabilities = {"qwen3:8b": ["completion"], "bge-m3:latest": ["embedding"]}
    installed(monkeypatch, *capabilities)
    monkeypatch.setattr("ollama.show", lambda name: SimpleNamespace(capabilities=capabilities[name]))
    monkeypatch.setattr(llm.shutil, "which", lambda name: "claude" if claude else None)
    monkeypatch.setattr(llm, "ENABLE_CLAUDE_CLI", claude_enabled)


def test_models_lists_chat_models_only(client, monkeypatch):
    models_installed(monkeypatch, claude=True)
    body = client.get("/api/models").json()
    assert body["default"] == {"backend": "ollama", "model": "qwen3:8b"}
    assert {"backend": "ollama", "model": "qwen3:8b"} in body["models"]
    assert {"backend": "claude_cli", "model": "haiku"} in body["models"]
    assert all(item["model"] != "bge-m3:latest" for item in body["models"])


def test_models_without_claude_cli(client, monkeypatch):
    models_installed(monkeypatch, claude=False)
    backends = {item["backend"] for item in client.get("/api/models").json()["models"]}
    assert backends == {"ollama"}


def test_chat_uses_selected_model(client, monkeypatch):
    calls = {}

    def fake_run(command, **options):
        calls["model"] = command[command.index("--model") + 1]
        return SimpleNamespace(returncode=0, stdout=json.dumps({"result": "答案 [1]"}), stderr="")

    models_installed(monkeypatch, claude=True)
    monkeypatch.setattr(llm.subprocess, "run", fake_run)
    upload(client)
    response = client.post(
        "/api/chat", json={"question": "第三季專案的預算是多少？", "backend": "claude_cli", "model": "sonnet"},
    )
    assert "答案 [1]" in response.text
    assert calls["model"] == "sonnet"


def test_chat_rejects_unavailable_model(client, monkeypatch):
    models_installed(monkeypatch)
    for choice in (
        {"backend": "ollama", "model": "bge-m3:latest"},  # 向量模型不能回答
        {"backend": "ollama", "model": "llama3:70b"},     # 沒下載的模型
        {"backend": "claude_cli", "model": "haiku"},      # 沒有安裝 Claude CLI
    ):
        response = client.post("/api/chat", json={"question": "預算？", **choice})
        assert response.status_code == 422


def test_chat_records_question_and_timing(client, fake_ollama):
    upload(client)
    done = ask(client)[-1]
    timing = done["timing"]
    assert 0 <= timing["search_ms"] <= timing["first_token_ms"] <= timing["total_ms"]

    records = client.get("/api/questions").json()
    assert len(records) == 1
    record = records[0]
    assert record["id"] == done["question_id"]
    assert record["question"] == "第三季專案的預算是多少？"
    assert record["answer"] == "這是測試回答 [1]"
    assert (record["backend"], record["model"]) == ("ollama", "qwen3:8b")
    assert record["status"] == "done"
    assert record["sources"] == [{"filename": "文件.txt", "page": None}]
    assert record["total_ms"] == timing["total_ms"]


def test_chat_records_model_error(client, fake_ollama):
    upload(client)
    fake_ollama.chat_error = httpx.ConnectError("連不到")
    events = ask(client)
    assert events[-1]["type"] == "error"
    assert events[-1]["timing"]["first_token_ms"] is None

    record = client.get("/api/questions").json()[0]
    assert record["status"] == "error"
    assert "連不到" in record["error"]


def test_stopped_chat_is_recorded(client, fake_ollama):
    upload(client)
    events = api._chat_events("第三季專案的預算是多少？", None, None)
    next(events)  # sources
    next(events)  # 第一段回答
    events.close()  # 模擬使用者按停止、連線中斷

    record = client.get("/api/questions").json()[0]
    assert record["status"] == "stopped"
    assert record["answer"] == "這是"
    assert record["first_token_ms"] is not None


def test_questions_newest_first_with_limit(client, fake_ollama):
    upload(client)
    for question in ("第一題預算？", "第二題預算？"):
        ask(client, question)
    records = client.get("/api/questions?limit=1").json()
    assert [record["question"] for record in records] == ["第二題預算？"]
    assert client.get("/api/questions?limit=0").status_code == 422


def test_claude_hidden_unless_enabled(client, monkeypatch):
    models_installed(monkeypatch, claude=True, claude_enabled=False)
    backends = {item["backend"] for item in client.get("/api/models").json()["models"]}
    assert backends == {"ollama"}
    response = client.post("/api/chat", json={"question": "預算？", "backend": "claude_cli", "model": "haiku"})
    assert response.status_code == 422


def test_questions_keyword_search(client, fake_ollama):
    upload(client)
    for question in ("預算多少？", "100%_完成了嗎？"):
        ask(client, question)
    assert [r["question"] for r in client.get("/api/questions?q=預算").json()] == ["預算多少？"]
    # % 和 _ 要照字面比對，不能當成萬用字元
    assert [r["question"] for r in client.get("/api/questions?q=0%_").json()] == ["100%_完成了嗎？"]
    assert client.get("/api/questions?q=%25").json()[0]["question"] == "100%_完成了嗎？"
    assert client.get("/api/questions?q=找不到的字").json() == []
