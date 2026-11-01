"""Build the official H2 test prediction file and team submission ZIP."""
from pathlib import Path
import shutil, subprocess, sys, zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "submission" / "H2_predictions.jsonl"
TEAM_ZIP = ROOT / "teamID_H2.zip"


def main():
    generator = ROOT / "FULL_CODE" / "hackathon_pipeline.py"
    subprocess.run([sys.executable, str(generator), "--split", "test", "--out", str(OUT)], check=True)
    # Confirm exact row count and valid JSON before packaging.
    import json, csv
    ids_file = ROOT / "HACKATHON_STARTER_PACK" / "data" / "test_ids.csv"
    with ids_file.open(encoding="utf-8-sig", newline="") as f:
        expected = {r["summary_id"] for r in csv.DictReader(f)}
    rows=[]
    with OUT.open(encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    got={r.get("summary_id") for r in rows}
    if len(rows) != 300 or got != expected:
        raise SystemExit(f"Submission validation failed: {len(rows)} rows, {len(got)} unique IDs, expected {len(expected)} test IDs")
    if any(r.get("translation",{}).get("language_code") != "te" for r in rows):
        raise SystemExit("Submission validation failed: translation language must be te")
    include=["README.md", "FULL_CODE", "HACKATHON_STARTER_PACK", "submission/H2_predictions.jsonl"]
    with zipfile.ZipFile(TEAM_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for item in include:
            path=ROOT/item
            if path.is_file():
                z.write(path, item)
            elif path.is_dir():
                for file in path.rglob("*"):
                    if file.is_file() and not any(part in {"__pycache__", ".pytest_cache", ".venv"} for part in file.parts):
                        z.write(file, file.relative_to(ROOT).as_posix())
    print(f"Validated {len(rows)} test predictions for {len(expected)} test IDs.")
    print(f"Team package created: {TEAM_ZIP}")
    print("Rename teamID_H2.zip using your actual team ID before submission if required by the organiser.")

if __name__ == "__main__":
    main()
