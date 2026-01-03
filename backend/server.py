# main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles

from l1_sj_engine import run_l1_engine

app = FastAPI(title="V14.0 SJ Ontology Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "https://proofence-lab.com",
        "https://www.proofence-lab.com",
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
    StaticFiles(directory="../frontend", html=True),
    name="frontend"
)
