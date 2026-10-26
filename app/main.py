import os
import tempfile
import threading
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import analysis, config, llm

STATIC = Path(__file__).resolve().parent.parent / "static"
ALLOWED = {".pdf", ".docx", ".txt", ".md"}
JOBS = {}


class Job:
    def __init__(self, name):
        self.id = uuid.uuid4().hex[:12]
        self.name = name
        self.status = "running"
        self.stage = "read"
        self.progress = 0.0
        self.log = []
        self.result = None
        self.error = ""
        self.created = time.time()

    def update(self, stage, progress, msg=None):
        self.stage = stage
        self.progress = round(progress, 3)
        if msg:
            self.log.append(msg)


def work(job, path, online):
    try:
        job.update("read", 0.0, "Reading the document")
        job.result = analysis.analyze(path, job.name, online, job.update)
        job.status = "done"
    except Exception as e:
        traceback.print_exc()
        job.status, job.error = "error", str(e)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


@asynccontextmanager
async def lifespan(_):
    threading.Thread(target=llm.preload, daemon=True).start()
    yield


app = FastAPI(title="Marginalia", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return llm.status


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...), verify_online: bool = Form(True)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(400, "Upload a PDF, DOCX, TXT or MD file.")
    data = await file.read()
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File is larger than {config.MAX_UPLOAD_MB} MB.")
    fd, path = tempfile.mkstemp(suffix=ext)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    for old in sorted(JOBS.values(), key=lambda j: j.created)[:-15]:
        JOBS.pop(old.id, None)
    job = Job(file.filename)
    JOBS[job.id] = job
    threading.Thread(target=work, args=(job, path, verify_online), daemon=True).start()
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job.")
    return {"status": job.status, "stage": job.stage, "progress": job.progress, "log": job.log[-12:], "error": job.error}


@app.get("/api/jobs/{job_id}/result")
def job_result(job_id: str):
    job = JOBS.get(job_id)
    if not job or job.status != "done":
        raise HTTPException(404, "Result not ready.")
    return job.result
