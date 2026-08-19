"""Čtení DS18B20 z 1-Wire.

Jedno čtení trvá ~750 ms, proto se volá výhradně z řídicího vlákna,
nikdy z HTTP requestu.
"""

import glob
import logging
import random
import time

from . import config

log = logging.getLogger(__name__)

W1_DIR = "/sys/bus/w1/devices"


def list_sensors() -> list[str]:
    """Vrátí ID všech čidel na sběrnici, např. ['28-3c01d607abcd']."""
    return sorted(p.split("/")[-1] for p in glob.glob(f"{W1_DIR}/28-*"))


def read_sensor(sensor_id: str) -> float | None:
    """Teplota ve °C, nebo None při chybě CRC / nedostupném čidle."""
    try:
        with open(f"{W1_DIR}/{sensor_id}/w1_slave") as fh:
            lines = fh.readlines()
    except OSError:
        return None

    if len(lines) < 2 or not lines[0].strip().endswith("YES"):
        return None  # CRC neprošlo

    marker = lines[1].find("t=")
    if marker == -1:
        return None

    raw = int(lines[1][marker + 2:])
    if raw == 85000:
        return None  # 85 °C = výchozí hodnota po resetu, není to měření

    return raw / 1000.0


class SensorHub:
    """Drží poslední platnou hodnotu a její stáří pro každou místnost."""

    def __init__(self, hardware=None):
        self._hw = hardware
        self._last: dict[str, tuple[float, float]] = {}
        self._sim = {room: 21.0 + random.uniform(-0.5, 0.5) for room in config.ROOMS}
        self._sim_t = time.monotonic()

    def read_all(self) -> dict[str, dict]:
        out = {}
        for room, cfg in config.ROOMS.items():
            sensor_id = cfg["sensor"]

            if sensor_id:
                value = read_sensor(sensor_id)
            else:
                value = self._simulate(room)

            if value is not None:
                self._last[room] = (value, time.monotonic())

            stored = self._last.get(room)
            if stored is None:
                out[room] = {"temp": None, "age": None, "ok": False}
            else:
                temp, stamp = stored
                age = time.monotonic() - stamp
                out[room] = {
                    "temp": round(temp, 2),
                    "age": round(age, 1),
                    "ok": age <= config.SENSOR_TIMEOUT_S,
                }
        return out

    def _simulate(self, room: str) -> float:
        """Hrubý model: topení ohřívá, jinak se místnost vrací k 21 °C.

        Slouží jen k tomu, abys mohl odladit termostat dřív, než dorazí čidla.
        """
        now = time.monotonic()
        dt = now - self._sim_t
        if room == list(config.ROOMS)[0]:
            self._sim_t = now

        heating = bool(self._hw and self._hw.heater_on and room == config.HEATER_ROOM)
        if heating:
            self._sim[room] += 0.35 * dt
        else:
            self._sim[room] += (21.0 - self._sim[room]) * 0.02 * dt

        return self._sim[room] + random.uniform(-0.05, 0.05)
