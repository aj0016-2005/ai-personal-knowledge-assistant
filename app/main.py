import os
import re
import math
import tempfile
from collections import Counter
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pypdf import PdfReader
from docx import Document as DocxDocument
from sqlalchemy import create_engine, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./knowledge.db").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
if not DATABASE_URL.startswith(("sqlite://", "postgresql+psycopg://")):
    print("Invalid DATABASE_URL: expected SQLite or PostgreSQL; using SQLite fallback.")
    DATABASE_URL = "sqlite:///./knowledge.db"

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)


class Base(DeclarativeBase):
    pass


class DocumentRecord(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)


class ChatRecord(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)


Base.metadata.create_all(engine)

app = FastAPI(title="AI Knowledge Assistant")
ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "he",
    "in", "is", "it", "its", "of", "on", "that", "the", "to", "was", "were",
    "will", "with", "what", "which", "when", "where", "who", "why", "how",
}


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_text(upload: UploadFile, data: bytes) -> str:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix == ".pdf":
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp:
            temp.write(data)
            temp_path = temp.name
        try:
            reader = PdfReader(temp_path)
            return clean_text("\n".join(page.extract_text() or "" for page in reader.pages))
        finally:
            os.unlink(temp_path)
    if suffix == ".docx":
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as temp:
            temp.write(data)
            temp_path = temp.name
        try:
            document = DocxDocument(temp_path)
            return clean_text("\n".join(paragraph.text for paragraph in document.paragraphs))
        finally:
            os.unlink(temp_path)
    if suffix in {".txt", ".md", ".csv"}:
        return clean_text(data.decode("utf-8", errors="replace"))
    raise HTTPException(400, "Unsupported file type. Upload PDF, DOCX, TXT, MD, or CSV.")


def split_chunks(text: str, size: int = 900) -> list[str]:
    words = text.split()
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)]


def tokenize(text: str) -> list[str]:
    return [
        word
        for word in re.findall(r"[a-z0-9]+", text.lower())
        if len(word) > 2 and word not in STOPWORDS
    ]


def retrieve(query: str, chunks: list[str], limit: int = 4) -> list[str]:
    query_terms = set(tokenize(query))
    if not chunks or not query_terms:
        return chunks[:limit]

    ranked: list[tuple[float, str]] = []
    for chunk in chunks:
        terms = tokenize(chunk)
        frequencies = Counter(terms)
        score = sum(frequencies.get(term, 0) for term in query_terms)
        score = score / math.sqrt(len(set(terms)) or 1)
        ranked.append((score, chunk))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [chunk for score, chunk in ranked[:limit] if score > 0]


async def ai_answer(question: str, context: str) -> str:
    api_key = os.getenv("AI_API_KEY")
    if not api_key:
        if not context:
            return "I could not find relevant text in the uploaded documents."
        return (
            "Here is the most relevant information I found:\n\n"
            f"{context[:2200]}\n\n"
            "This is local extraction mode. Add AI_API_KEY for generated answers."
        )

    base_url = os.getenv("AI_API_BASE", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("AI_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Answer only from the supplied context. Cite source text clearly "
                    "and say when the context does not contain the answer."
                ),
            },
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion:\n{question}"},
        ],
        "temperature": 0.2,
    }
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
    if response.status_code >= 400:
        raise HTTPException(502, "The AI provider returned an error.")
    return response.json()["choices"][0]["message"]["content"]


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"))


@app.post("/api/documents")
async def upload_document(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File exceeds the maximum upload size.")
    content = extract_text(file, data)
    if len(content) < 10:
        raise HTTPException(400, "The file contains no readable text.")

    with Session(engine) as session:
        record = DocumentRecord(name=file.filename or "Untitled", content=content)
        session.add(record)
        session.commit()
        session.refresh(record)
    return {"id": record.id, "name": record.name, "characters": len(record.content)}


@app.get("/api/documents")
async def list_documents() -> list[dict]:
    with Session(engine) as session:
        records = session.query(DocumentRecord).order_by(DocumentRecord.id.desc()).all()
        return [{"id": record.id, "name": record.name, "characters": len(record.content)} for record in records]


@app.delete("/api/documents/{document_id}")
async def delete_document(document_id: int) -> dict:
    with Session(engine) as session:
        record = session.get(DocumentRecord, document_id)
        if not record:
            raise HTTPException(404, "Document not found.")
        session.delete(record)
        session.commit()
    return {"deleted": document_id}


@app.post("/api/chat")
async def chat(payload: dict) -> dict:
    question = clean_text(str(payload.get("message", "")))
    if not question:
        raise HTTPException(400, "Message cannot be empty.")

    with Session(engine) as session:
        records = session.query(DocumentRecord).all()
        all_chunks: list[str] = []
        sources: list[str] = []
        for record in records:
            chunks = split_chunks(record.content)
            all_chunks.extend(chunks)
            if retrieve(question, chunks, limit=1):
                sources.append(record.name)

        relevant = retrieve(question, all_chunks, limit=5)
        answer = await ai_answer(question, "\n\n".join(relevant))
        session.add(ChatRecord(role="user", message=question))
        session.add(ChatRecord(role="assistant", message=answer))
        session.commit()

    return {
        "answer": answer,
        "sources": list(dict.fromkeys(sources)),
        "mode": "ai" if os.getenv("AI_API_KEY") else "local",
    }
