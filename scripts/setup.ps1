# Configuración inicial TennisAI (Windows)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"

Write-Host "=== TennisAI Setup ===" -ForegroundColor Cyan

if (-not (Test-Path (Join-Path $Backend "venv"))) {
    Write-Host "Creando entorno virtual..."
    python -m venv (Join-Path $Backend "venv")
}

$Python = Join-Path $Backend "venv\Scripts\python.exe"
& $Python -m pip install -r (Join-Path $Backend "requirements-train.txt")
& $Python (Join-Path $Backend "scripts\setup_project.py")

Write-Host "`nFrontend:" -ForegroundColor Yellow
Write-Host "  cd frontend"
Write-Host "  npm install"
Write-Host "  npm run dev"

Write-Host "`nAPI:" -ForegroundColor Yellow
Write-Host "  cd backend"
Write-Host "  .\venv\Scripts\activate"
Write-Host "  uvicorn api:app --reload"
