from fastapi import FastAPI
from fastapi import HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import duckdb
from pydantic import BaseModel
import os
from typing import Any, Dict, List, Optional
from fastapi.responses import FileResponse

DB_PATH = "/home/dolobos/DICOM_Viewer/app.duckdb"
# Back-compat: METADATA_PARQUET_PATH may be used for both; prefer specific envs when present
METADATA_PARQUET_PATH = "/mnt/nas_anakena/datasets/uc-cxr/processed_data/metadata/anon.parquet"
# Mapping parquet: real PHI -> anonymized ANON
MAPPING_PARQUET_PATH = "/mnt/nas_anakena/datasets/uc-cxr/processed_data/metadata/private_phi_index.parquet"
# DICOM metadata parquet: rows with Study/Series/SOP and optional paths
DICOM_METADATA_PARQUET_PATH = "/mnt/nas_anakena/datasets/uc-cxr/processed_data/metadata/anon.parquet"
# CSV sample 1k (CentaurLabs)
SAMPLE_1K_CSV_PATH = os.environ.get(
    "SAMPLE_1K_CSV_PATH",
    "/mnt/nas_anakena/datasets/uc-cxr/processed_data/reports_and_labels_llm/legacy_deprecated_data/sample_1k_for_centaurlabs.csv",
)
# CSV de grupos (Label -> Group)
LABEL_GROUPS_CSV_PATH = os.environ.get(
    "LABEL_GROUPS_CSV_PATH",
    "/mnt/nas_anakena/datasets/uc-cxr/processed_data/reports_and_labels_llm/label_freq_summary_1.csv",
)

# Base CSVs for textual info per StudyID
CSV_BASE_PATH = "/mnt/nas_anakena/datasets/uc-cxr/processed_data/reports_and_labels_llm"
FINDINGS_CSV = os.path.join(CSV_BASE_PATH, "100k_llm_findings_labels.csv")
SECTIONS_CSV = os.path.join(CSV_BASE_PATH, "sections_of_report.csv")
SENTENCES_CSV = os.path.join(CSV_BASE_PATH, "labels_per_sentence_mapped.csv")

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

def _csv_columns(csv_path: str) -> list[str]:
    """Return list of columns for a CSV using DuckDB DESCRIBE."""
    if not os.path.exists(csv_path):
        return []
    try:
        rows = _query_csv("DESCRIBE SELECT * FROM read_csv_auto(?, header=True) LIMIT 0", [csv_path])
        return [r.get("column_name") for r in rows if isinstance(r, dict) and r.get("column_name")]
    except Exception:
        return []


def _detect_uid_col_in_csv(csv_path: str) -> Optional[str]:
    """Detect UID/id column in a CSV among common candidates."""
    cols = set(_csv_columns(csv_path))
    return _find_col(cols, ["StudyInstanceUID", "studyInstanceUID", "StudyID", "studyID"])


def _finding_columns() -> list[str]:
    """Discover columns in findings CSV that correspond to findings (exclude metadata/uid)."""
    cols = set(_csv_columns(FINDINGS_CSV))
    uid_col = _detect_uid_col_in_csv(FINDINGS_CSV)
    meta_cols = {
        'clean_report_text', 'studyID', 'StudyID', 'StudyInstanceUID', 'studyInstanceUID',
        'age', 'views', 'study_date', 'regex_labels', 'report_text', 'report_path', 'llm_labels'
    }
    if uid_col:
        meta_cols.add(uid_col)
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

def _query_csv(sql: str, params: List[Any]) -> List[Dict[str, Any]]:
    """Execute a DuckDB SQL over CSV files via read_csv_auto and return list of dicts."""
    with duckdb.connect(database=":memory:") as con:
        cur = con.execute(sql, params)
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
    
def _load_label_groups() -> dict[str, list[str]]:
    """
    Retorna mapping {group: [labels...]}.
    Prioriza LABEL_GROUPS_CSV_PATH; si no existe, deriva de SAMPLE_1K_CSV_PATH.
    """
    mapping: dict[str, list[str]] = {}
    if os.path.exists(LABEL_GROUPS_CSV_PATH):
        # Usar DuckDB para leer CSV y agrupar
        sql = """
            SELECT "Group" AS grp, LIST(DISTINCT "Label") AS labels
            FROM read_csv_auto(?, header=True)
            GROUP BY grp
        """
        try:
            with duckdb.connect(database=":memory:") as con:
                rows = con.execute(sql, [LABEL_GROUPS_CSV_PATH]).fetchall()
                for grp, labels in rows:
                    if grp and isinstance(labels, list):
                        mapping[str(grp)] = [str(x) for x in labels]
                return mapping
        except Exception:
            pass
    # Fallback: deducir desde sample 1k
    if os.path.exists(SAMPLE_1K_CSV_PATH):
        sql = """
            SELECT "group" AS grp, LIST(DISTINCT "label") AS labels
            FROM read_csv_auto(?, header=True)
            GROUP BY grp
        """
        try:
            with duckdb.connect(database=":memory:") as con:
                rows = con.execute(sql, [SAMPLE_1K_CSV_PATH]).fetchall()
                for grp, labels in rows:
                    if grp and isinstance(labels, list):
                        mapping[str(grp)] = [str(x) for x in labels]
        except Exception:
            pass
    return mapping

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
    min_age: int = Query(default=18, ge=0, description="Edad mínima inclusiva"),
    max_age: int = Query(default=100, ge=0, description="Edad máxima inclusiva"),
    page: int = Query(default=1, ge=1, description="Número de página (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Cantidad de resultados por página"),
    sample_1k: bool = Query(default=False, description="Limitar a los StudyInstanceUID presentes en sample 1k"),
    label_group: str | None = Query(default=None, description="Filtrar a los UID cuyo group en el CSV 1k coincida"),
    study_id: str | None = Query(default=None, description="Buscar por StudyInstanceUID exacto; ignora otros filtros"),
):
    # Normalize age bounds
    if min_age > max_age:
        min_age, max_age = max_age, min_age

    uid_col = _detect_uid_col_in_csv(FINDINGS_CSV) or "StudyInstanceUID"
    # Choose a text column to preview
    cols = set(_csv_columns(FINDINGS_CSV))
    text_col = "clean_report_text" if "clean_report_text" in cols else ("report_text" if "report_text" in cols else None)

    base_select = f'SELECT "{uid_col}" AS studyId' + (f', MIN("{text_col}") AS cleanReportText' if text_col else ', NULL AS cleanReportText') + ' FROM read_csv_auto(?, header=True)'
    params: list = [FINDINGS_CSV]
    where_clauses = [f'"{uid_col}" IS NOT NULL']

    # If study_id is provided, short-circuit all other filters
    if study_id and study_id.strip():
        where_sql = f' WHERE "{uid_col}" = ?'
        params.append(study_id.strip())
        query = base_select + where_sql + f' GROUP BY "{uid_col}" ORDER BY "{uid_col}" LIMIT ? OFFSET ?'
        params.extend([page_size, (page - 1) * page_size])
        rows = _query_csv(query, params)
        return [{"studyId": r.get("studyId"), "cleanReportText": r.get("cleanReportText")} for r in rows]

    if hallazgo is not None and value is not None:
        valid_cols = set(_finding_columns())
        if hallazgo not in valid_cols:
            raise HTTPException(status_code=400, detail=f"Hallazgo desconocido: {hallazgo}")
        where_clauses.append(f'{_quote_ident(hallazgo)} = ?')
        params.append(value)

    # Age range filter (inclusive)
    if "age" in cols:
        where_clauses.append("age BETWEEN ? AND ?")
        params.extend([min_age, max_age])

    # Sample 1k filter (IDs presentes en CSV de 1k)
    if sample_1k:
        if not os.path.exists(SAMPLE_1K_CSV_PATH):
            raise HTTPException(status_code=503, detail=f"CSV 1k no disponible en ruta: {SAMPLE_1K_CSV_PATH}")
        s_uid = _detect_uid_col_in_csv(SAMPLE_1K_CSV_PATH) or "StudyInstanceUID"
        if label_group:
            where_clauses.append(f'"{uid_col}" IN (SELECT DISTINCT "{s_uid}" FROM read_csv_auto(?, header=True) WHERE "group" = ?)')
            params.extend([SAMPLE_1K_CSV_PATH, label_group])
        else:
            where_clauses.append(f'"{uid_col}" IN (SELECT DISTINCT "{s_uid}" FROM read_csv_auto(?, header=True))')
            params.append(SAMPLE_1K_CSV_PATH)

    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    query = base_select + where_sql + f' GROUP BY "{uid_col}" ORDER BY "{uid_col}" LIMIT ? OFFSET ?'
    params.extend([page_size, (page - 1) * page_size])
    rows = _query_csv(query, params)
    return [{"studyId": r.get("studyId"), "cleanReportText": r.get("cleanReportText")} for r in rows]

@app.get("/studies/count")
def get_studies_count(
    hallazgo: str | None = Query(default=None, description="Nombre de la columna de hallazgo a filtrar"),
    value: str | None = Query(default=None, description="Valor del hallazgo (e.g., 'Certainly True')"),
    min_age: int = Query(default=18, ge=0, description="Edad mínima inclusiva"),
    max_age: int = Query(default=100, ge=0, description="Edad máxima inclusiva"),
    sample_1k: bool = Query(default=False, description="Limitar a los StudyInstanceUID presentes en sample 1k"),
    label_group: str | None = Query(default=None, description="Filtrar a los UID cuyo group en el CSV 1k coincida"),
    study_id: str | None = Query(default=None, description="Buscar por StudyInstanceUID exacto; ignora otros filtros"),
):
    try:
        uid_col = _detect_uid_col_in_csv(FINDINGS_CSV) or "StudyInstanceUID"
        cols = set(_csv_columns(FINDINGS_CSV))
        base_select = f'SELECT COUNT(DISTINCT "{uid_col}") AS c FROM read_csv_auto(?, header=True)'
        params: list = [FINDINGS_CSV]
        where_clauses = [f'"{uid_col}" IS NOT NULL']

        # If study_id is provided, short-circuit to exact match count
        if study_id and study_id.strip():
            query = f'SELECT COUNT(*) AS c FROM read_csv_auto(?, header=True) WHERE "{uid_col}" = ?'
            rows = _query_csv(query, [FINDINGS_CSV, study_id.strip()])
            c = rows[0].get("c", 0) if rows else 0
            return {"count": int(c)}

        if hallazgo is not None and value is not None:
            valid_cols = set(_finding_columns())
            if hallazgo not in valid_cols:
                raise HTTPException(status_code=400, detail=f"Hallazgo desconocido: {hallazgo}")
            where_clauses.append(f'{_quote_ident(hallazgo)} = ?')
            params.append(value)

        if min_age > max_age:
            min_age, max_age = max_age, min_age
        if "age" in cols:
            where_clauses.append("age BETWEEN ? AND ?")
            params.extend([min_age, max_age])

        if sample_1k:
            if not os.path.exists(SAMPLE_1K_CSV_PATH):
                raise HTTPException(status_code=503, detail=f"CSV 1k no disponible en ruta: {SAMPLE_1K_CSV_PATH}")
            s_uid = _detect_uid_col_in_csv(SAMPLE_1K_CSV_PATH) or "StudyInstanceUID"
            if label_group:
                where_clauses.append(f'"{uid_col}" IN (SELECT DISTINCT "{s_uid}" FROM read_csv_auto(?, header=True) WHERE "group" = ?)')
                params.extend([SAMPLE_1K_CSV_PATH, label_group])
            else:
                where_clauses.append(f'"{uid_col}" IN (SELECT DISTINCT "{s_uid}" FROM read_csv_auto(?, header=True))')
                params.append(SAMPLE_1K_CSV_PATH)

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        query = base_select + where_sql
        rows = _query_csv(query, params)
        count = rows[0].get("c", 0) if rows else 0
        return {"count": int(count)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/label_groups")
def get_label_groups():
    try:
        mapping = _load_label_groups()
        groups = sorted(mapping.keys())
        return {"groups": groups, "mapping": mapping}
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

@app.get("/studies/{study_id}/text-info")
def get_study_text_info(study_id: str):
    """Return textual information assembled from the three CSV sources using StudyInstanceUID.

    This function auto-detects the UID column name in each CSV (StudyInstanceUID/studyInstanceUID/StudyID/studyID)
    and uses the current CSVs as the single source of truth (no anon mapping required).
    """
    try:
        if not (os.path.exists(FINDINGS_CSV) and os.path.exists(SECTIONS_CSV) and os.path.exists(SENTENCES_CSV)):
            missing = [p for p in (FINDINGS_CSV, SECTIONS_CSV, SENTENCES_CSV) if not os.path.exists(p)]
            raise HTTPException(status_code=503, detail=f"CSV(s) faltantes: {', '.join(missing)}")

        # Detect UID columns per CSV
        f_uid = _detect_uid_col_in_csv(FINDINGS_CSV)
        sec_uid = _detect_uid_col_in_csv(SECTIONS_CSV)
        sen_uid = _detect_uid_col_in_csv(SENTENCES_CSV)
        if not all([f_uid, sec_uid, sen_uid]):
            raise HTTPException(status_code=500, detail="No se pudo detectar columna UID en uno o más CSV (findings/sections/sentences)")

        # Discover label columns from findings (exclude metadata + uid)
        all_cols = _csv_columns(FINDINGS_CSV)
        meta_cols = {
            'clean_report_text', 'studyID', 'StudyID', 'StudyInstanceUID', 'studyInstanceUID',
            'age', 'views', 'study_date', 'regex_labels', 'report_text', 'report_path', 'llm_labels'
        }
        meta_cols.add(f_uid)
        label_cols = [c for c in all_cols if c and c not in meta_cols]

        # Findings row
        findings_sql = f'SELECT * FROM read_csv_auto(?, header=True) WHERE "{f_uid}" = ? LIMIT 1'
        f_rows = _query_csv(findings_sql, [FINDINGS_CSV, study_id])
        findings_block: Dict[str, Any] | None = None
        if f_rows:
            row = f_rows[0]
            label_status: Dict[str, Any] = {}
            for col in label_cols:
                val = row.get(col)
                if val is not None and val != "":
                    label_status[col] = val
            findings_block = {
                "study_date": row.get("study_date"),
                "age": row.get("age"),
                "report_text": row.get("report_text") or row.get("clean_report_text"),
                "regex_labels": row.get("regex_labels"),
                "llm_labels": row.get("llm_labels"),
                "label_status": label_status,
            }

        # Sections
        sections_sql = f'SELECT * FROM read_csv_auto(?, header=True) WHERE "{sec_uid}" = ? LIMIT 1'
        s_rows = _query_csv(sections_sql, [SECTIONS_CSV, study_id])
        sections_block: Dict[str, Any] | None = None
        if s_rows:
            s = s_rows[0]
            sections_block = {
                "projections": s.get("projections"),
                "history": s.get("history"),
                "original_report": s.get("original_report") or s.get("report_text"),
                "finding_sentences_es": s.get("finding_sentences_es"),
                "finding_sentences_en": s.get("finding_sentences_en"),
                "labels_list": s.get("labels_list"),
            }

        # Sentences (supports mapped schema: sentenceID, sentence, label, group)
        sentences_sql = f'SELECT * FROM read_csv_auto(?, header=True) WHERE "{sen_uid}" = ?'
        sent_rows = _query_csv(sentences_sql, [SENTENCES_CSV, study_id])
        # Basic projection keeping compatibility on naming
        sentences = [
            {
                "sentence_index": r.get("sentence_index") or r.get("sentenceID"),
                "sentence_text": r.get("sentence_text") or r.get("sentence"),
                "positive_or_not": r.get("positive_or_not"),
                "findings_affirmed": r.get("findings_affirmed"),
                "label": r.get("label"),
                "group": r.get("group"),
            }
            for r in sent_rows
        ]

        return {
            "studyId": study_id,
            "findings": findings_block,
            "sections": sections_block,
            "sentences": sentences,
            "sources": {
                "findings_csv": FINDINGS_CSV,
                "sections_csv": SECTIONS_CSV,
                "sentences_csv": SENTENCES_CSV,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/studies")
async def add_study(study: Study):
    with duckdb.connect(DB_PATH) as con:
        con.execute("INSERT INTO studies VALUES (?, ?)", [study.id, study.name])
    return {"ok": True}
