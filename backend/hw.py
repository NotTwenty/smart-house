"""Hardwarová vrstva. Když GPIO není k dispozici, přepne se do simulace."""

import atexit
import logging
import os

from . import config

log = logging.getLogger(__name__)

MOCK = os.environ.get("SMARTHOUSE_MOCK") == "1"

if not MOCK:
    try:
        from gpiozero import OutputDevice, PWMLED
    except Exception as exc:  # pragma: no cover
        log.warning("gpiozero nedostupné (%s) -> simulace", exc)
        MOCK = True


class Hardware:
    """Tři PWM kanály + jedno relé.

    Relé je aktivní v LOW, proto active_high=False. initial_value=False
    znamená "vypnuto", tedy pin drží HIGH. Relé nesmí sepnout při startu.
    """

    def __init__(self):
        self.mock = MOCK
        self._leds = {}
        self._relay = None
        self.heater_on = False
        self.brightness = {room: 0 for room in config.ROOMS}

        if not self.mock:
            for room, cfg in config.ROOMS.items():
                self._leds[room] = PWMLED(cfg["pin"], frequency=config.PWM_FREQ_HZ)
            self._relay = OutputDevice(
                config.RELAY_PIN, active_high=False, initial_value=False
            )
            log.info("GPIO inicializováno")
        else:
            log.warning("SIMULACE - žádné GPIO se nespíná")

        self.all_off()
        atexit.register(self.all_off)

    # --- LED pásky ---------------------------------------------------------
    def set_brightness(self, room: str, percent: float) -> float:
        percent = max(0.0, min(100.0, float(percent)))
        self.brightness[room] = percent
        if not self.mock:
            self._leds[room].value = percent / 100.0
        return percent

    # --- Topení ------------------------------------------------------------
    def set_heater(self, on: bool) -> bool:
        on = bool(on)
        if on != self.heater_on:
            log.info("Topení -> %s", "ZAP" if on else "VYP")
        self.heater_on = on
        if not self.mock:
            self._relay.value = 1 if on else 0
        return on

    # --- Fail-safe ---------------------------------------------------------
    def all_off(self):
        """Bezpečný stav. Volá se při startu, ukončení i pádu."""
        try:
            self.set_heater(False)
            for room in config.ROOMS:
                self.set_brightness(room, 0)
        except Exception:  # pragma: no cover
            log.exception("all_off selhalo")
