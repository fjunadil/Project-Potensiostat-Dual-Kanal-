from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


def ensure_directory(path: str | Path) -> Path:
    folder = Path(path)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def timestamped_path(folder: str | Path, prefix: str, suffix: str) -> Path:
    ensure_directory(folder)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(folder) / f"{prefix}_{timestamp}{suffix}"


def save_voltammogram_csv(
    path: str | Path,
    time_s: Sequence[float],
    potential_v: Sequence[float],
    current: Sequence[float],
) -> Path:
    output_path = Path(path)
    ensure_directory(output_path.parent)

    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["time_s", "potential_v", "current"])
        writer.writerows(zip(time_s, potential_v, current))

    return output_path


def read_rodeostat_rows(path: str | Path) -> list[tuple[float, float, float]]:
    rows: list[tuple[float, float, float]] = []

    with Path(path).open("r", encoding="utf-8") as data_file:
        for line in data_file:
            stripped = line.strip()
            if not stripped or stripped.lower().startswith("time"):
                continue

            parts = [part.strip() for part in stripped.replace(",", " ").split()]
            if len(parts) < 3:
                continue

            rows.append((float(parts[0]), float(parts[1]), float(parts[2])))

    return rows


def save_json(path: str | Path, data: dict[str, Any]) -> Path:
    output_path = Path(path)
    ensure_directory(output_path.parent)

    with output_path.open("w", encoding="utf-8") as json_file:
        json.dump(data, json_file, indent=2)

    return output_path
