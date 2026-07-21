# Resume Friend

A local AI tool that generates tailored resumes and cover letters for job applications. Paste a job description (or drop a URL), pick an AI provider, and get a `.docx` + `.pdf` output named and organized automatically — plus a Notion row logged for tracking.

Inspired by and built in discussion with [Fernando C. B. Horta](https://github.com/fernandocbhorta). A link to his work will be posted once it is published.

---

## How It Works

```
1. Paste job description (text or URL)
2. Choose AI provider: Claude · OpenAI · Ollama (local)
3. Choose job type: Design or Development
4. Enter job details (company, position, salary, etc.)
     ↓
   AI reads your resume + instructions + writing style
     ↓
5. Independent QA reviewer corrects grammar and formatting
6. Validated outputs saved to:
   outputs/{Company}_{Position}_{Date}/
     {Name}_Resume_{Position}.docx + .pdf
     {Name}_CoverLetter_{Position}.docx + .pdf
7. Job logged to Notion database automatically after QA passes
```

**AI rules applied on every generation:**

- Truthful — only draws from your actual resume, never invents experience
- ATS-optimized — mirrors keywords from the job description where they match your background
- Humanized — matches your writing style from the examples you provide

> **Privacy:** Personal model files stay outside version control under the gitignored
> `models_personal/` directory. During generation, their contents are sent to the
> AI provider you select. Choose Ollama when you need the generation request to
> remain on your machine.

---

## Tech Stack

| Layer       | Technology                          |
| ----------- | ----------------------------------- |
| Backend     | Python 3.12 + FastAPI               |
| Frontend    | Vite 8 + React 19 + TypeScript 6    |
| Styling     | Tailwind CSS v4                     |
| Documents   | python-docx + docx2pdf              |
| Notion      | notion-client (official Python SDK) |
| AI: Claude  | anthropic SDK                       |
| AI: ChatGPT | openai SDK                          |
| AI: Local   | Ollama HTTP API                     |

---

## Project Structure

```
resume-friend/
├── .env                          ← your secrets (gitignored — copy from .env.example)
├── .env.example                  ← template for all config values
├── .gitignore
├── PLAN.md                       ← implementation plan and architecture decisions
│
├── backend/
│   ├── main.py                   ← FastAPI app, CORS, route registration
│   ├── config.py                 ← all settings via pydantic-settings + .env
│   ├── schemas.py                ← Pydantic request/response models
│   ├── routers/
│   │   ├── generate.py           ← POST /api/generate  (main endpoint)
│   │   ├── scrape.py             ← POST /api/scrape-job
│   │   ├── model_files.py        ← GET  /api/model-files
│   │   └── notion.py             ← GET  /api/notion/status
│   ├── services/
│   │   ├── ai_service.py         ← unified Claude / OpenAI / Ollama interface
│   │   ├── document_service.py   ← .docx builder + docx→pdf conversion
│   │   ├── qa_service.py         ← deterministic checks + AI reviewer/fixer
│   │   ├── qa_pipeline.py        ← bounded review, render, inspect, repair loop
│   │   ├── artifact_qa_service.py ← DOCX/PDF and visual validation
│   │   ├── notion_service.py     ← create Notion database rows
│   │   └── job_scraper.py        ← extract plain text from a job URL
│   └── requirements.txt
│
├── frontend/                     ← Vite + React app (see frontend/README.md)
│   └── src/
│       ├── App.tsx               ← 4-step wizard orchestrator
│       ├── types.ts              ← shared TypeScript types
│       ├── api/client.ts         ← typed fetch wrapper for backend
│       └── components/
│           ├── StepJobInput.tsx  ← Step 1: paste JD or scrape URL
│           ├── StepAIConfig.tsx  ← Step 2: AI provider + job type
│           ├── StepJobMeta.tsx   ← Step 3: company, position, salary…
│           └── StepResult.tsx    ← Step 4: output paths + Notion link
│
├── prompts/                      ← public application prompt templates
│   ├── system_prompt.md          ← identity-neutral writer prompt
│   ├── qa_prompt.md              ← grammar/format reviewer and fixer prompt
│   └── visual_qa_prompt.md       ← rendered PDF inspection prompt
│
├── models_personal/              ← your personal files (gitignored — fill these in)
│   ├── design_resume.md          ← your Design/UX resume
│   ├── dev_resume.md             ← your Developer resume
│   ├── instructions_prompt.md    ← generation rules (length, format, tone)
│   ├── writing_examples.md       ← 2-3 writing samples for style matching
│   └── school_transcript.md     ← education details, courses, and achievements
│
└── outputs/                      ← generated documents saved here (gitignored)
    └── {Company}_{Position}_{Date}/
        ├── {Name}_Resume_{Position}.docx
        ├── {Name}_Resume_{Position}.pdf
        ├── {Name}_CoverLetter_{Position}.docx
        └── {Name}_CoverLetter_{Position}.pdf
```

---

## Prerequisites

| Requirement              | Check                                                         |
| ------------------------ | ------------------------------------------------------------- |
| Python 3.12+             | `python --version`                                            |
| Node.js 18+              | `node -v`                                                     |
| Microsoft Word (for PDF) | Needed by docx2pdf on Windows — .docx always saves regardless |
| Ollama (optional)        | `ollama list` — only needed for local AI                      |

---

## Setup (One Time)

### 1. Copy and fill your `.env`

```powershell
copy .env.example .env
```

Open `.env` and fill in the values you need:

```env
OWNER_NAME="Your Name"      # exact display name used in documents and filenames
APP_MODEL_FILES_DIR=./prompts
MODEL_FILES_DIR=./models_personal
ANTHROPIC_API_KEY=           # for Claude
OPENAI_API_KEY=              # for ChatGPT
QA_PROVIDER=same             # same writer provider, or claude/openai/ollama
QA_VISUAL_ENABLED=true       # inspect rendered PDFs when available
NOTION_TOKEN=                # for Notion tracking
NOTION_DATABASE_ID=          # see Notion Setup section below
```

### 2. Set up your model files

The `models_personal/` directory is gitignored and must be created manually. The easiest way is to copy the provided identity-neutral example templates:

```powershell
# Windows
xcopy models_personal_example models_personal /E /I

# macOS / Linux
cp -r models_personal_example models_personal
```

Then open each file and replace the placeholder content with your own:

| File                     | What to put in it                                   |
| ------------------------ | --------------------------------------------------- |
| `design_resume.md`       | Your Design/UX resume (plain text)                  |
| `dev_resume.md`          | Your Developer resume (plain text)                  |
| `instructions_prompt.md` | Rules for the AI: length, format, what to emphasize |
| `writing_examples.md`    | 2-3 of your real cover letters for style matching   |
| `school_transcript.md`   | Program name, courses, graduation, achievements     |

Keep `prompts/system_prompt.md` identity-neutral because it is committed as
part of the public application. Put applicant names, contact details, education
facts, portfolio links, and personal writing preferences only in
`models_personal/` or `.env`.

### QA behavior

QA is enabled by default. It always performs one independent review, then makes
up to `QA_MAX_REPAIRS` additional corrective retries while validating the
actual DOCX/PDF artifacts. Each output folder receives `qa_report.json`.
Notion logging occurs only after blocking QA issues are resolved.

Mechanical invariants such as resume bullet markers, the configured applicant
name, cover-letter sign-off, and an existing valid ATS score are normalized in
code before validation. Repeated runs for the same company, position, and date
use suffixed folders (`_2`, `_3`, and so on) so earlier QA evidence is retained.

Set `QA_PROVIDER=ollama` to keep review local even when another provider writes
the first draft. Set `QA_VISUAL_ENABLED=false` to skip the extra visual model
call while retaining grammar, structure, DOCX, and PDF page checks.

### 3. Install backend dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements.txt
```

### 4. Install frontend dependencies

```powershell
cd frontend
npm install
```

---

## Running the App

Open two terminals from the project root:

**Terminal 1 — Backend:**
From the project folder:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
```

Reload only for development.

**Terminal 2 — Frontend:**

```powershell
cd frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

The FastAPI interactive docs are also available at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## Notion Setup

To have job applications logged automatically:

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations) → **New Integration** → copy the token into `NOTION_TOKEN`
2. Create a new full-page **Database** in Notion with these **exact** property names and types:

| Property name      | Type     | Notes                                                   |
| ------------------ | -------- | ------------------------------------------------------- |
| Title              | Title    | The default Notion title column — keep the name `Title` |
| Company            | Text     |                                                         |
| Position           | Text     |                                                         |
| Status             | Select   | Add option: `Applied`                                   |
| Location           | Text     | Optional                                                |
| Sent Resume        | Checkbox |                                                         |
| AI Resume          | Checkbox |                                                         |
| ATS Use            | Checkbox |                                                         |
| Folder Name        | Text     |                                                         |
| Salary (Annual)    | Number   | Optional                                                |
| Salary (By Hour)   | Number   | Optional                                                |
| Date of Submission | Date     |                                                         |
| Contact            | Email    | Optional                                                |

> **Property names are case-sensitive and must match exactly** — including spaces and parentheses. Run `GET /api/notion/test` (with the backend running) to check your database against these requirements and see any mismatches.

3. Click **Share** on the database page → invite your integration
4. Copy the database ID from the URL (`notion.so/.../{DATABASE_ID}?v=...`) → paste into `NOTION_DATABASE_ID`

> If Notion is not configured, the app still works — it just skips the logging step.

---

## AI Providers

| Provider | Needs                         | Model                                          |
| -------- | ----------------------------- | ---------------------------------------------- |
| Claude   | `ANTHROPIC_API_KEY` in `.env` | `claude-sonnet-4-6` (configurable)             |
| ChatGPT  | `OPENAI_API_KEY` in `.env`    | `gpt-4o` (configurable)                        |
| Ollama   | Ollama running locally        | `gemma4:e4b` (configurable via `OLLAMA_MODEL`) |

For Ollama: install from [ollama.com](https://ollama.com), then `ollama pull gemma3:4b` (or whichever model you have).

---

## Auth

The app is local-only with no authentication. The architecture is ready for it when needed:

- **Backend**: add `Depends(get_current_user)` to any router — zero restructuring
- **Frontend**: wrap `<App />` with `<AuthProvider>` + a protected route in `main.tsx`

---

## Credits

Inspired by and developed in discussion with [Fernando C. B. Horta](https://github.com/fernandocbhorta). Fernando's work on AI-assisted resume generation was the direct inspiration for this project. A link to his work will be added once it is published.

---

Built by [Louielyn Mata](https://github.com/louielynmata) · Local only · no data leaves your machine
