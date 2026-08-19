# Chytrý domek

Řízení tří místností: nezávisle stmívatelné LED pásky, měření teploty
DS18B20 a termostat s Peltierovým článkem. Vše běží na Raspberry Pi 4.

## Nasazení

```bash
cd ~/smart-house
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install fastapi uvicorn
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Otevři `http://dum.local:8000` nebo `http://<IP-Pi>:8000`.

Bez připojených čidel běží **simulace** — v hlavičce se objeví žlutý pruh.
Termostat se dá odladit dřív, než dorazí hardware.

## Identifikace čidel

Po zapojení tří DS18B20:

```bash
curl -s localhost:8000/api/sensors | python3 -m json.tool
```

Chytni jedno čidlo do ruky, zavolej znovu a sleduj, které ID stoupá.
ID zapiš do `backend/config.py` do `ROOMS[...]["sensor"]` a restartuj.

## Systemd

```bash
sudo cp dum.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dum
journalctl -u dum -f
```

V `dum.service` je uživatel `kheil` — pokud máš jiný, oprav `User=`
a obě cesty.

## Zapojení

| BCM | Pin | Funkce |
|---|---|---|
| 18 | 12 | Podkroví — PWM pásek |
| 13 | 33 | Levý pokoj — PWM pásek |
| 12 | 32 | Pravý pokoj — PWM pásek |
| 5 | 29 | Relé → Peltier (aktivní v LOW) |
| 4 | 7 | 1-Wire, tři DS18B20 |

GPIO5 je zvolený schválně: piny 0–8 mají po startu výchozí pull-**up**,
takže relé zůstane rozepnuté po celou dobu bootu. Na GPIO9–27 (pull-down)
by relé sepnulo dřív, než se spustí program.

## Bezpečnostní opatření

Pořadí podmínek v `decide_heater()` je bezpečnostní, neměň ho.

| Ochrana | Chování |
|---|---|
| Výpadek čidla | Čtení starší než 30 s → topení vypnuto |
| Tvrdý cutoff | Nad 45 °C vypnuto, přebíjí i minimální dobu sepnutí |
| Ochrana relé | Minimálně 60 s sepnuto, 30 s rozepnuto |
| Hystereze | ±1 °C kolem cíle, brání kmitání |
| Start a ukončení | `all_off()` při startu, ukončení i pádu procesu |
| Pád smyčky | Výjimka → okamžité vypnutí topení, smyčka pokračuje |
| Rozsah cíle | Zaříznuto na 15–35 °C na straně serveru |

## API

| Metoda | Cesta | Popis |
|---|---|---|
| GET | `/api/state` | Kompletní stav |
| POST | `/api/room/{id}` | `{"brightness": 0-100, "target": 15-35}` |
| POST | `/api/mode` | `{"mode": "auto"\|"off"}` |
| GET | `/api/sensors` | Sken 1-Wire sběrnice |
| WS | `/ws` | Push stavu každé 2 s |

## Struktura

```
backend/
  config.py     piny, místnosti, limity
  hw.py         GPIO vrstva + fail-safe
  sensors.py    čtení 1-Wire + simulace
  control.py    termostat a řídicí vlákno
  main.py       FastAPI
frontend/
  index.html    jedna stránka, bez frameworku
```

Čtení DS18B20 trvá ~750 ms a je blokující, proto běží výhradně
v řídicím vlákně. HTTP requesty čtou jen hotový snapshot.
