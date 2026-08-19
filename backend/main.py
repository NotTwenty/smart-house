"""FastAPI: REST pro ovládání, WebSocket pro živý stav."""

import asyncio
import logging
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, sensors
from .control import Controller

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
)
log = logging.getLogger("smart-house")

ctrl: Controller | None = None
clients: set[WebSocket] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ctrl
    ctrl = Controller()
    ctrl.start()
    task = asyncio.create_task(_broadcast())
    try:
        yield
    finally:
        task.cancel()
        ctrl.stop()
        log.info("Vypnuto, hardware v bezpečném stavu")


app = FastAPI(title="Chytrý domek", lifespan=lifespan)


async def _broadcast():
    while True:
        await asyncio.sleep(config.LOOP_PERIOD_S)
        if not clients or not ctrl:
            continue
        payload = ctrl.snapshot
        for ws in list(clients):
            try:
                await ws.send_json(payload)
            except Exception:
                clients.discard(ws)


# --- API -------------------------------------------------------------------
class RoomPatch(BaseModel):
    brightness: float | None = None
    target: float | None = None


class ModePatch(BaseModel):
    mode: str


@app.get("/api/state")
def get_state():
    return ctrl.snapshot


@app.post("/api/room/{room_id}")
def patch_room(room_id: str, body: RoomPatch):
    if room_id not in config.ROOMS:
        raise HTTPException(404, "neznámá místnost")
    out = {}
    if body.brightness is not None:
        out["brightness"] = ctrl.set_brightness(room_id, body.brightness)
    if body.target is not None:
        out["target"] = ctrl.set_target(room_id, body.target)
    return out


@app.post("/api/mode")
def patch_mode(body: ModePatch):
    try:
        return {"mode": ctrl.set_mode(body.mode)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/sensors")
def scan_sensors():
    """Pomůcka pro identifikaci čidel. Zahřej jedno v ruce a sleduj, které stoupá."""
    found = sensors.list_sensors()
    return {
        "found": found,
        "readings": {sid: sensors.read_sensor(sid) for sid in found},
        "configured": {r: c["sensor"] for r, c in config.ROOMS.items()},
    }


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        await ws.send_json(ctrl.snapshot)
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)


# Frontend až nakonec, jinak přebije /api
FRONTEND = pathlib.Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
