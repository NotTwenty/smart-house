"""Konfigurace. Tady se mění všechno, co se mění často."""

# --- Místnosti -------------------------------------------------------------
# pin  = BCM číslo pro PWM kanál LED pásku
# sensor = ID DS18B20 (např. "28-3c01d607xxxx"). Doplníš po identifikaci čidel.
#          Dokud je None, běží simulace.
ROOMS = {
    "attic": {"name": "Podkroví", "pin": 18, "sensor": None},
    "left": {"name": "Levý pokoj", "pin": 13, "sensor": None},
    "right": {"name": "Pravý pokoj", "pin": 12, "sensor": None},
}

# Ve které místnosti je Peltier
HEATER_ROOM = "right"

# --- Piny ------------------------------------------------------------------
RELAY_PIN = 6          # BCM5 = fyzický pin 29. Výchozí pull-UP -> relé po bootu vypnuté.
PWM_FREQ_HZ = 1000

# --- Bezpečnost a regulace -------------------------------------------------
CUTOFF_C = 45.0        # nad tímhle vypni topení bez ohledu na cokoliv
HYSTEREZE_C = 1.0      # zapni pod (cíl - hyst), vypni nad (cíl + hyst)
MIN_ON_S = 60          # relé nesmí klapat rychleji
MIN_OFF_S = 30
SENSOR_TIMEOUT_S = 30  # čidlo mlčí déle -> topení vypnout
TARGET_MIN_C = 15.0
TARGET_MAX_C = 35.0

LOOP_PERIOD_S = 2.0

DB_PATH = "smart-house.db"
