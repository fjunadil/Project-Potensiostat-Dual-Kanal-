from __future__ import annotations

from pathlib import Path
from typing import Any


class RodeostatConnectionError(RuntimeError):
    pass


def connect_rodeostat(port: str):
    try:
        from potentiostat import Potentiostat
    except ImportError as exc:
        raise RodeostatConnectionError(
            "Library iorodeo-potentiostat belum terpasang. "
            "Jalankan: pip install iorodeo-potentiostat"
        ) from exc

    try:
        return Potentiostat(port)
    except Exception as exc:
        raise RodeostatConnectionError(
            f"Gagal membuka Rodeostat pada port {port}: {exc}"
        ) from exc


def run_cyclic_voltammetry(
    port: str,
    parameters: dict[str, Any],
    output_file: str | Path,
):
    return run_voltammetry(
        port=port,
        test_name="cyclic",
        parameters=parameters,
        output_file=output_file,
    )


def run_square_wave_voltammetry(
    port: str,
    parameters: dict[str, Any],
    output_file: str | Path,
):
    return run_voltammetry(
        port=port,
        test_name="squareWave",
        parameters=parameters,
        output_file=output_file,
    )


def run_rodeostat_test(
    port: str,
    test_name: str,
    parameters: dict[str, Any],
    output_file: str | Path,
):
    return run_voltammetry(
        port=port,
        test_name=test_name,
        parameters=parameters,
        output_file=output_file,
    )


def run_voltammetry(
    port: str,
    test_name: str,
    parameters: dict[str, Any],
    output_file: str | Path,
):
    pstat = connect_rodeostat(port)
    try:
        device_parameters = prepare_device_parameters(pstat, test_name, parameters)
        return pstat.run_test(test_name, param=device_parameters, filename=str(output_file))
    except Exception as exc:
        raise RodeostatConnectionError(
            "Komunikasi Rodeostat terputus atau port serial sedang dipakai proses lain. "
            f"Port: {port}. Detail: {exc}"
        ) from exc


def prepare_device_parameters(pstat: Any, test_name: str, parameters: dict[str, Any]) -> dict[str, Any]:
    control_keys = {"currentRange", "sampleRate"}
    if "sampleRate" in parameters:
        sample_rate = float(parameters["sampleRate"])
        if sample_rate > 0:
            pstat.set_sample_period(max(1, int(round(1000 / sample_rate))))

    if "currentRange" in parameters:
        pstat.set_curr_range(str(parameters["currentRange"]).replace(" ", ""))

    if test_name != "cyclic":
        return {
            key: _coerce_device_parameter(key, value)
            for key, value in parameters.items()
            if key not in control_keys
        }

    device_parameters: dict[str, Any] = {}
    if "quietValue" in parameters:
        device_parameters["quietValue"] = float(parameters["quietValue"])
    if "quietTime" in parameters:
        device_parameters["quietTime"] = int(round(float(parameters["quietTime"]) * 1000))
    if "numCycles" in parameters:
        device_parameters["numCycles"] = int(float(parameters["numCycles"]))

    if "startValue" in parameters and "vertex1Value" in parameters:
        start_value = float(parameters["startValue"])
        vertex_value = float(parameters["vertex1Value"])
        low = min(start_value, vertex_value)
        high = max(start_value, vertex_value)
        amplitude = abs(high - low) / 2
        device_parameters["amplitude"] = amplitude
        device_parameters["offset"] = (high + low) / 2
        if "scanRate" in parameters and float(parameters["scanRate"]) > 0 and amplitude > 0:
            device_parameters["period"] = int(round((4 * amplitude / float(parameters["scanRate"])) * 1000))

    return device_parameters


def _coerce_device_parameter(key: str, value: Any) -> Any:
    if key == "step":
        return _parse_step_sequence(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return stripped
        try:
            numeric = float(stripped)
        except ValueError:
            return stripped
        if key in {"quietTime", "duration", "period", "numCycles"}:
            return int(round(numeric))
        return numeric
    return value


def _parse_step_sequence(value: Any) -> list[tuple[int, float]]:
    if isinstance(value, list):
        parsed: list[tuple[int, float]] = []
        for item in value:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise ValueError("step harus berisi pasangan duration:value")
            parsed.append((int(round(float(item[0]))), float(item[1])))
        return parsed

    text = str(value).strip()
    if not text:
        raise ValueError("step tidak boleh kosong")

    parsed = []
    for item in text.split(","):
        if ":" in item:
            duration, voltage = item.split(":", 1)
        elif "=" in item:
            duration, voltage = item.split("=", 1)
        else:
            parts = item.split()
            if len(parts) != 2:
                raise ValueError("format step harus duration:voltage, contoh 1000:-0.25,1000:0.5")
            duration, voltage = parts
        parsed.append((int(round(float(duration.strip()))), float(voltage.strip())))
    return parsed
