"""
Explainable Compiler -- backend entrypoint.

Run from the project root with:
    uvicorn backend.main:app --reload

Exposes:
    POST /api/analyze     run the full phase-by-phase analysis + execution
    GET  /api/languages   supported languages, their pipeline order, sample code
    GET  /api/health      liveness check
    /                     serves the frontend (frontend/index.html, app.js, style.css)
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.compiler.pipeline import run_pipeline
from backend.languages.config import LANGS, MAX_CODE_LENGTH, MAX_INPUT_LENGTH
from backend import ai
from backend.pdf_report import build_pdf_bytes

app = FastAPI(title="Explainable Compiler API", version="1.0.0")

# Local development: allow the frontend to call this API even if it's opened
# from a different origin/port than the one serving it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    language: str = Field(..., description="one of: c, cpp, java, python")
    code: str = Field(..., description="source code to analyze")
    input: str = Field("", description="whitespace-separated stdin values for input()/scanf")


class AskRequest(BaseModel):
    question: str = Field(..., description="the user's question")
    language: str = Field("", description="current language in the editor, if any")
    code: str = Field("", description="current source code in the editor, if any")
    activePhase: str = Field("", description="which phase tab the user currently has open")
    phases: dict = Field(default_factory=dict, description="the current /api/analyze result's phases, if any")


class ReportRequest(BaseModel):
    language: str = Field(..., description="one of: c, cpp, java, python")
    code: str = Field(..., description="source code that was analyzed")
    phases: dict = Field(..., description="the full phases object from /api/analyze")


class PdfRequest(BaseModel):
    language: str = Field(..., description="one of: c, cpp, java, python")
    code: str = Field(..., description="source code that was analyzed")
    phases: dict = Field(..., description="the full phases object from /api/analyze")
    status: dict = Field(default_factory=dict, description="the status object from /api/analyze")
    error: dict | None = Field(None, description="the error object from /api/analyze, if analysis stopped early")
    aiReport: str | None = Field(None, description="previously-generated AI report text to append, if any")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/languages")
def languages():
    return {
        key: {"name": cfg["name"], "pipeline": cfg["pipeline"], "sample": cfg["sample"]}
        for key, cfg in LANGS.items()
    }


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    if req.language not in LANGS:
        raise HTTPException(status_code=400, detail=f"Unsupported language '{req.language}'. "
                                                      f"Supported: {', '.join(LANGS.keys())}")
    if len(req.code) > MAX_CODE_LENGTH:
        raise HTTPException(status_code=400, detail=f"Source code exceeds the {MAX_CODE_LENGTH} character limit.")
    if len(req.input) > MAX_INPUT_LENGTH:
        raise HTTPException(status_code=400, detail=f"Program input exceeds the {MAX_INPUT_LENGTH} character limit.")
    try:
        return run_pipeline(req.language, req.code, req.input)
    except Exception as e:  # noqa: BLE001 -- never let an unexpected bug 500 the whole UI
        raise HTTPException(status_code=500, detail=f"Internal analyzer error: {e}")


@app.get("/api/ai-status")
def ai_status():
    return {"configured": ai.is_configured(), "provider": ai.get_provider()}


@app.post("/api/ask")
def ask(req: AskRequest):
    context = None
    if req.code or req.phases:
        context = {"language": req.language, "code": req.code, "activePhase": req.activePhase, "phases": req.phases}
    try:
        answer = ai.ask_question(req.question, context)
        return {"answer": answer}
    except ai.AIError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/report")
def report(req: ReportRequest):
    if req.language not in LANGS:
        raise HTTPException(status_code=400, detail=f"Unsupported language '{req.language}'.")
    try:
        text = ai.generate_report(req.language, req.code, req.phases)
        return {"report": text}
    except ai.AIError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/pdf-report")
def pdf_report(req: PdfRequest):
    if req.language not in LANGS:
        raise HTTPException(status_code=400, detail=f"Unsupported language '{req.language}'.")
    if len(req.code) > MAX_CODE_LENGTH:
        raise HTTPException(status_code=400, detail=f"Source code exceeds the {MAX_CODE_LENGTH} character limit.")
    try:
        pdf_bytes = build_pdf_bytes(
            req.language, req.code, req.phases, req.status, req.error, ai_report_text=req.aiReport
        )
    except Exception as e:  # noqa: BLE001 -- never 500 the whole UI over a PDF layout bug
        raise HTTPException(status_code=500, detail=f"Could not generate the PDF report: {e}")
    filename = f"compilation-report-{req.language}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ---- serve the static frontend so `uvicorn backend.main:app` is all you need ----
_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")
