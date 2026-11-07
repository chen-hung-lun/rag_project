# RAG Document Q&A: Project Overview

> [中文版](PROJECT_OVERVIEW.md) | Setup and usage: [README.md](README.md) (Chinese)

## In one sentence

Upload PDF, Word, or text files, ask questions in Chinese, and get answers based only on the documents, with the cited passages marked. By default everything runs locally and documents never leave the machine.

## Problem

A language model has never read your documents, so asking it directly invites made-up answers. RAG first retrieves the relevant passages, then asks the model to answer only from them.

This project implements the whole pipeline by hand: parsing, chunking, embedding, storage, retrieval, filtering, prompt building, streaming answers, and citing sources, with automated tests and an evaluation set to check each step.

## My role

Personal project. I decided the requirements, architecture, and technology choices, and wrote the code with extensive help from Claude Code. I reviewed the code and ran the tests and evaluations.

## Architecture

```text
Vue 3 + TypeScript (document list, chat, history, model picker)
        │  /api/* (Vite proxy)
        ▼
FastAPI (api.py)
   Upload: document_parser extracts text → chunker splits by sentence → bge-m3 embeds → PostgreSQL
   Ask:    embed question → pgvector top 4 → distance threshold → build prompt → model → SSE stream
        │                                   │
        ▼                                   ▼
PostgreSQL 17 + pgvector (Docker)      Answer model (selectable per question)
   documents, chunks, questions tables  Ollama local model (default qwen3:8b)
                                        Claude Code CLI (haiku / sonnet / opus, off by default)
```

## Key design decisions

| Decision | Reason |
|---|---|
| No RAG framework; hand-written pipeline | Chunking, the distance threshold, and citing only used sources all need fine control. The core pipeline fits in three files and every step is visible |
| PostgreSQL + pgvector | Data persists; documents and vectors live in one database, so JOINs, transactions, and cascading deletes work |
| `bge-m3` embedding model | Multilingual model with good Chinese support that runs locally through Ollama |
| Sentence-based chunking; overlap uses whole sentences | Chunks never start mid-sentence, which makes results and previews easier to read |
| Distance threshold plus prompt rules | With no relevant passage the model is not called; cases the threshold misses are handled by instructing the model to say it cannot find the answer |
| Show only cited sources | The model marks [1], [2]; the backend parses them and returns only passages actually cited |
| SSE streaming | Local models take a while, so tokens are shown as they arrive. Questions are sent with POST, so the frontend reads the stream with fetch |
| All tools disabled for Claude CLI | Uploaded documents may contain malicious instructions; without file or command access, the worst case is a misleading answer |
| Model picker in the UI, validated by the backend | Makes it easy to compare local and cloud models; only listed models are accepted, so Ollama cannot be made to download arbitrary models |
| `num_ctx` set to 6144 | With 8192 the two models no longer fit on an 8 GB GPU and are reloaded on every question |

## Verification

- **Automated tests:** 56 pytest tests, about 3 seconds. A fake Ollama replaces the real models, so no GPU is needed; the database is a real PostgreSQL instance using a separate `rag_test` database. Covers upload, duplicates, size and type limits, preview, delete, streaming, citation parsing, health check, model switching, disconnects, question logging with timing, and Claude CLI running without tools.
- **Evaluation set:** `eval_rag.py` runs fixed questions against the real models. All 19 answerable questions were answered correctly, all 5 unanswerable questions were refused, and the malicious instruction in a sample file did not affect answers.
- **Manual run:** On 2026-11-06 the same question was answered by both qwen3:8b and Claude haiku; both were correct and cited the source. The model picker was checked in a browser, including that the choice persists after a reload.

The evaluation questions were written against the sample documents and most answers sit in a single passage, so these results do not represent accuracy on real documents.

## Known limitations

- Vector search only; exact terms such as names, model numbers, or article numbers may be missed.
- No conversation memory, so follow-ups like "What about overseas?" are not understood.
- Scanned PDFs without a text layer need OCR, which is not supported.
- Chunking happens within each page, so sentences spanning pages are split.
- No authentication; the server binds to 127.0.0.1 and must not be exposed directly.
- With Claude CLI, retrieved passages are sent to Anthropic, and answers are not streamed token by token.

## FAQ

**Why not LangChain?**

LangChain is great for a quick prototype, but this project needs control over details: splitting on Chinese punctuation, overlapping with whole sentences only, using a distance threshold to decide whether to call the model, and listing only the sources actually cited. Those require working inside the framework. The core pipeline is small (`chunker.py`, `ingest.py`, `rag.py`), every step is visible, and problems are easy to trace. The cost is more code, and switching databases or models means changing it by hand.

**Why pgvector instead of FAISS, Chroma, or Pinecone?**

FAISS keeps its index in memory by default, so it is lost on restart. pgvector keeps documents and vectors in the same PostgreSQL database, with SQL JOINs, transactions, and `ON DELETE CASCADE`, so there is only one store to maintain. Pinecone is a cloud service, so documents would leave the machine. As data grows, pgvector supports HNSW indexes.

**Why chunk, and where do 500 characters with 100 overlap come from?**

One vector for a whole document dilutes the important parts, and the model's context only fits a few passages. Small chunks lack context; large chunks mix topics. 500/100 is a common starting point that the evaluation set showed to work; other settings have not been compared systematically.

**How do you reduce hallucination?**

Four layers: a distance threshold drops unrelated passages, and with none left the model is not called; the prompt allows only content from the provided passages and requires saying when the answer is missing; every fact must cite a source number the user can open; and temperature is 0.1. The evaluation set includes 5 questions with no answer in the documents to confirm refusals.

**What is prompt injection, and how is it handled?**

Uploaded documents may contain text like "ignore the previous instructions." Passages are wrapped in `<source>` tags and the prompt states they are data, not instructions. With Claude CLI, all tools are disabled and it runs in an empty folder, so even a fooled model cannot read files or run commands. The sample file `停車場公告.txt` contains a malicious instruction, and the evaluation script checks that answers are unaffected. Prompt-level defenses are not perfect, which is why permissions are removed as well.

**Why SSE instead of WebSocket?**

Only one-way server-to-client text is needed, and SSE works over plain HTTP. The browser's `EventSource` only supports GET, while questions are sent with POST, so the frontend reads the response stream with `fetch` and splits events itself.

**How do you test without a GPU?**

Automated tests replace Ollama with a fake: vectors come from character hashes, so texts sharing more characters are closer and search order is predictable; answers are fixed and reproducible. The database is a real PostgreSQL instance because SQL and transactions need testing. Anything requiring real models lives in `eval_rag.py`.

**What happens if an import fails halfway?**

The document and all its chunks are written in one transaction, so any error rolls everything back and no half-written document remains. Embedding, the slowest step, runs before the transaction opens so the transaction stays short. Files with identical content are detected with SHA-256 and not imported twice.

**What would change for production or much more data?**

Add authentication, HTTPS, and rate limiting, and move the database password to an environment variable; add an HNSW index to pgvector; move imports to a background job queue; run models on a GPU server or switch to a cloud model API.

## Tech stack

- **Backend:** Python 3.11, FastAPI, Pydantic, psycopg 3, pypdf, python-docx
- **Database:** PostgreSQL 17 + pgvector, run with Docker Compose
- **Models:** Ollama (`bge-m3` embeddings, `qwen3:8b` answers), optional Claude Code CLI
- **Frontend:** Vue 3, TypeScript, Vite
- **Testing:** pytest, FastAPI TestClient

## Next steps

1. Build an evaluation set from real questions as the baseline for future changes.
2. Hybrid search: combine pgvector with PostgreSQL full-text search and merge rankings with RRF to improve exact-term matches.
3. Reranking: retrieve 20 chunks, then use a reranker to pick the best 4.
4. Conversation memory: rewrite follow-ups into standalone questions before searching.
