"""Minimal web UI + HTTP API around the same pipeline the CLI uses.

    uvicorn app:app --port 8000        then open http://localhost:8000

POST /extract  (multipart, field "file")  ->  {"status", "result", "meta"}
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse

from invoice_extractor.llm import GeminiClient
from invoice_extractor.loader import MAX_FILE_BYTES
from invoice_extractor.pipeline import extract_document

load_dotenv()
app = FastAPI(title="Invoice extractor")
STATIC = Path(__file__).parent / "static"
_client = GeminiClient()


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/extract")
async def extract(file: UploadFile = File(...)):
    data = await file.read(MAX_FILE_BYTES + 1)
    suffix = Path(file.filename or "upload").suffix[:10]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"upload{suffix}"
        path.write_bytes(data)  # oversize files are rejected by the loader's own size check
        # pipeline is blocking (network I/O); run it off the event loop
        outcome = await run_in_threadpool(extract_document, path, _client)
    meta = outcome.meta()
    meta["file"] = file.filename
    code = 200 if outcome.result is not None else 422
    return JSONResponse({"status": outcome.status, "result": outcome.result, "meta": meta}, status_code=code)
