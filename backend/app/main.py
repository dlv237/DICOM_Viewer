from fastapi import FastAPI
from fastapi import HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import duckdb
from pydantic import BaseModel
import os
from typing import Any, Dict, List
from fastapi.responses import FileResponse

DB_PATH = os.environ.get("DUCKDB_PATH", "/data/app.duckdb")
# Absolute Parquet metadata path (must be accessible inside the backend container)
METADATA_PARQUET_PATH = os.environ.get(
    "METADATA_PARQUET_PATH",
    "/data/anon.parquet",
)

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

def _query_parquet(sql: str, params: List[Any]) -> List[Dict[str, Any]]:
    """Run a DuckDB query over a Parquet file and return list of dicts.
    This avoids requiring pandas/pyarrow in the image.
    """
    # Use an in-memory DuckDB; do not open in read-only mode (not supported for :memory:)
    with duckdb.connect(database=":memory:") as con:
        # Using in-memory db is fine; read_parquet will lazy-scan from disk
        cur = con.execute(sql, params)
        # Build dicts from cursor description + rows
        col_names = [d[0] for d in cur.description]
        rows = cur.fetchall()
        return [dict(zip(col_names, r)) for r in rows]

def _detect_study_uid_column(available_cols: set[str]) -> str | None:
    """Return the best matching column name that represents the Study UID."""
    candidates = [
        "StudyInstanceUID",
        "studyID",
        "study_id",
        "anon_study_uid",
        "StudyUID",
    ]
    for c in candidates:
        if c in available_cols:
            return c
    return None

@app.get("/findings")
def get_findings():
    try:
        cols = _finding_columns()
        cols.sort()
        return cols
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/dicoms/{sop_instance_uid}")
def get_dicom_by_sop(sop_instance_uid: str):
    """Stream a DICOM file by SOPInstanceUID resolved from the Parquet metadata.

    Returns application/dicom if possible, else octet-stream.
    """
    try:
        if not os.path.exists(METADATA_PARQUET_PATH):
            raise HTTPException(status_code=503, detail="Parquet no disponible.")

        # Determine columns
        cols_info = _query_parquet("DESCRIBE SELECT * FROM read_parquet(?) LIMIT 0", [METADATA_PARQUET_PATH])
        available_cols = {c["column_name"] for c in cols_info if "column_name" in c}
        file_cols = [c for c in ("file_path", "dicom_path", "path") if c in available_cols]
        if not file_cols:
            raise HTTPException(status_code=500, detail="No se encontraron columnas de ruta de archivo en el parquet.")
        file_col = file_cols[0]

        sql = f'SELECT "{file_col}" FROM read_parquet(?) WHERE "SOPInstanceUID" = ? LIMIT 1'
        rows = _query_parquet(sql, [METADATA_PARQUET_PATH, sop_instance_uid])
        if not rows:
            raise HTTPException(status_code=404, detail="SOPInstanceUID no encontrado.")
        path = rows[0][file_col]
        if not isinstance(path, str) or not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Archivo DICOM no disponible en el servidor.")
        # Let the browser/viewer fetch bytes
        return FileResponse(path, media_type="application/dicom", filename=os.path.basename(path))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/studies")
def get_studies(
    hallazgo: str | None = Query(default=None, description="Nombre de la columna de hallazgo a filtrar"),
    value: str | None = Query(default=None, description="Valor del hallazgo (e.g., 'Certainly True')"),
    page: int = Query(default=1, ge=1, description="Número de página (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Cantidad de resultados por página"),
):
    print("Fetching studies with filters:", {hallazgo, value, page, page_size})
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

    # Stable ordering helps consistent pagination
    query = base_select + where + " ORDER BY studyID LIMIT ? OFFSET ?"
    params.extend([page_size, (page - 1) * page_size])
    with duckdb.connect(DB_PATH, read_only=True) as con:
        rows = con.execute(query, params).fetchall()
    return [{"studyId": r[0], "cleanReportText": r[1]} for r in rows]

@app.get("/studies/count")
def get_studies_count(
    hallazgo: str | None = Query(default=None, description="Nombre de la columna de hallazgo a filtrar"),
    value: str | None = Query(default=None, description="Valor del hallazgo (e.g., 'Certainly True')"),
):
    try:
        base_select = "SELECT COUNT(*) FROM reports"
        params: list = []
        where = ""
        if hallazgo is not None and value is not None:
            valid_cols = set(_finding_columns())
            if hallazgo not in valid_cols:
                raise HTTPException(status_code=400, detail=f"Hallazgo desconocido: {hallazgo}")
            where = f" WHERE {_quote_ident(hallazgo)} = ?"
            params.append(value)

        query = base_select + where
        with duckdb.connect(DB_PATH, read_only=True) as con:
            count = con.execute(query, params).fetchone()[0]
        return {"count": int(count)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/studies/{study_id}/dicoms")
def get_study_dicoms(study_id: str):
    """Return rows from the metadata Parquet for a given StudyInstanceUID (study_id).

    Notes:
    - Requires that METADATA_PARQUET_PATH points to a readable Parquet file inside the container.
    - We select a useful subset of columns when available; otherwise we return all available columns.
    """
    try:
        if not os.path.exists(METADATA_PARQUET_PATH):
            raise HTTPException(
                status_code=503,
                detail=f"Parquet no disponible en ruta: {METADATA_PARQUET_PATH}. Monte el NAS y/o configure METADATA_PARQUET_PATH.",
            )

        # Probe available columns first
        describe_sql = (
            "DESCRIBE SELECT * FROM read_parquet(?) LIMIT 0"
        )
        cols_info = _query_parquet(describe_sql, [METADATA_PARQUET_PATH])
        available_cols = {c["column_name"] for c in cols_info if "column_name" in c}

        uid_col = _detect_study_uid_column(available_cols)
        if not uid_col:
            raise HTTPException(status_code=500, detail="No se encontró columna de Study UID en el parquet.")

        # Prefer selecting a compact set if present
        preferred = [
            "StudyInstanceUID",
            "SeriesInstanceUID",
            "SOPInstanceUID",
            "PatientID",
            "Modality",
            "BodyPartExamined",
            "AcquisitionDate",
            "AcquisitionTime",
            "dicom_path",
            "path",
            "file_path",
        ]
        select_cols = [c for c in preferred if c in available_cols]
        if not select_cols:
            select_expr = "*"
        else:
            select_expr = ", ".join(f'"{c}"' for c in select_cols)

        sql = (
            f"SELECT {select_expr} FROM read_parquet(?) WHERE \"{uid_col}\" = ? LIMIT 2000"
        )
        rows = _query_parquet(sql, [METADATA_PARQUET_PATH, study_id])
        return {"studyId": study_id, "count": len(rows), "items": rows}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/dicom/studies")
def list_dicom_studies(limit: int = Query(default=10, ge=1, le=100)):
    """List unique Study UIDs from the Parquet (up to limit) for quick testing."""
    try:
        if not os.path.exists(METADATA_PARQUET_PATH):
            raise HTTPException(
                status_code=503,
                detail=f"Parquet no disponible en ruta: {METADATA_PARQUET_PATH}.",
            )
        cols_info = _query_parquet("DESCRIBE SELECT * FROM read_parquet(?) LIMIT 0", [METADATA_PARQUET_PATH])
        available_cols = {c["column_name"] for c in cols_info if "column_name" in c}
        uid_col = _detect_study_uid_column(available_cols)
        if not uid_col:
            raise HTTPException(status_code=500, detail="No se encontró columna de Study UID en el parquet.")

        # Try to also return a sample file path column if available
        file_cols = [c for c in ("file_path", "dicom_path", "path") if c in available_cols]
        if file_cols:
            select_expr = f'"{uid_col}", "{file_cols[0]}"'
        else:
            select_expr = f'"{uid_col}"'

        sql = (
            f"SELECT DISTINCT {select_expr} FROM read_parquet(?) WHERE \"{uid_col}\" IS NOT NULL LIMIT ?"
        )
        rows = _query_parquet(sql, [METADATA_PARQUET_PATH, limit])
        return {"uidColumn": uid_col, "items": rows}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/studies")
async def add_study(study: Study):
    with duckdb.connect(DB_PATH) as con:
        con.execute("INSERT INTO studies VALUES (?, ?)", [study.id, study.name])
    return {"ok": True}
