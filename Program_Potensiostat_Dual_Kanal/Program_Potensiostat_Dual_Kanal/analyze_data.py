from __future__ import annotations

import argparse
from pathlib import Path

from config import RAW_DATA_DIR
from src.analysis import save_curve_summaries, summarize_curve
from src.file_manager import read_rodeostat_rows, timestamped_path


def infer_channel(path: Path) -> int:
    name = path.stem.lower()
    if "channel2" in name or "ch2" in name:
        return 2
    return 1


def analyze_files(files: list[Path], output: Path | None = None) -> Path:
    summaries = []
    for file_path in files:
        rows = read_rodeostat_rows(file_path)
        if not rows:
            raise ValueError(f"file tidak berisi data voltammogram: {file_path}")

        _, potential, current = zip(*rows)
        summaries.append(summarize_curve(infer_channel(file_path), potential, current))

    output_path = output or timestamped_path(RAW_DATA_DIR, "analysis_manual", ".csv")
    return save_curve_summaries(output_path, summaries)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analisis peak data Rodeostat yang sudah tersimpan")
    parser.add_argument("files", nargs="+", type=Path, help="File data .txt/.csv Rodeostat")
    parser.add_argument("--output", type=Path, help="File output CSV")
    args = parser.parse_args()

    try:
        output = analyze_files(args.files, args.output)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"Analisis tersimpan: {output}")


if __name__ == "__main__":
    main()
