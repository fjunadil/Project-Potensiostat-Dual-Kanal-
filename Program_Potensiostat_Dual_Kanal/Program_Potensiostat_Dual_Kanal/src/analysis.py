from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class CurveSummary:
    channel: int
    points: int
    max_current: float
    max_current_potential: float
    min_current: float
    min_current_potential: float
    absolute_peak_current: float
    absolute_peak_potential: float
    delta_peak_potential: float


def _edge_margin(length: int) -> int:
    if length < 20:
        return 0
    return max(1, int(round(length * 0.05)))


def _interior_indices(length: int) -> range:
    margin = _edge_margin(length)
    return range(max(1, margin), min(length - 1, length - margin))


def _local_extreme_index(values: Sequence[float], mode: str) -> int | None:
    candidates: list[int] = []
    for index in _interior_indices(len(values)):
        previous_value = float(values[index - 1])
        value = float(values[index])
        next_value = float(values[index + 1])
        if mode == "max" and value >= previous_value and value > next_value:
            candidates.append(index)
        elif mode == "min" and value <= previous_value and value < next_value:
            candidates.append(index)

    if not candidates:
        return None
    if mode == "max":
        return max(candidates, key=lambda index: float(values[index]))
    return min(candidates, key=lambda index: float(values[index]))


def _peak_index(values: Sequence[float], mode: str) -> int:
    local_index = _local_extreme_index(values, mode)
    if local_index is not None:
        return local_index
    if mode == "max":
        return max(range(len(values)), key=lambda index: float(values[index]))
    return min(range(len(values)), key=lambda index: float(values[index]))


def summarize_curve(channel: int, potential: Sequence[float], current: Sequence[float]) -> CurveSummary:
    if not potential or not current:
        raise ValueError("potential dan current tidak boleh kosong")
    if len(potential) != len(current):
        raise ValueError("panjang potential dan current harus sama")

    max_index = _peak_index(current, "max")
    min_index = _peak_index(current, "min")
    absolute_index = max((max_index, min_index), key=lambda index: abs(float(current[index])))

    return CurveSummary(
        channel=channel,
        points=len(current),
        max_current=float(current[max_index]),
        max_current_potential=float(potential[max_index]),
        min_current=float(current[min_index]),
        min_current_potential=float(potential[min_index]),
        absolute_peak_current=float(current[absolute_index]),
        absolute_peak_potential=float(potential[absolute_index]),
        delta_peak_potential=abs(float(potential[max_index]) - float(potential[min_index])),
    )


def save_curve_summaries(path: str | Path, summaries: Sequence[CurveSummary]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = list(asdict(summaries[0]).keys()) if summaries else [
        "channel",
        "points",
        "max_current",
        "max_current_potential",
        "min_current",
        "min_current_potential",
        "absolute_peak_current",
        "absolute_peak_potential",
        "delta_peak_potential",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for summary in summaries:
            writer.writerow(asdict(summary))

    return output_path
