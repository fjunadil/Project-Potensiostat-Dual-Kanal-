from __future__ import annotations

from dataclasses import dataclass
from time import sleep

from config import (
    DEFAULT_STABILIZATION_SECONDS,
    MUX_ADDRESS_BY_CHANNEL,
    MUX_CHANNELS,
    MUX_PINS,
)


class GpioUnavailableError(RuntimeError):
    pass


@dataclass
class MuxController:
    s0: int = MUX_PINS["s0"]
    stabilization_seconds: float = DEFAULT_STABILIZATION_SECONDS

    def __post_init__(self) -> None:
        try:
            import RPi.GPIO as GPIO
        except ImportError as exc:
            raise GpioUnavailableError(
                "RPi.GPIO hanya tersedia di Raspberry Pi. "
                "Jalankan script ini langsung pada Raspberry Pi OS."
            ) from exc

        self.GPIO = GPIO
        self.GPIO.setmode(self.GPIO.BCM)
        self.GPIO.setup(self.s0, self.GPIO.OUT, initial=self.GPIO.LOW)

    def set_channel(self, channel: int, wait: bool = True) -> None:
        if channel not in MUX_CHANNELS:
            raise ValueError("channel hanya boleh 1 atau 2")

        mux_address = MUX_ADDRESS_BY_CHANNEL[channel]
        self.GPIO.output(self.s0, mux_address & 0x01)

        if wait and self.stabilization_seconds > 0:
            sleep(self.stabilization_seconds)

    def cleanup(self) -> None:
        self.GPIO.cleanup(self.s0)


def main() -> None:
    mux = MuxController()
    try:
        channel = int(input("Pilih channel sistem (1/2): "))
        mux.set_channel(channel)
        print(f"Channel {channel} aktif")
    finally:
        mux.cleanup()


if __name__ == "__main__":
    main()
