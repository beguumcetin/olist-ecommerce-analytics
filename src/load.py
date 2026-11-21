"""Load the Olist CSVs into a local DuckDB file and build the analysis tables.

The dataset is free on Kaggle (needs an account, download it yourself):
https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
Put the downloaded zip, or the CSVs inside it, in data/raw/.

    python -m src.load
"""

import sys
import zipfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "olist.duckdb"
SQL_DIR = ROOT / "sql"

# CSV file name -> raw table name
TABLES = {
    "olist_orders_dataset.csv": "raw_orders",
    "olist_order_items_dataset.csv": "raw_order_items",
    "olist_order_payments_dataset.csv": "raw_order_payments",
    "olist_order_reviews_dataset.csv": "raw_order_reviews",
    "olist_customers_dataset.csv": "raw_customers",
    "olist_sellers_dataset.csv": "raw_sellers",
    "olist_products_dataset.csv": "raw_products",
    "product_category_name_translation.csv": "raw_category_translation",
}


def unzip_if_needed(raw_dir: Path):
    for z in raw_dir.glob("*.zip"):
        with zipfile.ZipFile(z) as f:
            for name in f.namelist():
                if Path(name).name in TABLES and not (raw_dir / Path(name).name).exists():
                    (raw_dir / Path(name).name).write_bytes(f.read(name))


def find_csv_dir(raw_dir: Path) -> Path:
    """Safari unzips downloads into a subfolder, so look one level down too."""
    for d in [raw_dir, *sorted(p for p in raw_dir.iterdir() if p.is_dir())]:
        if (d / "olist_orders_dataset.csv").exists():
            return d
    return raw_dir


def main(raw_dir: Path = RAW_DIR, db_path: Path = DB_PATH):
    unzip_if_needed(raw_dir)
    raw_dir = find_csv_dir(raw_dir)
    missing = [f for f in TABLES if not (raw_dir / f).exists()]
    if missing:
        sys.exit(f"Missing in {raw_dir}: {', '.join(missing)}\nDownload the dataset first (see the docstring).")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    for file, table in TABLES.items():
        con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM read_csv_auto(?, header=true)",
                    [str(raw_dir / file)])
        print(f"{table:26s} {con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]:>8,} rows")

    for sql_file in sorted(SQL_DIR.glob("*.sql")):
        con.execute(sql_file.read_text())
        print(f"ran {sql_file.name}")
    con.close()


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else RAW_DIR)
