from fastapi import FastAPI
from fastapi import HTTPException, Query
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

class Study(BaseModel):
    id: int
    name: str

@app.get("/")
async def root():
    return {"message": "Welcome to the DICOM Viewer API"}

@app.get("/health")
async def health():
    return {"status": "ok"}

def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'

def _finding_columns() -> list[str]:
    # Discover columns in 'reports' that correspond to findings (exclude metadata columns)
    meta_cols = {
        'clean_report_text', 'studyID', 'age', 'views', 'study_date',
        'regex_labels', 'report_text', 'report_path', 'llm_labels'
    }
    with duckdb.connect(DB_PATH, read_only=True) as con:
        rows = con.execute("PRAGMA table_info('reports')").fetchall()
    # rows: (cid, name, type, notnull, dflt_value, pk)
    cols = [r[1] for r in rows]
    return [c for c in cols if c not in meta_cols]

@app.get("/findings")
def get_findings():
    try:
        cols = _finding_columns()
        cols.sort()
        return cols
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/studies")
def get_studies(
    hallazgo: str | None = Query(default=None, description="Nombre de la columna de hallazgo a filtrar"),
    value: str | None = Query(default=None, description="Valor del hallazgo (e.g., 'Certainly True')"),
):  
    print("Fetching studies with filters:", { hallazgo, value })
    base_select = (
        "SELECT studyID AS studyId, clean_report_text AS cleanReportText FROM reports"
    )
    params: list = []
    where = ""
    if hallazgo is not None and value is not None:
        # Validate hallazgo exists to avoid SQL injection
        valid_cols = set(_finding_columns())
        if hallazgo not in valid_cols:
            raise HTTPException(status_code=400, detail=f"Hallazgo desconocido: {hallazgo}")
        where = f" WHERE {_quote_ident(hallazgo)} = ?"
        params.append(value)
    query = base_select + where + " LIMIT 50"
    with duckdb.connect(DB_PATH, read_only=True) as con:
        rows = con.execute(query, params).fetchall()
    return [{"studyId": r[0], "cleanReportText": r[1]} for r in rows]

@app.post("/studies")
async def add_study(study: Study):
    with duckdb.connect(DB_PATH) as con:
        con.execute("INSERT INTO studies VALUES (?, ?)", [study.id, study.name])
    return {"ok": True}
