# Installs Ollama on D:, keeps all model files on D:, and downloads the two models the app uses.
#   powershell -ExecutionPolicy Bypass -File setup_ollama.ps1            (default: qwen2.5:7b, fits the RTX 2060 6GB)
#   powershell -ExecutionPolicy Bypass -File setup_ollama.ps1 -ChatModel qwen2.5:3b   (smaller / faster)
param([string]$ChatModel = "qwen2.5:7b", [string]$EmbedModel = "nomic-embed-text")
$ErrorActionPreference = "Stop"
$dir = "D:\Ollama"; $models = "D:\Ollama\models"
New-Item -ItemType Directory -Force $dir, $models | Out-Null
[Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $models, "User")   # model files live on D:
$env:OLLAMA_MODELS = $models

$exe = Join-Path $dir "ollama.exe"
if (-not (Test-Path $exe) -and -not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    $setup = Join-Path $dir "OllamaSetup.exe"
    Write-Host "Downloading Ollama installer (~1.5 GB) to $setup ..."
    Invoke-WebRequest "https://ollama.com/download/OllamaSetup.exe" -OutFile $setup
    Write-Host "Installing to $dir ..."
    Start-Process $setup -ArgumentList "/DIR=$dir", "/VERYSILENT", "/NORESTART" -Wait
}
if (-not (Test-Path $exe)) { $exe = (Get-Command ollama).Source }

if (-not (Get-Process ollama -ErrorAction SilentlyContinue)) {
    Start-Process $exe -ArgumentList "serve" -WindowStyle Minimized
    Start-Sleep 4
}
Write-Host "Pulling $ChatModel and $EmbedModel (models are stored in $models) ..."
& $exe pull $ChatModel
& $exe pull $EmbedModel
Write-Host "`nDone. Start the app with start.bat. If you chose a different chat model, set CHAT_MODEL in backend\.env"
