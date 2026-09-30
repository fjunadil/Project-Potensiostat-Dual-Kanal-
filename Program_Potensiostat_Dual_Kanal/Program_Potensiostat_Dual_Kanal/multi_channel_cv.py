from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

from config import (
    METHOD_DEFINITIONS,
    MUX_CHANNELS,
    RAW_DATA_DIR,
    RODEOSTAT_PORT,
)
from mux_gpio import GpioUnavailableError, MuxController
from src.analysis import CurveSummary, save_curve_summaries, summarize_curve
from src.file_manager import save_json, timestamped_path
from src.measurement import (
    RodeostatConnectionError,
    run_rodeostat_test,
)
from src.plotter import plot_multiple_voltammograms


METHOD_CONFIG = {
    key: (
        str(definition["prefix"]),
        str(definition["title"]),
        definition["parameters"],
        str(definition["test_name"]),
    )
    for key, definition in METHOD_DEFINITIONS.items()
}


def parse_parameter_overrides(values: list[str]) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for value in values:
        if "=" not in value:
            raise argparse.ArgumentTypeError("format parameter harus key=value")

        key, raw = value.split("=", 1)
        key = key.strip()
        raw = raw.strip()
        if not key:
            raise argparse.ArgumentTypeError("nama parameter tidak boleh kosong")

        try:
            overrides[key] = float(raw)
        except ValueError:
            overrides[key] = raw

    return overrides


def run_channel_measurement(
    port: str,
    channel: int,
    method: str,
    parameters: dict[str, Any],
) -> tuple[Path, list[float], list[float]]:
    prefix, _, _, test_name = METHOD_CONFIG[method]
    data_file = timestamped_path(RAW_DATA_DIR, f"{prefix}_channel{channel}", ".txt")
    _, potential_v, current = run_rodeostat_test(
        port=port,
        test_name=test_name,
        parameters=parameters,
        output_file=data_file,
    )
    return data_file, list(potential_v), list(current)


def run_multi_channel_cv(
    port: str = RODEOSTAT_PORT,
    channels: tuple[int, ...] = (1, 2),
    method: str = "cv",
    parameter_overrides: dict[str, Any] | None = None,
    measurement_info: dict[str, Any] | None = None,
    show_plot: bool = True,
) -> tuple[list[Path], Path, Path, Path]:
    prefix, title, default_parameters, _ = METHOD_CONFIG[method]
    parameters = dict(default_parameters)
    parameters.update(parameter_overrides or {})

    mux = MuxController()
    data_files: list[Path] = []
    curves = []
    summaries: list[CurveSummary] = []

    try:
        for channel in channels:
            print(f"Mengaktifkan Channel {channel}...")
            mux.set_channel(channel, wait=True)

            print(f"Menjalankan {title} Channel {channel}...")
            data_file, potential_v, current = run_channel_measurement(
                port=port,
                channel=channel,
                method=method,
                parameters=parameters,
            )
            data_files.append(data_file)
            curves.append((potential_v, current, f"Channel {channel}"))
            summaries.append(summarize_curve(channel, potential_v, current))
    finally:
        mux.cleanup()

    plot_file = timestamped_path(RAW_DATA_DIR, f"{prefix}_multi_channel", ".png")
    plot_multiple_voltammograms(
        curves,
        title=f"{title} Multi-Channel",
        output_path=plot_file,
        show=show_plot,
        peaks=[
            peak
            for summary in summaries
            for peak in (
                (summary.channel, summary.max_current_potential, summary.max_current, "Oksidasi"),
                (summary.channel, summary.min_current_potential, summary.min_current, "Reduksi"),
            )
        ],
    )

    analysis_file = timestamped_path(RAW_DATA_DIR, f"{prefix}_analysis", ".csv")
    save_curve_summaries(analysis_file, summaries)

    info_file = timestamped_path(RAW_DATA_DIR, f"{prefix}_info", ".json")
    save_json(
        info_file,
        {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "method": method,
            "method_title": title,
            "port": port,
            "channels": list(channels),
            "parameters": parameters,
            "data_files": [str(path) for path in data_files],
            "plot_file": str(plot_file),
            "analysis_file": str(analysis_file),
            "preset": (measurement_info or {}).get("preset", ""),
        },
    )

    return data_files, plot_file, analysis_file, info_file


def parse_channels(value: str) -> tuple[int, ...]:
    channels = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not channels:
        raise argparse.ArgumentTypeError("minimal satu channel diperlukan")
    if any(channel not in MUX_CHANNELS for channel in channels):
        raise argparse.ArgumentTypeError("channel hanya boleh 1 atau 2")
    return channels


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Rodeostat measurement with CD4051 channel selection")
    parser.add_argument("--port", default=RODEOSTAT_PORT, help="Port Rodeostat")
    parser.add_argument("--channels", type=parse_channels, default=(1, 2), help="Contoh: 1,2 atau 1")
    parser.add_argument("--method", choices=METHOD_CONFIG.keys(), default="cv", help="Metode pengukuran")
    parser.add_argument("--param", action="append", default=[], help="Override parameter, contoh: scanRate=0.05")
    parser.add_argument("--no-show", action="store_true", help="Simpan plot tanpa tampilkan window")
    args = parser.parse_args()

    try:
        data_files, plot_file, analysis_file, info_file = run_multi_channel_cv(
            port=args.port,
            channels=args.channels,
            method=args.method,
            parameter_overrides=parse_parameter_overrides(args.param),
            measurement_info={},
            show_plot=not args.no_show,
        )
    except (GpioUnavailableError, RodeostatConnectionError) as exc:
        raise SystemExit(str(exc)) from exc

    for data_file in data_files:
        print(f"Data tersimpan: {data_file}")
    print(f"Plot tersimpan: {plot_file}")
    print(f"Analisis peak tersimpan: {analysis_file}")
    print(f"Info pengukuran tersimpan: {info_file}")


if __name__ == "__main__":
    main()
