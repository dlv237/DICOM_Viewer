from fastapi import FastAPI
from fastapi import HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import duckdb
from pydantic import BaseModel
import os
from typing import Any, Dict, List
from fastapi.responses import FileResponse

DB_PATH = os.environ.get("DUCKDB_PATH", "/data/app.duckdb")
# Back-compat: METADATA_PARQUET_PATH may be used for both; prefer specific envs when present
METADATA_PARQUET_PATH = os.environ.get("METADATA_PARQUET_PATH", "/data/anon.parquet")
# Mapping parquet: real PHI -> anonymized ANON
MAPPING_PARQUET_PATH = os.environ.get("MAPPING_PARQUET_PATH", METADATA_PARQUET_PATH)
# DICOM metadata parquet: rows with Study/Series/SOP and optional paths
DICOM_METADATA_PARQUET_PATH = os.environ.get("DICOM_METADATA_PARQUET_PATH", METADATA_PARQUET_PATH)

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

def _find_col(available_cols: set[str], candidates: list[str]) -> str | None:
    """Find a column in available_cols that matches any candidate (case-insensitive),
    and return the original-case column name."""
    # Build lowercase -> original map
    lower_map = {c.lower(): c for c in available_cols}
    for cand in candidates:
        key = cand.lower()
        if key in lower_map:
            return lower_map[key]
    return None

def _map_real_to_anon_study_uid(real_uid: str) -> str | None:
    """Map a real StudyInstanceUID to its anonymized counterpart using the Parquet mapping.

    Expects two columns in the Parquet (names can vary); tries common candidates:
    - real: StudyInstanceUID | studyID | original_study_uid | real_study_uid
    - anon: anon_study_uid | AnonymizedStudyInstanceUID | anonStudyInstanceUID
    Returns the anonymized UID if found; otherwise None.
    """
    if not os.path.exists(MAPPING_PARQUET_PATH):
        return None
    try:
        cols_info = _query_parquet("DESCRIBE SELECT * FROM read_parquet(?) LIMIT 0", [MAPPING_PARQUET_PATH])
        available = {c.get("column_name") for c in cols_info if isinstance(c, dict) and c.get("column_name")}
        # Prefer explicit PHI/ANON, then fall back to other common names
        real_col = _find_col(available, ["PHI"]) or _find_col(available, ["StudyInstanceUID", "studyID", "original_study_uid", "real_study_uid"]) 
        anon_col = _find_col(available, ["ANON"]) or _find_col(available, ["anon_study_uid", "AnonymizedStudyInstanceUID", "anonStudyInstanceUID", "anon_StudyInstanceUID"]) 
        if not real_col or not anon_col:
            return None
        sql = f'SELECT "{anon_col}" AS anon FROM read_parquet(?) WHERE "{real_col}" = ? LIMIT 1'
        rows = _query_parquet(sql, [MAPPING_PARQUET_PATH, real_uid])
        if rows:
            return rows[0].get("anon")
        return None
    except Exception:
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
    """Stream a DICOM file by SOPInstanceUID.

    Resolution order:
    1) Direct file under common roots using the SOP as filename: {SOP}.dcm
       Roots checked: /app/data (mounted from ./backend/data), /data_in (mounted from ./data), /data (duckdb volume or extra mount)
    2) If Parquet metadata is available, resolve by SOP and use the path column
    """
    try:
        # 1) Direct file lookup
        filename = f"{sop_instance_uid}.dcm"
        for root in ("/app/data", "/data_in", "/data"):
            path = os.path.join(root, filename)
            if os.path.exists(path):
                return FileResponse(path, media_type="application/dicom", filename=os.path.basename(path))

        # 2) Parquet-based resolution (optional)
        if os.path.exists(DICOM_METADATA_PARQUET_PATH):
            try:
                cols_info = _query_parquet("DESCRIBE SELECT * FROM read_parquet(?) LIMIT 0", [DICOM_METADATA_PARQUET_PATH])
                available_cols = {c["column_name"] for c in cols_info if "column_name" in c}
                file_cols = [c for c in ("file_path", "dicom_path", "path") if c in available_cols]
                if file_cols:
                    file_col = file_cols[0]
                    sql = f'SELECT "{file_col}" FROM read_parquet(?) WHERE "SOPInstanceUID" = ? LIMIT 1'
                    rows = _query_parquet(sql, [DICOM_METADATA_PARQUET_PATH, sop_instance_uid])
                    if rows:
                        parquet_path = rows[0][file_col]
                        if isinstance(parquet_path, str) and os.path.exists(parquet_path):
                            return FileResponse(parquet_path, media_type="application/dicom", filename=os.path.basename(parquet_path))
            except Exception:
                # ignore parquet errors and continue
                pass

        raise HTTPException(status_code=404, detail="Archivo DICOM no encontrado en /app/data, /data_in, /data ni por parquet.")
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
    # Build filtered, deduplicated list of studies (unique studyID)
    # Use a representative text per study (MIN as deterministic choice)
    base_select = (
        "SELECT studyID AS studyId, MIN(clean_report_text) AS cleanReportText FROM reports"
    )
    params: list = []
    where_clauses = ["studyID IS NOT NULL"]
    if hallazgo is not None and value is not None:
        # Validate hallazgo exists to avoid SQL injection
        valid_cols = set(_finding_columns())
        if hallazgo not in valid_cols:
            raise HTTPException(status_code=400, detail=f"Hallazgo desconocido: {hallazgo}")
        where_clauses.append(f"{_quote_ident(hallazgo)} = ?")
        params.append(value)

    # Stable ordering helps consistent pagination
    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    query = base_select + where_sql + " GROUP BY studyID ORDER BY studyID LIMIT ? OFFSET ?"
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
        base_select = "SELECT COUNT(DISTINCT studyID) FROM reports"
        params: list = []
        where_clauses = ["studyID IS NOT NULL"]
        if hallazgo is not None and value is not None:
            valid_cols = set(_finding_columns())
            if hallazgo not in valid_cols:
                raise HTTPException(status_code=400, detail=f"Hallazgo desconocido: {hallazgo}")
            where_clauses.append(f"{_quote_ident(hallazgo)} = ?")
            params.append(value)
        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        query = base_select + where_sql
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
        if not os.path.exists(DICOM_METADATA_PARQUET_PATH):
            raise HTTPException(
                status_code=503,
                detail=f"Parquet no disponible en ruta: {DICOM_METADATA_PARQUET_PATH}. Configure DICOM_METADATA_PARQUET_PATH.",
            )

        # Probe available columns first
        describe_sql = "DESCRIBE SELECT * FROM read_parquet(?) LIMIT 0"
        cols_info = _query_parquet(describe_sql, [DICOM_METADATA_PARQUET_PATH])
        available_cols = {c["column_name"] for c in cols_info if "column_name" in c}

        uid_col = _detect_study_uid_column(available_cols)
        if not uid_col:
            raise HTTPException(status_code=500, detail="No se encontró columna de Study UID en el parquet.")

        # If the incoming study_id is real, try to map it to anonymized value first
        anon_uid = _map_real_to_anon_study_uid(study_id)
        print(study_id, anon_uid)
        target_uid = anon_uid or study_id

        # Decide which column to filter on. Prefer the anonymized column when mapping succeeded.
        filter_col = uid_col
        if anon_uid:
            anon_filter_col = _find_col(available_cols, [
                "ANON", "anon", "anon_study_uid", "AnonymizedStudyInstanceUID", "anonStudyInstanceUID", "anon_StudyInstanceUID"
            ])
            if anon_filter_col:
                filter_col = anon_filter_col

        print(f"Filtrando por columna: {filter_col}")

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

        sql = f'SELECT {select_expr} FROM read_parquet(?) WHERE "{filter_col}" = ? LIMIT 2000'
        rows = _query_parquet(sql, [DICOM_METADATA_PARQUET_PATH, target_uid])
        return {"studyId": study_id, "mappedStudyId": target_uid if target_uid != study_id else None, "count": len(rows), "items": rows}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/dicom/studies")
def list_dicom_studies(limit: int = Query(default=10, ge=1, le=100)):
    """List unique Study UIDs from the Parquet (up to limit) for quick testing."""
    try:
        if not os.path.exists(DICOM_METADATA_PARQUET_PATH):
            raise HTTPException(
                status_code=503,
                detail=f"Parquet no disponible en ruta: {DICOM_METADATA_PARQUET_PATH}.",
            )
        cols_info = _query_parquet("DESCRIBE SELECT * FROM read_parquet(?) LIMIT 0", [DICOM_METADATA_PARQUET_PATH])
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

        sql = f'SELECT DISTINCT {select_expr} FROM read_parquet(?) WHERE "{uid_col}" IS NOT NULL LIMIT ?'
        rows = _query_parquet(sql, [DICOM_METADATA_PARQUET_PATH, limit])
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
