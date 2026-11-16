# Commands cheat sheet

Every command you need, in the order you'll use them. All commands are for **Windows PowerShell**, run from the project folder unless a line says otherwise.

> The project folder is the one that contains `api`, `evalguard`, `web` and `README.md`.

---

## 1. One-time setup

You need these installed first: **Python 3.11**, **Node.js 20 or newer**, and [**uv**](https://docs.astral.sh/uv/) (a fast Python installer). Check them:

```powershell
node --version        # should say v20 or higher
uv --version
```

### 1.1 Backend (Python)

```powershell
uv venv --python 3.11 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
```

What this does: makes a private Python environment in `.venv` and installs everything the backend needs. It downloads a lot (the search model library is large), so the first run takes several minutes.

No `uv`? This does the same with plain Python:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 1.2 Settings file

```powershell
copy .env.example .env
```

Then open `.env` and paste your OpenRouter key after `OPENROUTER_API_KEY=`. Get a key at <https://openrouter.ai/keys>. See [every setting explained](TECHNICAL.md#13-settings-reference).

### 1.3 Frontend (the web app)

```powershell
cd web
npm install
copy .env.example .env
cd ..
```

### 1.4 Sign-in with Clerk

Clerk is the sign-in service. This links the web app to your Clerk application and writes its keys into `web\.env.local`.

```powershell
cd web
npx -y clerk@latest auth login                       # opens a browser, sign in to Clerk
npx -y clerk@latest link --app <your_clerk_app_id>   # find the id in the Clerk dashboard
npx -y clerk@latest env pull                         # writes web\.env.local
cd ..
```

Useful extras:

```powershell
npx -y clerk@latest doctor            # checks the Clerk setup and tells you what is wrong
npx -y clerk@latest config pull       # shows your Clerk sign-in settings
```

---

## 2. Start and stop the app

### Start both parts with one command

```powershell
.\scripts\dev.ps1
```

This opens two windows: the **API** on port 8000 and the **web app** on port 3000. Then open <http://localhost:3000> and sign in.

### Start them by hand (two terminals)

Terminal 1, the API:

```powershell
.venv\Scripts\python.exe -m uvicorn api.main:app --port 8000
```

Terminal 2, the web app:

```powershell
cd web
npm run dev
```

Add `--reload` to the API command while you are changing Python code, so it restarts by itself.

### Check that they are running

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health     # should print: status ok
Invoke-WebRequest http://localhost:3000/sign-in -UseBasicParsing | Select-Object StatusCode   # should say 200
```

### Stop them

Close the two windows, or stop by port:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
Get-NetTCPConnection -LocalPort 3000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

---

## 3. Run evaluations from the terminal

You can do all of this in the web app too. The terminal is handy for scripts and checks.

```powershell
# One industry
.venv\Scripts\python.exe scripts\run_eval.py --domain hr

# Every industry, one after another (about 1.5 hours with free models, roughly 10 minutes each)
.venv\Scripts\python.exe scripts\run_eval.py --all-domains

# Give the run a name, or choose which earlier run to compare with
.venv\Scripts\python.exe scripts\run_eval.py --domain legal --run-name "after policy update"
.venv\Scripts\python.exe scripts\run_eval.py --domain legal --baseline-id <run id>
```

Industry names to use after `--domain`: `education`, `healthcare`, `banking_finance`, `legal`, `ecommerce`, `it_support`, `hr`, `travel_hospitality`.

The terminal runner uses the standard question set and the default prompt. For trick questions, other prompts, or model comparisons, use the web app (Evaluate and Experiments pages).

### Make a fake "quality drop" for a demo

```powershell
.venv\Scripts\python.exe scripts\simulate_drift.py --domain hr
```

This takes the latest real run, creates a deliberately bad copy, and runs the drift check on it. Simulated runs are labelled "simulated" and are never used as a baseline.

---

## 4. Check your work

### Backend tests

```powershell
.venv\Scripts\python.exe -m pytest tests -q
```

Expected: all tests pass (61 at the time of writing). Run one file:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_lab.py -q
```

### Check the question files

```powershell
py -I scripts\validate_dataset.py                  # every industry
py -I scripts\validate_dataset.py hr legal         # only some
```

This confirms every expected keyword really appears in that industry's documents, there are no duplicate questions, and the trick questions are set up correctly. Run it after editing any `data\*\*.json` file.

### Frontend checks

```powershell
cd web
npx tsc --noEmit        # type check
npm run lint            # style and mistake check
npm run build           # full production build (needs the Clerk keys from step 1.4)
cd ..
```

---

## 5. Save your work to GitHub

```powershell
git status                       # what changed
git add -A                       # include everything
git commit -m "Describe what you changed"
git push                         # needs a GitHub login or token with write access
```

Never commit `.env` or `web\.env.local`. They hold your keys and are already ignored by git.

---

## 6. Fixing common problems

| What you see | What it means | What to do |
| --- | --- | --- |
| `ModuleNotFoundError` when running Python | You used the wrong Python | Use `.venv\Scripts\python.exe` exactly as shown above |
| Web app says "Clerk keys are missing" | `web\.env.local` doesn't exist | Run the Clerk steps in 1.4, then restart the web app |
| Web app shows "Cannot reach the API" | The API isn't running | Start it (section 2) and check `/health` |
| API returns 401 | Your sign-in expired or is missing | Sign in again in the browser |
| API returns 403 "not on this workspace's allow-list" | `EVALGUARD_ALLOWED_USER_IDS` is set and your account is not in it | Add your Clerk user id, or remove the setting, then restart the API |
| API returns 503 "Auth is not configured" | The API can't find the Clerk key | Check `web\.env.local` exists, then restart the API |
| Run fails with "daily request limit" or `free-models-per-day` | The free AI quota for today is used up | Wait for 00:00 UTC, add credit to OpenRouter, or switch `LLM_PROVIDER` in `.env` |
| A page shows "Mock LLM active" | No real AI key is set, so scores are fake | Set `LLM_PROVIDER` and the key in `.env`, restart the API |
| "Port 8000 (or 3000) already in use" | An old copy is still running | Stop it with the commands in section 2 |
| First start is very slow, or mentions "offline mode is enabled" | The search model (about 90 MB) is downloading or blocked | Run once with `$env:HF_HUB_OFFLINE=0` set in that terminal before starting the API |
| Changes to `.env` don't show up | Settings are read when the API starts | Restart the API |
