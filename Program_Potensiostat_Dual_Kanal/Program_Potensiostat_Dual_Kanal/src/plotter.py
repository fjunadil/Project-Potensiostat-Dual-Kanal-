from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _format_peak_label(channel: int, potential: float, current: float, peak_name: str) -> str:
    return f"{peak_name} Ch {channel}\n{current:.3e} ÂµA @ {potential:.3f} V"


def _annotate_peak(ax, channel: int, potential: float, current: float, peak_name: str) -> None:
    ax.scatter([potential], [current], s=46, marker="o", edgecolors="black", linewidths=0.8, zorder=5)
    ax.annotate(
        _format_peak_label(channel, potential, current, peak_name),
        xy=(potential, current),
        xytext=(10, 14),
        textcoords="offset points",
        fontsize=8,
        arrowprops={"arrowstyle": "->", "linewidth": 0.8},
        bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "edgecolor": "#555555", "alpha": 0.85},
    )


def plot_voltammogram(
    potential: Sequence[float],
    current: Sequence[float],
    title: str = "Voltammogram",
    label: str | None = None,
    output_path: str | Path | None = None,
    show: bool = True,
    peak: tuple[int, float, float] | tuple[int, float, float, str] | None = None,
) -> Path | None:
    fig, ax = plt.subplots()
    ax.plot(potential, current, label=label)
    if peak is not None:
        peak_name = peak[3] if len(peak) > 3 else "Peak"
        _annotate_peak(ax, peak[0], peak[1], peak[2], peak_name)
    ax.set_xlabel("Potential (V)")
    ax.set_ylabel("Current (ÂµA)")
    ax.set_title(title)
    ax.grid(True)

    if label:
        ax.legend()

    saved_path = None
    if output_path is not None:
        saved_path = Path(output_path)
        saved_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(saved_path, dpi=300, bbox_inches="tight")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return saved_path


def plot_multiple_voltammograms(
    curves: Iterable[tuple[Sequence[float], Sequence[float], str]],
    title: str = "Cyclic Voltammetry",
    output_path: str | Path | None = None,
    show: bool = True,
    peaks: Iterable[tuple[int, float, float] | tuple[int, float, float, str]] | None = None,
) -> Path | None:
    fig, ax = plt.subplots()

    for potential, current, label in curves:
        ax.plot(potential, current, label=label)

    if peaks is not None:
        for peak in peaks:
            peak_name = peak[3] if len(peak) > 3 else "Peak"
            _annotate_peak(ax, peak[0], peak[1], peak[2], peak_name)

    ax.set_xlabel("Potential (V)")
    ax.set_ylabel("Current (ÂµA)")
    ax.set_title(title)
    ax.grid(True)
    ax.legend()

    saved_path = None
    if output_path is not None:
        saved_path = Path(output_path)
        saved_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(saved_path, dpi=300, bbox_inches="tight")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return saved_path
