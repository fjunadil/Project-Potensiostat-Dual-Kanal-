from __future__ import annotations

import os
import subprocess
import sys

from touchscreen_fix import apply_touchscreen_axis_swap


def available_displays(preferred_display: str | None = None) -> list[str]:
    displays = []
    x11_dir = "/tmp/.X11-unix"
    if os.path.isdir(x11_dir):
        for name in sorted(os.listdir(x11_dir)):
            if name.startswith("X") and name[1:].isdigit():
                displays.append(f":{name[1:]}")

    preferred = []
    if preferred_display:
        preferred.append(preferred_display)
    preferred.extend([":0", ":1"])

    ordered = []
    for display in preferred + displays:
        if display not in ordered:
            ordered.append(display)
    return ordered


def main() -> int:
    preferred_display = None
    if "--display" in sys.argv:
        index = sys.argv.index("--display")
        try:
            preferred_display = sys.argv[index + 1]
        except IndexError:
            print("Gunakan format: python3 run_gui.py --display :0")
            return 1

    env = os.environ.copy()
    if env.get("DISPLAY"):
        apply_touchscreen_axis_swap()
        return subprocess.call([sys.executable, "dashboard.py"], env=env)

    for display in available_displays(preferred_display):
        env["DISPLAY"] = display
        os.environ["DISPLAY"] = display
        apply_touchscreen_axis_swap()
        print(f"Mencoba membuka GUI pada DISPLAY={display}")
        result = subprocess.run(
            [sys.executable, "dashboard.py"],
            env=env,
            text=True,
            capture_output=True,
        )
        if result.returncode == 0:
            return 0

        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)

    print("GUI tidak bisa dibuka karena tidak ada display grafis yang dapat diakses.")
    print("Buka terminal dari desktop/VNC Raspberry Pi, atau jalankan:")
    print("DISPLAY=:1 python3 dashboard.py")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
