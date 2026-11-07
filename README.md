# RAG 文件問答系統

上傳文件，用自然語言提問，系統會根據文件內容回答並附上來源。預設全部在本機執行，文件不會傳到外部服務。

想快速了解這個專案，先看 [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)（[English](PROJECT_OVERVIEW.en.md)）。

## 目前進度

| 步驟 | 內容 | 狀態 |
|---|---|---|
| 1 | 環境：Python 套件、PostgreSQL、Ollama 模型 | ✅ 完成，已用 `check_env.py` 實測 |
| 2 | 切塊 `chunker.py` | ✅ 完成，已通過 `chunker.py` 內的測試 |
| 3 | 文件解析（PDF、Word、TXT）並寫入資料庫 | ✅ 完成，已用 `samples/` 實測 |
| 4 | 搜尋與回答 | ✅ 完成，已用 `eval_rag.py` 實測 |
| 5 | FastAPI 後端 API | ✅ 完成，已用實際 HTTP 請求測試 |
| 6 | Vue 3 前端畫面 | ✅ 完成，已用真實瀏覽器測試 |
| 7 | 依句子切塊、自動測試、模型切換、健康檢查、真實文件評估 | ✅ 完成 |

目前已可使用：在網頁上傳文件、提問，回答會逐字顯示並標出來源。啟動方式見「執行方式」。

也可以用指令操作：

```powershell
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python.exe ingest.py samples\報價單.pdf
.\.venv\Scripts\python.exe rag.py 雲端主機方案每個月多少錢？
```

## 什麼是 RAG

RAG（Retrieval-Augmented Generation，檢索增強生成）是先從文件找出相關段落，再把段落和問題一起交給模型回答。模型本身沒讀過你的文件，也可能編造答案，所以要先提供資料給它。

```text
建立索引（上傳時做一次）
文件 → 解析出文字 → 切塊 → 轉成向量 → 存進 PostgreSQL

回答問題（每次提問都做）
問題 → 轉成向量 → 找出最接近的文字塊 → 連同問題交給模型 → 回答與來源
```

## 技術棧

| 層級 | 技術 | 用途 | 選擇原因 |
|---|---|---|---|
| 語言 | Python 3.11 | 後端與 RAG 流程 | AI 工具最完整，也能補上履歷中 Python 較弱的部分 |
| 後端 | FastAPI | 提供 HTTP API | 語法簡潔，內建 Swagger 文件 |
| 前端 | Vue 3 + TypeScript | 上傳與聊天介面 | 開發者已有 Vue 經驗 |
| 資料庫 | PostgreSQL 17 + pgvector | 存文字與向量，並做相似度搜尋 | 同一個資料庫就能處理一般資料和向量 |
| 容器 | Docker Compose | 執行 PostgreSQL | 不用把資料庫裝在 Windows 上，移除也乾淨 |
| 模型執行 | Ollama | 在本機執行 AI 模型 | 免費，資料留在本機 |
| 向量模型 | `bge-m3` | 文字轉向量 | 見「Ollama 模型」 |
| 回答模型 | `qwen3:8b` | 產生回答 | 見「Ollama 模型」 |
| 文件解析 | pypdf、python-docx | 讀取 PDF、Word | 純 Python，安裝簡單 |

刻意不使用 LangChain。這個專案也用來學習，自己寫才看得懂每一步，面試時也講得清楚。

### Python 套件

| 套件 | 用途 |
|---|---|
| `fastapi` | Web API 框架 |
| `uvicorn[standard]` | 執行 FastAPI 的伺服器，類似 ASP.NET Core 的 Kestrel |
| `python-multipart` | 讓 FastAPI 能接收上傳的檔案 |
| `ollama` | 用 Python 呼叫 Ollama |
| `psycopg[binary]` | 連線 PostgreSQL |
| `pgvector` | 讓 Python 能讀寫向量欄位 |
| `numpy` | 處理向量陣列 |
| `pypdf` | 讀取 PDF 文字 |
| `python-docx` | 讀取 Word 文字 |

## Docker：資料庫容器

容器由 `docker-compose.yml` 定義，啟動指令是：

```powershell
docker compose up -d
```

- `docker compose`：讀取目前資料夾的 `docker-compose.yml`。
- `up`：依設定建立並啟動容器。本機沒有映像檔時會先下載。
- `-d`：在背景執行，終端機可以繼續使用。

### 設定檔逐行說明

```yaml
services:                                  # 要啟動的服務
  db:                                      # 服務名稱，自己取的
    image: pgvector/pgvector:pg17          # 映像檔：已裝好 pgvector 的 PostgreSQL 17
    container_name: rag-db                 # 容器名稱，下指令時使用
    environment:                           # 第一次啟動時用來建立資料庫
      POSTGRES_USER: rag                   # 帳號
      POSTGRES_PASSWORD: rag_dev_only      # 密碼，僅供本機開發
      POSTGRES_DB: rag                     # 資料庫名稱
    ports:
      - "127.0.0.1:5432:5432"              # 本機 5432 對應容器 5432
    volumes:
      - rag-db-data:/var/lib/postgresql/data   # 資料存到 volume

volumes:
  rag-db-data:                             # 宣告 volume
```

兩個重要設計：

- **`127.0.0.1:5432:5432`**：只有這台電腦連得到。如果寫成 `5432:5432`，同網路的其他裝置也可能連到資料庫，而這裡的密碼很簡單。
- **Volume**：容器刪除後，裡面的檔案也會消失。資料放在 volume，重建容器時就不會遺失。

### 不用 Compose 的等效指令

```powershell
docker run -d --name rag-db `
  -e POSTGRES_USER=rag -e POSTGRES_PASSWORD=rag_dev_only -e POSTGRES_DB=rag `
  -p 127.0.0.1:5432:5432 `
  -v rag-db-data:/var/lib/postgresql/data `
  pgvector/pgvector:pg17
```

`-e` 是環境變數，`-p` 是連接埠對應，`-v` 是 volume。用 Compose 的原因是設定可以放進 Git，不必記這串指令。

### 常用指令

```powershell
docker ps                                    # 查看執行中的容器
docker compose stop                          # 停止，資料保留
docker compose start                         # 重新啟動
docker compose logs db                       # 查看資料庫紀錄
docker exec -it rag-db psql -U rag -d rag    # 進入資料庫下 SQL
docker compose down                          # 刪除容器，volume 保留
docker compose down -v                       # 連 volume 一起刪除，資料會全部消失
```

## 切塊（Chunking）

### 為什麼要切塊

1. **搜尋才準：** 一整份文件只變成一個向量，多個主題的意思會混在一起，很難對應到具體問題。
2. **模型有長度限制：** 一次塞不下整份文件，而且無關內容越多，回答越容易偏掉。
3. **來源才清楚：** 回答可以指出依據的是哪一段。

### 目前做法：依句子切塊 + 重疊

`chunker.py` 分兩個階段：

1. **切成小單位：** 先依 `。！？；` 和換行切成句子。句子超過 `size` 時改依 `，、` 和空白切；還是太長才按字數切。
2. **合併成文字塊：** 依序把句子放進同一塊，再放會超過 `size` 就換下一塊。下一塊開頭會重複上一塊結尾的完整句子，總長不超過 `overlap`。

```text
句子：A。B。C。D。E。
第 1 塊：A。B。C。
第 2 塊：      C。D。E。   ← C 是重疊
```

如果沒有重疊，相關內容剛好被分到兩塊時，兩塊的語意都不完整，也就更難被搜尋到。

`size=500`、`overlap=100` 是起始值，還沒有用題庫比較其他設定。

### 為什麼不用固定字數

按固定字數切，可能從句子中間切開。依句子切之後，銀行法 85 塊中有 68 塊結尾是完整句子。其餘 17 塊的結尾不是句末標點，可能原因是每頁分開切塊或標題、款項，還沒逐一確認。

PDF 的換行是版面造成的，常在句子中間，所以解析時會去掉；Word 和文字檔的換行則保留，當成段落邊界。

實作時有三個邊界要處理：

- `overlap >= size` 時視為錯誤。
- 重疊加上新句子超過 `size` 時，優先保留新句子，每塊一定包含新內容，迴圈才不會卡死。
- 句子比 `overlap` 長時不會重疊，因為不想把句子切開。

## Ollama 模型

### 什麼是 Ollama

Ollama 負責下載模型並在本機執行，同時在 `http://127.0.0.1:11434` 提供 API。程式不必處理 GPU 和模型載入的細節。

### 為什麼需要兩個模型

| | 向量模型 `bge-m3` | 回答模型 `qwen3:8b` |
|---|---|---|
| 工作 | 把文字變成向量，用來搜尋 | 閱讀資料後寫出回答 |
| 開發者 | 北京智源人工智慧研究院（BAAI） | 阿里巴巴 Qwen 團隊 |
| 參數量 | 5.67 億 | 82 億 |
| 上下文長度 | 8192 | 40960 |
| 輸出 | 1024 維向量 | 文字 |
| 量化 | F16 | Q4_K_M |
| 授權 | MIT | Apache 2.0 |
| 下載大小 | 1.2 GB | 約 5.2 GB |
| 載入後占用 GPU | 0.7 GB | 5.6 GB |

### 選擇原因

**`bge-m3`**

- 支援多語言，適合中英文混合的文件。
- 上下文長度 8192，處理 500 字的文字塊綽綽有餘。
- 實測語意搜尋有效：問「一年可以請幾天休假？」，沒有完全相同的字詞也找到了「十四天特休假」。

**`qwen3:8b`**

- 中文能力佳，大小也符合硬體：RTX 3060 Ti 只有 8 GB 記憶體，它可以完整放進 GPU。
- 和 `bge-m3` 同時載入共約 6.3 GB，仍在 8 GB 內。如果選更大的模型，部分運算會落到 CPU，速度會明顯變慢。
- 授權為 Apache 2.0。

量化（Q4_K_M）是降低權重精度來縮小模型，精度略降，但記憶體需求少很多，一般顯卡才跑得動。

### 實測速度

環境：RTX 3060 Ti 8 GB、32 GB RAM。

| 項目 | 第一次（含載入模型） | 模型載入後 |
|---|---|---|
| 向量化 | 1.89 秒（8 筆） | 0.07 秒（8 筆） |
| 回答 | 57.3 秒（環境測試） | 0.46～0.72 秒（1 句），約 73 tokens/秒 |

環境測試中的 57.3 秒是第一次載入，和後面的數字不是同一題，只能當參考。實際回答會更長，時間也會增加。

### 開發時要注意

- **關閉思考模式：** `qwen3:8b` 預設會先輸出思考過程，程式裡用 `think=False` 關閉。
- **上下文長度：** 模型上限是 40960，但 Ollama 預設只開 4096，超過可能被截斷。專案用 `num_ctx` 設為 6144，原因見「搜尋與回答」。
- **簡體字：** 模型可能混用簡體字，所以提示詞要指定繁體中文。

## 文件匯入

`ingest.py` 的流程：

1. 計算檔案的 SHA-256。內容相同就略過，避免重複匯入。
2. `document_parser.py` 取出文字，PDF 保留頁碼，Word 也會讀表格。
3. `chunker.py` 切塊。
4. 用 `bge-m3` 每 32 塊向量化一批。
5. 在同一個交易內寫入 `documents` 和 `chunks`，失敗時不會留下只寫一半的文件。

資料表：

| 資料表 | 內容 |
|---|---|
| `documents` | 一份文件一筆：檔名、內容雜湊、匯入時間 |
| `chunks` | 一塊文字一筆：所屬文件、順序、頁碼、內容、1024 維向量 |

`chunks.document_id` 設了 `ON DELETE CASCADE`，刪除文件時文字塊會一起刪除。

目前沒有建向量索引，每次搜尋都會逐筆比對。資料量小時這樣最準確，文件變多再評估 HNSW 索引。

切塊是在每頁內各自進行，所以 PDF 跨頁的句子會被切開。TXT 會先試 UTF-8，再試 Big5（cp950）。

## 搜尋與回答

`rag.py` 的流程：

1. 用 `bge-m3` 把問題轉成向量。
2. 用 pgvector 的餘弦距離（`<=>`）找出最接近的 4 塊（`TOP_K`）。
3. 排除距離超過 0.6 的文字塊（`MAX_DISTANCE`）。全部被排除時直接回答「文件中找不到相關資料。」，不呼叫模型。
4. 把文字塊和問題交給 `qwen3:8b`，以串流方式輸出回答。

防止亂答有兩層：距離門檻擋掉明顯無關的問題，系統提示詞要求模型只能根據資料回答。

提示詞裡的文件內容放在 `<source>` 標籤內，並要求模型把資料當參考文字，不當指令。這可以降低提示詞注入的風險，但不是絕對保證。

### 為什麼 `num_ctx` 是 6144

| `num_ctx` | 回答模型占用 GPU | 兩個模型能否同時留在 GPU | 問一題的時間 |
|---|---|---|---|
| 8192 | 6.2 GB | 不行，每題都要重新載入 | 約 8 秒 |
| 6144 | 5.9 GB | 可以 | 多數 0.3～0.8 秒，偶爾 2～3 秒；第一題載入模型約 10 秒（皆為短回答） |

測試時 GPU 也被其他程式占用，總用量約 7.6 / 8 GB。開啟更多吃 GPU 的程式時，可能再次發生重新載入，問題會變慢。

目前最長的提示詞（4 塊共 2000 字）用了 1766 tokens，遠低於 6144。

### 距離門檻的限制

測試題中，有答案的最近距離是 0.162～0.442，沒答案的是 0.421～0.612，兩者有重疊，只靠門檻分不開。例如「產假有幾天？」的 0.421 比部分有答案的問題還近，這類問題是靠模型判斷拒答。

0.6 只用來擋掉明顯無關的問題，而且會受文件影響：加入銀行法後，「台積電今天股價多少？」的距離從 0.613 降到 0.569，不再被門檻擋下，改由模型拒答。換成其他文件要重新檢查。

## 後端 API

啟動：

```powershell
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
```

啟動後可在 <http://127.0.0.1:8000/docs> 開啟 Swagger 測試 API。

| 方法 | 路徑 | 功能 | 成功 | 失敗 |
|---|---|---|---|---|
| GET | `/api/health` | 檢查資料庫、Ollama、模型是否就緒 | 200 | 503，並列出缺少的項目 |
| GET | `/api/models` | 預設模型和可選的回答模型 | 200 | |
| GET | `/api/documents` | 列出文件 | 200 | |
| POST | `/api/documents` | 上傳文件，欄位名稱 `file` | 201 | 413 太大、415 類型不支援、422 讀不到文字、503 Ollama 無法連線 |
| GET | `/api/documents/{id}` | 預覽系統讀到的文字 | 200 | 404 |
| DELETE | `/api/documents/{id}` | 刪除文件和文字塊 | 204 | 404 |
| POST | `/api/chat` | 提問，內容 `{"question": "..."}`，可加 `"backend"`、`"model"` 指定模型 | 200 串流 | 422 問題空白、超過 2000 字或模型不能用 |
| GET | `/api/questions?q=&limit=50` | 問答紀錄和花費時間，最新的排前面；`q` 搜尋問題或回答，`limit` 1～500 | 200 | 422 |

同內容的檔案再次上傳時不會重複寫入，回傳既有文件並標示 `"duplicate": true`。

### 串流格式

`/api/chat` 用 SSE（Server-Sent Events）格式，回答邊產生邊送出，不必等全部完成。依序會收到：

```text
data: {"type":"sources","sources":[{"id":1,"filename":"報價單.pdf","page":1,"content":"...","distance":0.162}]}
data: {"type":"token","text":"雲端"}
data: {"type":"token","text":"主機"}
data: {"type":"done","cited":[1],"timing":{"search_ms":85,"first_token_ms":610,"total_ms":2140},"question_id":12}
```

`cited` 是回答實際引用的來源編號，由回答中的 `[1]` 解析而來。`timing` 是花費時間（毫秒），從後端收到問題開始算：`search_ms` 找完段落、`first_token_ms` 模型送出第一段文字、`total_ms` 回答完成。發生錯誤時會收到 `{"type":"error","message":"...","timing":{...}}`。

### 問答紀錄

每次提問，不論完成、出錯或按停止，後端都會在 `questions` 表存一筆：問題、回答、使用的模型、狀態（`done`／`error`／`stopped`）、引用的來源檔名和頁碼、上面三個時間。查看方式：

```powershell
# 用 API
curl.exe http://127.0.0.1:8000/api/questions?limit=10

# 直接查資料庫
docker exec -it rag-db psql -U rag -d rag -c "SELECT id, left(question, 30), model, status, search_ms, first_token_ms, total_ms, created_at FROM questions ORDER BY id DESC LIMIT 10;"
```

前端的「問答歷史」分頁讀的就是這張表，可以搜尋；點一筆紀錄時，如果問答頁畫面上還有那個回答就跳過去，沒有就在原地展開完整回答。問答頁畫面上的對話另外存在瀏覽器的 localStorage，「清除畫面」只清掉這份，不會刪除資料庫的紀錄。

`EventSource` 只支援 GET，而提問要用 POST，所以前端要用 `fetch` 讀取串流。

## 前端

`frontend/` 使用 Vue 3、TypeScript 和 Vite，沒有另外裝 UI 套件。

| 檔案 | 功能 |
|---|---|
| `src/api.ts` | 呼叫後端、定義型別、讀取串流 |
| `src/App.vue` | 版面，連接左右兩個面板 |
| `src/components/DocumentPanel.vue` | 上傳、文件列表、刪除 |
| `src/components/ChatPanel.vue` | 提問、串流回答、引用來源 |
| `src/components/HistoryPanel.vue` | 問答歷史，讀資料庫的紀錄、搜尋 |
| `src/components/DocumentPreview.vue` | 預覽系統讀到的文件內容 |
| `src/chatHistory.ts` | 問答頁畫面上的對話，存在瀏覽器 |
| `src/style.css` | 樣式，支援深色模式和手機寬度 |

設計重點：

- **Vite proxy：** 前端呼叫 `/api` 時由 Vite 轉給 FastAPI，瀏覽器看到的是同一個來源，所以後端不必設定 CORS。
- **串流拆包：** 網路一次送來的資料可能只有半個事件，所以未完成的部分留在 `buffer`，等下一批資料接起來再解析。
- **中文輸入：** 注音選字時按 Enter 會帶 `isComposing`，此時不送出問題。
- **避免 XSS：** 不使用 `v-html`。回答用文字和引用按鈕分別渲染，文件裡的 HTML 只會顯示成文字。
- **只顯示引用來源：** 後端的 `cited` 決定顯示哪些來源，沒被引用的搜尋結果不會列出。
- **刪除確認：** 用同一列的「確定刪除」按鈕，不跳瀏覽器對話框。

## 評估結果

`eval_rag.py` 用固定題目測試，題目根據 `samples/` 的文件（`銀行法.pdf` 是真實法條，其餘是虛構文件）：

| 項目 | 結果 |
|---|---|
| 搜尋命中正確文件 | 19/19 |
| 回答包含正確答案 | 19/19 |
| 文件沒有答案時正確拒答 | 5/5 |
| 文件內的惡意指令被忽略 | 通過 |

題庫有 12 題虛構文件題、7 題銀行法題。銀行法這題的標準答案原本寫錯（第 47 條），對照 PDF 後確認第 46 條才對，已修正。

這只是冒煙測試：題目是配合文件寫的，答案大多在單一段落，也不是獨立的測試集。這不代表真實文件也有 100% 準確率。還沒測過跨段落推論和表格。

範例文件放在獨立的 `rag_eval` 資料庫，不會和自己上傳的文件混在一起。

```powershell
$env:RAG_DB_URL = "postgresql://rag:rag_dev_only@127.0.0.1:5432/rag_eval"
.\.venv\Scripts\python.exe eval_rag.py
Remove-Item Env:RAG_DB_URL
```

### 切塊方式比較

用銀行法的 5 題定義題，比較兩種切塊方式下，正確條文在搜尋結果的排名：

| 題目 | 固定字數 | 依句子 |
|---|---|---|
| 商業銀行 | 2 | 2 |
| 銀行 | 1 | 1 |
| 信託投資公司 | 1 | 2 |
| 專業銀行 | 1 | 1 |
| 銀行負責人 | 1 | 1 |

依句子切塊在這 5 題沒有提升排名，「信託投資公司」還從第 1 名變第 2 名。它的好處是文字塊比較完整，對搜尋準確度的影響要用更大的題庫才能判斷。

## 模型切換

### 在網頁上切換

問答頁上方的「回答模型」選單會列出：

- Ollama 已下載、能回答問題的模型（標示「本機」）。向量模型 `bge-m3` 不能回答，不會列出。
- 有開啟 Claude 而且已安裝 Claude Code CLI 時，加上 Claude haiku、sonnet、opus（標示「雲端」）。**預設不開啟**，因為會把文件段落傳到雲端，也可能用掉訂閱額度或產生 API 費用。要開啟時，啟動後端前設定 `$env:ENABLE_CLAUDE_CLI = "1"`。

每次提問都用當下選的模型，回答下方和問答歷史會標出是哪個模型回答的。選擇存在瀏覽器，下次開啟還是同一個。想多一個本機模型，用 `ollama pull 模型名稱` 下載後重新整理頁面即可。

後端只接受清單裡的模型，其他名稱回 422，避免讓 Ollama 去下載任意模型。向量模型不能在網頁上換，原因見本節最後。

### 用環境變數設定預設值

選單的預設選項，以及沒有指定模型時用的模型，由環境變數決定，啟動後端前設定：

| 變數 | 預設值 | 說明 |
|---|---|---|
| `LLM_BACKEND` | `ollama` | `ollama` 或 `claude_cli` |
| `OLLAMA_MODEL` | `qwen3:8b` | Ollama 回答模型 |
| `CLAUDE_MODEL` | `haiku` | Claude CLI 使用的模型 |
| `ENABLE_CLAUDE_CLI` | `0` | 設成 `1` 才會在選單列出 Claude；`LLM_BACKEND` 是 `claude_cli` 時自動開啟 |
| `EMBED_MODEL` | `bge-m3` | 向量模型 |
| `EMBED_DIM` | `1024` | 向量維度，要和向量模型一致 |
| `RAG_DB_URL` | 本機資料庫 | 資料庫連線字串 |

```powershell
$env:LLM_BACKEND = "claude_cli"
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
```

使用 `claude_cli` 時要注意：

- **資料不再只留在本機：** 搜尋到的文字和問題會傳到 Anthropic。向量化仍在本機，所以還是需要 Ollama。
- **沒有逐字串流：** CLI 會等全部完成才一次回傳。
- **工具已關閉：** 文件內容不可信，所以用 `--tools ""` 關閉所有工具，並在空資料夾執行，避免文件裡的指令讓 CLI 讀檔或執行程式。

換向量模型後，舊向量不能和新向量比較，資料表的維度也可能不同，必須重建資料表並重新匯入所有文件。

## 自動測試

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
docker compose up -d
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python.exe -m pytest
```

共 56 個測試，約 3 秒跑完。

| 檔案 | 內容 |
|---|---|
| `tests/test_chunker.py` | 句子邊界、重疊、長句、不合法參數 |
| `tests/test_parser.py` | 文字編碼、Word 表格、PDF 頁碼、掃描檔 |
| `tests/test_api.py` | 上傳、刪除、串流、引用、健康檢查、模型切換、斷線 |

- **模型是假的：** 不需要 GPU 或 Ollama。假的向量用字元雜湊產生，只測流程，不測回答品質。
- **資料庫是真的：** 使用獨立的 `rag_test`，不會動到正式資料。pgvector 的行為要用真的資料庫才測得出來。

`eval_rag.py` 則相反，使用真實模型評估回答品質，需要先匯入 `samples/`。

## 測試資料

`samples/` 除了 `銀行法.pdf` 是真實法條，其餘都是自動產生的**虛構文件**，內容和真實公司無關：

| 檔案 | 測試目的 | 結果 |
|---|---|---|
| `員工手冊_utf8.txt` | 長文字切塊 | 5 塊，每塊 260～500 字 |
| `公告_big5.txt` | Big5 編碼 | 1 塊，中文正確 |
| `福利補助辦法.docx` | Word 段落與表格 | 1 塊，表格有讀到 |
| `報價單.pdf` | 多頁 PDF 與頁碼 | 2 塊，頁碼 1、2 正確 |
| `銀行法.pdf` | **真實法條**，來自全國法規資料庫 | 85 塊，平均 375 字 |
| `掃描檔模擬.pdf` | 沒有文字的 PDF | 依設計拒絕並顯示原因 |
| `停車場公告.txt` | 文件內藏惡意指令 | 模型忽略指令，正常回答 |

重複匯入同一份檔案也實測過，會略過。

此外，`check_env.py` 裡有**手寫的 3 句假資料**，不是從真實文件取得，也還沒做過正式的品質評估：

```python
texts = ["員工每年有十四天特休假", "公司地址在台中市西屯區", "報銷差旅費需要附上發票"]
question = "一年可以請幾天休假？"
```

這份測試只能確認環境能動：模型能執行、pgvector 能搜尋、流程走得通。它**不能**證明系統對真實文件的準確度。

測試用的是暫存資料表（`CREATE TEMP TABLE`），連線結束就消失，資料庫裡不會留下資料。

實測結果（距離越小越接近）：

| 距離 | 句子 |
|---|---|
| 0.291 | 員工每年有十四天特休假 |
| 0.521 | 報銷差旅費需要附上發票 |
| 0.622 | 公司地址在台中市西屯區 |

模型回答：「一年可以請十四天休假。」

## 執行方式

前置需求：Python 3.11、Node.js、Docker Desktop、Ollama。第一次使用先做下面的「第一次安裝」。

### 要開的東西和順序

| 順序 | 服務 | 位址 | 為什麼要先開 |
|---|---|---|---|
| 1 | Docker Desktop | | 資料庫容器要靠它執行 |
| 2 | 資料庫容器 `rag-db` | 127.0.0.1:5432 | 後端啟動時會連資料庫建立資料表 |
| 3 | Ollama | 127.0.0.1:11434 | 上傳和提問都要用向量模型；用 Claude 回答也一樣 |
| 4 | 後端 FastAPI | 127.0.0.1:8000 | 前端的 `/api` 請求會轉到這裡 |
| 5 | 前端 Vite | 127.0.0.1:5173 | 瀏覽器開這個 |

前三項沒開，後端還是能啟動，但上傳或提問時會出錯。

### 方法一：一鍵啟動（建議）

```powershell
cd rag_project
.\start.ps1
```

腳本會依序檢查並啟動上面五項，已經在執行的會略過。後端和前端各開一個新視窗，最後做健康檢查並開啟瀏覽器。

### 方法二：手動啟動

1. 開啟 **Docker Desktop**，等它顯示 Engine running。
2. 開啟 **Ollama**（開始功能表搜尋 Ollama，啟動後會出現在右下角系統匣）。
3. 終端機 1：啟動資料庫和後端。

   ```powershell
   cd rag_project
   docker compose up -d
   $env:PYTHONUTF8 = "1"
   .\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
   ```

   看到 `Uvicorn running on http://127.0.0.1:8000` 就是成功，這個視窗不要關。

4. 終端機 2：啟動前端。

   ```powershell
   cd rag_project\frontend
   npm run dev
   ```

   看到 `Local: http://127.0.0.1:5173/` 就是成功。

5. 開啟 <http://127.0.0.1:5173>。

### 確認每一項都正常

| 檢查 | 方法 | 正常結果 |
|---|---|---|
| Docker | `docker ps` | 列表中有 `rag-db` |
| Ollama | `ollama list` | 有 `bge-m3` 和 `qwen3:8b` |
| 後端整體 | 開啟 <http://127.0.0.1:8000/api/health> | `"status": "ok"` |
| 前端 | 開啟 <http://127.0.0.1:5173> | 左側顯示文件清單，上方有回答模型選單 |

健康檢查回 `degraded` 時，看 JSON 哪一項有問題：`database` 是 `false` 代表資料庫沒開，`ollama` 是 `false` 代表 Ollama 沒開，`missing_models` 列出還沒下載的模型。

### 關閉

1. 在後端和前端的視窗按 `Ctrl + C`，或直接關掉視窗。
2. 停止資料庫：`docker compose stop`。資料存在 Docker volume，下次啟動還在。
3. Docker Desktop 和 Ollama 可以從系統匣結束。

不要用 `docker compose down -v`，`-v` 會刪掉資料庫裡的所有文件。

### 常見問題

| 狀況 | 原因和處理 |
|---|---|
| `docker` 指令出現 `failed to connect to the docker API` | Docker Desktop 還沒開或還在啟動，等它顯示 Engine running |
| 上傳時顯示「模型服務無法使用」 | Ollama 沒開，或沒下載 `bge-m3` |
| 回答模型選單沒出現 | 後端沒開，或 Ollama 和 Claude CLI 都不能用 |
| 選單裡沒有 Claude | 預設不開啟，要設 `$env:ENABLE_CLAUDE_CLI = "1"` 再啟動後端；也可能是沒安裝 Claude Code CLI |
| `Port 5173 is in use` | 前端已經開過一次，用原本那個視窗，或關掉它再重開 |
| `address already in use`（8000） | 後端已經開過一次 |
| pytest 顯示連不到資料庫 | 先 `docker compose up -d` |
| `.\start.ps1` 無法執行，說系統已停用指令碼 | 執行一次 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

### 第一次安裝

```powershell
git clone https://github.com/chen-hung-lun/rag_project.git
cd rag_project

# 1. 建立虛擬環境並安裝套件
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. 啟動資料庫
docker compose up -d

# 3. 下載模型（若 ollama 指令無效，重開終端機）
ollama pull bge-m3
ollama pull qwen3:8b

# 4. 測試環境
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python.exe check_env.py

# 5. 安裝前端套件
cd frontend
npm install
```

## 檔案結構

```text
rag_project/
├── check_env.py         環境測試
├── chunker.py           切塊
├── config.py            模型、資料庫、切塊設定
├── llm.py               回答模型後端切換
├── db.py                資料庫連線與資料表
├── document_parser.py   從檔案取出文字
├── ingest.py            文件匯入流程
├── rag.py               搜尋與回答
├── eval_rag.py          固定題目評估
├── api.py               FastAPI 後端
├── frontend/            Vue 3 前端
├── tests/               pytest 自動測試
├── requirements-dev.txt 測試用套件
├── samples/             虛構的測試文件
├── docker-compose.yml   資料庫容器設定
├── start.ps1            一鍵啟動
├── requirements.txt     Python 套件清單
├── .gitignore           不進 Git 的檔案
├── README.md            本文件
├── PROJECT_OVERVIEW.md  專案總覽（另有英文版 .en.md）
└── .venv/               虛擬環境，不進 Git
```

## 已知限制

- 掃描版 PDF 沒有文字層，需要 OCR，目前不支援。
- 目前只做向量搜尋，人名、型號這類精確字詞可能找不準。
- `rag_dev_only` 是本機開發密碼，不可用於對外部署。
- API 沒有登入驗證，只綁定 `127.0.0.1`，不可直接對外開放。
- 切塊在每頁內各自進行，跨頁的句子會被切開。
- 文件匯入後，再改切塊方式不會自動更新，要重新匯入。
- 每次提問都是獨立的，沒有對話記憶，無法處理「那國外呢？」這類追問。問答紀錄存在瀏覽器，換瀏覽器或清除網站資料後就會消失。
- 注音 Enter 是用程式模擬事件測試，沒有用真實的注音輸入法測過。
- 淺色模式、後端離線時的畫面還沒實際檢查。

## 授權

[MIT License](LICENSE)
