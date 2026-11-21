# AI Knowledge Assistant

A full-stack document assistant that indexes PDF, DOCX, TXT, Markdown, and CSV files and answers questions using local retrieval or an OpenAI-compatible model.

## Features

- Document upload and extraction
- Local TF-IDF-style retrieval
- Optional OpenAI-compatible answer generation
- Source document tracking
- Persistent SQLite or PostgreSQL storage
- Responsive web interface
- Render deployment configuration

## Run locally

```powershell
cd knowledge-assistant
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000.

## Enable AI answers

Copy `.env.example` to `.env` and set `AI_API_KEY`. Environment variables are loaded automatically by your hosting platform or process manager.

## Deploy to Render

1. Push this repository to GitHub.
2. Create a free Render Web Service from the repository.
3. Set build command to `pip install -r requirements.txt`.
4. Set start command to `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
5. Leave `DATABASE_URL` as `sqlite:///./knowledge.db` for an ephemeral demo, or replace it with a valid PostgreSQL URL from Neon.
6. Optionally add `AI_API_KEY`, `AI_API_BASE`, and `AI_MODEL`.
