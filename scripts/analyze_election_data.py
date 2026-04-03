import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.election_ml_pipeline import export_ml_artifacts


def main():
    parser = argparse.ArgumentParser(
        description="Export simple analytics tables from the Bincom SQLite database."
    )
    parser.add_argument("--db", default="db.sqlite3", help="Path to the SQLite database.")
    parser.add_argument(
        "--out",
        default="analysis_outputs",
        help="Directory for generated CSV outputs.",
    )
    args = parser.parse_args()
    output_dir = Path(args.out)
    outputs = export_ml_artifacts(db_path=args.db, out_dir=output_dir)
    for key in ("lga_summary", "party_share", "polling_unit_completeness"):
        print(f"Wrote {outputs[key]}")


if __name__ == "__main__":
    main()
