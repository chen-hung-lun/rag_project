"""專案設定集中在這裡，可用環境變數覆寫。

有 os.getenv 的項目可以在啟動前用環境變數修改，例如：
    $env:LLM_BACKEND = "claude_cli"
其他項目要直接改這個檔案。
"""
import os

# 回答模型的後端：ollama（本機）或 claude_cli（Claude Code CLI）
LLM_BACKEND = os.getenv("LLM_BACKEND", "ollama").lower()

# 換向量模型後要同步調整維度，並重新匯入所有文件
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "haiku")
# Claude 會把檢索到的段落傳到雲端，也可能用掉訂閱額度或產生費用，所以預設不放進選單。
# 要使用時設 $env:ENABLE_CLAUDE_CLI = "1"；LLM_BACKEND 設成 claude_cli 時也會自動開啟
ENABLE_CLAUDE_CLI = os.getenv("ENABLE_CLAUDE_CLI", "0") == "1" or LLM_BACKEND == "claude_cli"

# 本機開發用的密碼，和 docker-compose.yml 一致；正式環境要改用環境變數
DB_URL = os.getenv("RAG_DB_URL", "postgresql://rag:rag_dev_only@127.0.0.1:5432/rag")

# 切塊：每塊最多 500 字，相鄰塊重疊約 100 字（見 chunker.py）
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
# 每次送給向量模型的段數
EMBED_BATCH_SIZE = 32

MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# 每個問題取最相近的 4 塊；距離超過 0.6 視為無關（見 rag.py）
TOP_K = 4
MAX_DISTANCE = 0.6
# 8192 會讓兩個模型在 8 GB GPU 放不下，每題都要重新載入
CHAT_NUM_CTX = 6144
