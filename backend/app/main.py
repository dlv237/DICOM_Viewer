from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import duckdb
from pydantic import BaseModel
import os

DB_PATH = os.environ.get("DUCKDB_PATH", "/data/app.duckdb")

app = FastAPI(title="DICOM Viewer API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure database and a demo table
con = duckdb.connect(DB_PATH)
con.execute("CREATE TABLE IF NOT EXISTS studies(id INTEGER, name VARCHAR);")
# Seed demo row only if table is empty
try:
    cnt = con.execute("SELECT COUNT(*) FROM studies").fetchone()[0]
    if cnt == 0:
        con.execute("INSERT INTO studies VALUES (1, 'Demo Study')")
except Exception:
    pass

class Study(BaseModel):
    id: int
    name: str
@app.get("/")
async def root():
    return {"message": "Welcome to the DICOM Viewer API"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/studies")
async def list_studies():
    rows = con.execute("SELECT id, name FROM studies ORDER BY id").fetchall()
    return [Study(id=r[0], name=r[1]) for r in rows]

@app.post("/studies")
async def add_study(study: Study):
    con.execute("INSERT INTO studies VALUES (?, ?)", [study.id, study.name])
    return {"ok": True}
