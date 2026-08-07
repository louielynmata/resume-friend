# Resume Friend — Implementation Plan

## Context
A local-only personal productivity tool that automates resume + cover letter generation for job applications. The user pastes or links a job description, selects an AI provider (Claude / OpenAI / Ollama), picks a job type (Design or Development), and the app tailors a resume and cover letter based on pre-loaded personal model files (resume, writing style, transcript). Output is saved locally as `.docx` + `.pdf` and logged to a Notion database.

Key principles from flowchart:
1. Be truthful — only draw from the user's own resume
2. Adjust to improve ATS score (keyword-match the JD)
3. Match the user's writing style and humanize the output

---

## Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Backend | Python 3.12 + FastAPI | Best AI SDK support (anthropic, openai, ollama), python-docx, async-native, trivial to add auth middleware later |
| Frontend | Vite + React + TypeScript | Fast dev, TypeScript catches API shape mismatches, easy to extend |
| Document gen | python-docx + docx2pdf | Word-compatible .docx; PDF via MS Word COM on Windows 11 (requires Word installed) |
| Notion | notion-client (official Python SDK) | Free tier sufficient |
| AI providers | anthropic, openai, ollama (HTTP) | Abstracted behind a single common interface |
| Job scraping | requests + beautifulsoup4 | Extract JD text from a URL (best-effort; falls back to paste) |
| Config | pydantic-settings + .env | All critical values configurable via .env |

---

## Project Structure

```
resume-friend/
├── PLAN.md                      ← this file
├── AGENTS.md
├── backend/
│   ├── main.py                  # FastAPI app, CORS, router registration
│   ├── config.py                # pydantic-settings reads .env
│   ├── routers/
│   │   ├── generate.py          # POST /api/generate
│   │   ├── scrape.py            # POST /api/scrape-job
│   │   ├── model_files.py       # GET /api/model-files
│   │   └── notion.py            # POST /api/notion/log, GET /api/notion/jobs
│   ├── services/
│   │   ├── ai_service.py        # Unified Claude/OpenAI/Ollama interface
│   │   ├── document_service.py  # .docx builder + docx2pdf
│   │   ├── notion_service.py    # Notion API: log entry, read jobs
│   │   └── job_scraper.py       # URL → plain text
│   ├── schemas.py               # Pydantic request/response models
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/client.ts        # fetch wrapper
│   │   ├── components/
│   │   │   ├── StepJobInput.tsx      # Step 1: JD text or URL
│   │   │   ├── StepAIConfig.tsx      # Step 2: AI model + job type
│   │   │   ├── StepJobMeta.tsx       # Step 3: Company, position, salary…
│   │   │   └── StepResult.tsx        # Step 4: Output paths + Notion link
│   │   └── types.ts
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts           # /api proxy → localhost:8000
├── model_files/                 # Personal files — gitignored, user fills these in
│   ├── design_resume.txt        # PLACEHOLDER
│   ├── dev_resume.txt           # PLACEHOLDER
│   ├── instructions_prompt.txt  # PLACEHOLDER
│   ├── writing_examples.txt     # PLACEHOLDER
│   └── sait_transcript.txt      # PLACEHOLDER
├── outputs/                     # All generated documents saved here
├── .env                         # Gitignored — user fills in secrets
├── .env.example                 # Committed — shows all required keys
└── .gitignore
```

---

## .env Configuration (all critical values live here)

```env
# ── Personal ─────────────────────────────────────────────────────────────
OWNER_NAME=LouielynMata           # Used in output filenames
OWNER_EMAIL=louielynmata@gmail.com

# ── AI Providers ─────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=                # Claude (anthropic)
OPENAI_API_KEY=                   # ChatGPT
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:e4b           # Change if you switch local models

# ── Notion ────────────────────────────────────────────────────────────────
NOTION_TOKEN=                     # From Notion Integration settings
NOTION_DATABASE_ID=               # ID of the tracking database page

# ── Paths (change if you want outputs elsewhere) ──────────────────────────
MODEL_FILES_DIR=./model_files
OUTPUT_DIR=./outputs

# ── App ───────────────────────────────────────────────────────────────────
BACKEND_PORT=8000
FRONTEND_PORT=5173
```

---

## Application Flow

```
Step 1 — Job Input
  User pastes JD text OR enters a URL
  → URL path: POST /api/scrape-job → returns plain text
  → Both paths hand off the same plain-text JD

Step 2 — AI Config
  Select AI provider: Claude | OpenAI | Ollama
  Select Job Type:    Design | Development

Step 3 — Job Metadata (for Notion + file naming)
  Position*, Company*, Location, Salary Annual, Salary Hourly,
  Date of Job Posting, Contact Email (optional)

  → Click "Generate"

Step 4 — POST /api/generate (backend does):
  1. Load model files based on job type (design_resume.txt OR dev_resume.txt)
     + instructions_prompt.txt + writing_examples.txt + sait_transcript.txt
  2. Build system prompt (ATS-aware, truthful, humanized style)
  3. Call ai_service.py → AI provider → returns resume + cover letter text
  4. Build .docx files via document_service.py
  5. Convert to .pdf via docx2pdf (Windows/Word COM)
  6. Save to:
       outputs/{Company}_{Position}_{YYYY-MM-DD}/
         {OWNER_NAME}_Resume_{Position}.docx
         {OWNER_NAME}_Resume_{Position}.pdf
         {OWNER_NAME}_CoverLetter_{Position}.docx
         {OWNER_NAME}_CoverLetter_{Position}.pdf
     Note: Position is the value entered in Step 3, spaces removed
     Example: "Senior UX Designer" → SeniorUXDesigner
  7. POST /api/notion/log → create Notion DB row
  Returns: { output_folder, resume_path, cover_letter_path, notion_page_url }

Step 4 — Result view
  Shows: output folder path, download links, Notion page link
```

---

## Notion Database Schema

| Field | Type | Notes |
|---|---|---|
| Title | Title | "{Position} @ {Company}" |
| Company | Text | |
| Location | Text | |
| Salary Annual | Number | |
| Salary Hourly | Number | |
| Date of Job Posting | Date | |
| Date Submitted | Date | auto-set to today |
| Status | Select | Applied / Interview / Offer / Rejected |
| AI Used | Select | Claude / OpenAI / Ollama |
| ATS Use | Checkbox | always true when app generates |
| Contact Email | Email | optional |

---

## AI Service Abstraction

```python
# ai_service.py — all three providers implement the same call
async def generate(provider: str, system_prompt: str, user_prompt: str) -> str:
    # provider = "claude" | "openai" | "ollama"
```

- Claude → `anthropic.AsyncAnthropic`, model from config (default: claude-sonnet-4-6)
- OpenAI → `openai.AsyncOpenAI`, model from config (default: gpt-4o)
- Ollama → HTTP POST to `{OLLAMA_BASE_URL}/api/generate`, model = `{OLLAMA_MODEL}`

The system prompt is assembled from:
1. Core rules (truthful / ATS / humanize)
2. Chosen resume file (design or dev)
3. instructions_prompt.txt
4. writing_examples.txt (few-shot style)
5. sait_transcript.txt

---

## Auth-Ready Notes
- FastAPI: adding auth = wrap routers with `Depends(get_current_user)` — zero restructuring
- React: add `<AuthProvider>` + protected route HOC over the existing multi-step wizard
- Credentials stay in `.env` / config — no leakage risk on migration

---

## Run Instructions

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev      # → http://localhost:5173 (proxies /api to :8000)
```

---

## Verification Checklist
1. `backend/` starts, `/docs` (OpenAPI) loads at localhost:8000
2. Frontend loads at localhost:5173
3. Paste a sample JD → proceeds to Step 2
4. URL mode → scrapes a public job posting URL to text
5. Select Ollama + Development → Generate (no API key needed)
6. `outputs/` folder contains `.docx` and `.pdf` with correct naming
7. Notion DB has a new row with all fields populated
8. Test Claude and OpenAI providers (requires `.env` keys)
