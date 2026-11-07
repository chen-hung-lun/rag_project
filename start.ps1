# 一鍵啟動：Docker Desktop → 資料庫 → Ollama → 後端 → 前端 → 瀏覽器
# 用法：在 rag_project 資料夾執行 .\start.ps1
# 後端和前端會各開一個新視窗，關掉視窗就停止該服務。

# 不用 Stop：Windows PowerShell 5.1 會把外部程式的錯誤輸出當成例外
$ErrorActionPreference = "Continue"
$root = $PSScriptRoot

function Wait-Until([scriptblock]$check, [int]$seconds, [string]$name) {
    for ($i = 0; $i -lt $seconds; $i++) {
        if (& $check) { return }
        Start-Sleep -Seconds 1
    }
    throw "$name 在 $seconds 秒內沒有啟動，請手動檢查。"
}

function Test-Url([string]$url) {
    try {
        Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        # 回應 503 也代表服務有在跑
        return $null -ne $_.Exception.Response
    }
}

# 1. Docker Desktop：資料庫容器需要它
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "1/5 開啟 Docker Desktop..."
    $docker = @(
        "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe",
        "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $docker) { throw "找不到 Docker Desktop，請先安裝或手動開啟。" }
    Start-Process $docker
    Wait-Until { docker info *> $null; $LASTEXITCODE -eq 0 } 120 "Docker Desktop"
}
Write-Host "1/5 Docker Desktop 已就緒"

# 2. 資料庫容器（rag-db）
Set-Location $root
docker compose up -d *> $null
Wait-Until { docker exec rag-db pg_isready -U rag *> $null; $LASTEXITCODE -eq 0 } 60 "資料庫"
Write-Host "2/5 資料庫已就緒（127.0.0.1:5432）"

# 3. Ollama：向量模型一定要用到它
if (-not (Test-Url "http://127.0.0.1:11434/api/version")) {
    $ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe"
    if (Test-Path $ollama) { Start-Process $ollama } else { Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden }
    Wait-Until { Test-Url "http://127.0.0.1:11434/api/version" } 60 "Ollama"
}
Write-Host "3/5 Ollama 已就緒（127.0.0.1:11434）"

# 4. 後端（新視窗）
if (Test-Url "http://127.0.0.1:8000/api/health") {
    Write-Host "4/5 後端已經在執行"
} else {
    $backend = "Set-Location '$root'; `$env:PYTHONUTF8 = '1'; .\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $backend
    Wait-Until { Test-Url "http://127.0.0.1:8000/api/health" } 60 "後端"
    Write-Host "4/5 後端已就緒（127.0.0.1:8000）"
}

# 5. 前端（新視窗）
if (Test-Url "http://127.0.0.1:5173") {
    Write-Host "5/5 前端已經在執行"
} else {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\frontend'; npm run dev"
    Wait-Until { Test-Url "http://127.0.0.1:5173" } 60 "前端"
    Write-Host "5/5 前端已就緒（127.0.0.1:5173）"
}

# 健康檢查：列出缺少的模型或沒連上的服務
try {
    Invoke-RestMethod "http://127.0.0.1:8000/api/health" | Out-Null
    Write-Host "健康檢查：正常"
} catch {
    Write-Warning "健康檢查未通過，請開啟 http://127.0.0.1:8000/api/health 查看原因。"
}

Start-Process "http://127.0.0.1:5173"
