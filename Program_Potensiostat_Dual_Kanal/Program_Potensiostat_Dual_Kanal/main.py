from __future__ import annotations

from config import DEFAULT_CV_PARAMETERS, MUX_PINS, RODEOSTAT_PORT


def main() -> None:
    print("Potentiostat Portable Raspberry Pi")
    print(f"Port Rodeostat default: {RODEOSTAT_PORT}")
    print(f"Pin MUX BCM: S0={MUX_PINS['s0']} (S1 dan S2 CD4051 ke GND)")
    print(f"Parameter CV default: {DEFAULT_CV_PARAMETERS}")
    print("Gunakan multi_channel_cv.py untuk Channel 1/2 atau salah satu channel.")


if __name__ == "__main__":
    main()
