# main.py

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles

from l1_sj_engine import run_l1_engine

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

app = FastAPI(title="V14.0 SJ Ontology Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
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
    
    
app.mount(
    "/",
    StaticFiles(directory=str(FRONTEND_DIR), html=True),
    name="frontend"
)
