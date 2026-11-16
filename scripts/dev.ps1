# Starts the API (:8000) and the web app (:3000) in two windows.
# Prereq (once):  cd web; npx -y clerk@latest auth login; npx -y clerk@latest link --app <app_id>; npx -y clerk@latest env pull
$root = Split-Path $PSScriptRoot -Parent
if (-not (Test-Path "$root\web\.env.local")) {
    Write-Warning "web\.env.local is missing - run the Clerk CLI steps above first, otherwise sign-in and the API's token check won't work."
}
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; .venv\Scripts\python.exe -m uvicorn api.main:app --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\web'; npm run dev"
Write-Host "API  -> http://127.0.0.1:8000/docs`nWeb  -> http://localhost:3000"
