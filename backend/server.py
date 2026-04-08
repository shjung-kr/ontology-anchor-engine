# main.py

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles

from backend.core.domain_models import DomainExecutionRequest
from backend.core.domain_registry import list_domain_summaries
from backend.core.engine import run_domain_engine
from backend.l1_sj_engine import run_l1_engine

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

app = FastAPI(title="V14.0 SJ Ontology Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        # cloudflare pages domain
        "https://ontology-anchor-engine.pages.dev",
        ],
    
    allow_methods=["*"],
    allow_headers=["*"],
)

class RawInput(BaseModel):
    raw_data: str


@app.post("/v14/run")
def run_engine(data: RawInput):
    return run_l1_engine(data.raw_data)


@app.get("/domains")
def list_domains():
    return {"domains": [item.model_dump() for item in list_domain_summaries()]}


@app.post("/run")
def run_domain(data: DomainExecutionRequest):
    return run_domain_engine(data)


app.mount(
    "/",
    StaticFiles(directory=str(FRONTEND_DIR), html=True),
    name="frontend"
)
