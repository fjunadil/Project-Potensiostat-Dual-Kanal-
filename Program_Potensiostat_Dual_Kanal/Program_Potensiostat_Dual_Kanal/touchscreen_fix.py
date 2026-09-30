from __future__ import annotations

import os
import re
import shutil
import subprocess


TOUCH_DEVICE_PATTERN = re.compile(
    r"(touch|touchscreen|goodix|ft5x06|ads7846|waveshare|evdev)",
    re.IGNORECASE,
)

SWAP_XY_MATRIX = ("0", "1", "0", "1", "0", "0", "0", "0", "1")
ADS7846_CALIBRATION = ("227", "3936", "3880", "268")
ADS7846_SWAP_AXES = ("1",)
ADS7846_AXIS_INVERSION = ("0", "0")


def _touch_device_ids(xinput_output: str) -> list[str]:
    device_ids: list[str] = []
    for line in xinput_output.splitlines():
        if not TOUCH_DEVICE_PATTERN.search(line):
            continue
        match = re.search(r"\bid=(\d+)\b", line)
        if match:
            device_ids.append(match.group(1))
    return device_ids


def _set_prop(device_id: str, prop_name: str, values: tuple[str, ...]) -> bool:
    result = subprocess.run(
        ["xinput", "set-prop", device_id, prop_name, *values],
        text=True,
        capture_output=True,
        check=False,
        timeout=3,
    )
    return result.returncode == 0


def apply_touchscreen_axis_swap() -> list[str]:
    """Calibrate ADS7846 touch direction on Raspberry Pi X11."""
    if os.name == "nt" or os.environ.get("POTENTIOSTAT_SKIP_TOUCH_FIX") == "1":
        return []
    if not os.environ.get("DISPLAY") or shutil.which("xinput") is None:
        return []

    try:
        result = subprocess.run(
            ["xinput", "list"],
            text=True,
            capture_output=True,
            check=False,
            timeout=3,
        )
    except Exception:
        return []

    if result.returncode != 0:
        return []

    updated: list[str] = []
    for device_id in _touch_device_ids(result.stdout):
        ok = _set_prop(
            device_id,
            "Coordinate Transformation Matrix",
            SWAP_XY_MATRIX,
        )
        _set_prop(device_id, "Evdev Axis Calibration", ADS7846_CALIBRATION)
        _set_prop(device_id, "Evdev Axes Swap", ADS7846_SWAP_AXES)
        _set_prop(device_id, "Evdev Axis Inversion", ADS7846_AXIS_INVERSION)
        if ok:
            updated.append(device_id)
    return updated
