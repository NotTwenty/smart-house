"""Termostat a řídicí smyčka.

Rozhodovací logika je v čisté funkci decide_heater() - jde otestovat
bez hardwaru a bez čekání.
"""

import logging
import sqlite3
import threading
import time

from . import config
from .hw import Hardware
from .sensors import SensorHub

log = logging.getLogger(__name__)


def decide_heater(
    temp: float | None,
    age: float | None,
    target: float,
    heating: bool,
    since: float,
    mode: str,
) -> tuple[bool, str]:
    """Vrací (topit, důvod). Pořadí podmínek je bezpečnostní, neměň ho."""
    now = time.monotonic()

    if mode != "auto":
        return False, "vypnuto"

    # 1. Čidlo. Bez platné teploty se netopí, tečka.
    if temp is None or age is None or age > config.SENSOR_TIMEOUT_S:
        return False, "porucha čidla"

    # 2. Tvrdý cutoff. Přebíjí i minimální dobu sepnutí.
    if temp >= config.CUTOFF_C:
        return False, "cutoff 45 °C"

    # 3. Ochrana relé proti klapání.
    if heating and now - since < config.MIN_ON_S:
        return True, "minimální doba sepnutí"
    if not heating and now - since < config.MIN_OFF_S:
        return False, "minimální doba klidu"

    # 4. Hystereze.
    if heating:
        if temp >= target + config.HYSTEREZE_C:
            return False, "dosaženo"
        return True, "topí"
    if temp <= target - config.HYSTEREZE_C:
        return True, "požadavek"
    return False, "v klidu"


class Controller:
    def __init__(self):
        self.hw = Hardware()
        self.sensors = SensorHub(self.hw)
        self.lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self.targets = {room: 22.0 for room in config.ROOMS}
        self.mode = "auto"
        self.reason = "start"
        self._since = time.monotonic()
        self.snapshot: dict = {}

        self._db = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS history ("
            " ts INTEGER, room TEXT, temp REAL, brightness REAL, heater INTEGER)"
        )
        self._db.commit()
        self._last_log = 0.0

    # --- Ovládání zvenčí ---------------------------------------------------
    def set_brightness(self, room: str, percent: float) -> float:
        with self.lock:
            return self.hw.set_brightness(room, percent)

    def set_target(self, room: str, celsius: float) -> float:
        celsius = max(config.TARGET_MIN_C, min(config.TARGET_MAX_C, float(celsius)))
        with self.lock:
            self.targets[room] = celsius
            return celsius

    def set_mode(self, mode: str) -> str:
        if mode not in ("auto", "off"):
            raise ValueError("mode musí být 'auto' nebo 'off'")
        with self.lock:
            self.mode = mode
            return mode

    # --- Smyčka ------------------------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        log.info("Řídicí smyčka běží (simulace: %s)", self.hw.mock)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self.hw.all_off()
        self._db.close()

    def _run(self):
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                log.exception("Chyba ve smyčce - bezpečné vypnutí topení")
                try:
                    self.hw.set_heater(False)
                except Exception:
                    pass
            self._stop.wait(config.LOOP_PERIOD_S)

    def _tick(self):
        readings = self.sensors.read_all()

        with self.lock:
            room = config.HEATER_ROOM
            r = readings[room]
            want, reason = decide_heater(
                temp=r["temp"],
                age=r["age"],
                target=self.targets[room],
                heating=self.hw.heater_on,
                since=self._since,
                mode=self.mode,
            )
            if want != self.hw.heater_on:
                self._since = time.monotonic()
                self.hw.set_heater(want)
            self.reason = reason

            self.snapshot = {
                "ts": time.time(),
                "mode": self.mode,
                "heater": {
                    "room": room,
                    "on": self.hw.heater_on,
                    "reason": reason,
                    "cutoff_c": config.CUTOFF_C,
                },
                "simulace": self.hw.mock,
                "rooms": {
                    name: {
                        "name": cfg["name"],
                        "temp": readings[name]["temp"],
                        "sensor_ok": readings[name]["ok"],
                        "brightness": self.hw.brightness[name],
                        "target": self.targets[name],
                        "has_heater": name == room,
                    }
                    for name, cfg in config.ROOMS.items()
                },
            }

        self._maybe_log(readings)

    def _maybe_log(self, readings):
        now = time.time()
        if now - self._last_log < 30:
            return
        self._last_log = now
        rows = [
            (
                int(now),
                room,
                readings[room]["temp"],
                self.hw.brightness[room],
                int(self.hw.heater_on and room == config.HEATER_ROOM),
            )
            for room in config.ROOMS
        ]
        self._db.executemany("INSERT INTO history VALUES (?,?,?,?,?)", rows)
        self._db.commit()
