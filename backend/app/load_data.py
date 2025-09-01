import duckdb
import os

DB_PATH = os.environ.get("DUCKDB_PATH", "/data/app.duckdb")
# If running in container with dev overlay, data is mounted at /data_in; otherwise use repo-relative path
DATA_PATH = "/mnt/nas_anakena/datasets/uc-cxr/processed_data/reports_and_labels_llm"

def build_db():
    con = duckdb.connect(DB_PATH)
    con.execute("DROP TABLE IF EXISTS reports")

    # Cargar datos principales (CSV disponible en repo)
    con.execute(f"""
        CREATE TABLE reports AS
        SELECT * FROM read_csv_auto('{DATA_PATH}/100k_llm_findings_labels.csv')
    """)

    # Cargar el CSV extra de secciones (ejemplo)
    con.execute("DROP TABLE IF EXISTS sections")
    con.execute(f"""
        CREATE TABLE sections AS
        SELECT * FROM read_csv_auto('{DATA_PATH}/sections_of_report.csv')
    """)

    con.close()
    print(f"DuckDB built at {DB_PATH}")

if __name__ == "__main__":
    build_db()
