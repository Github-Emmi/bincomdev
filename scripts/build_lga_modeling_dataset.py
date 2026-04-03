#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.election_ml_pipeline import export_ml_artifacts


def main():
    parser = argparse.ArgumentParser(
        description="Build the Bincom LGA-level modeling dataset and descriptive CSV outputs."
    )
    parser.add_argument("--db", default="db.sqlite3", help="Path to the SQLite database.")
    parser.add_argument(
        "--out",
        default="analysis_outputs",
        help="Directory where CSV artifacts will be written.",
    )
    args = parser.parse_args()

    outputs = export_ml_artifacts(db_path=args.db, out_dir=args.out)
    for path in outputs.values():
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
