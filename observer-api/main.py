import asyncio
import json
import threading
import time
import socket
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import paho.mqtt.client as mqtt
import uvicorn
import os

app = FastAPI()

# Mount static files for the dashboard
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# ── State Aggregation ─────────────────────────────────────────────────
fleet_state = {}
logs = []
ledger = []
system_status = {
    "mqtt": "OFFLINE",
    "udp": "ONLINE",
    "observer": "ONLINE",
}

ROBOT_GOSSIP_PORTS = {"R01": 5001, "R02": 5002, "R03": 5003, "R04": 5004}
VALID_ROBOT_IDS = {"R01", "R02", "R03", "R04"}

# ── UDP Send Helper ──────────────────────────────────────────────────
def udp_send(payload: dict, ports: list = None):
    """Send a JSON payload via UDP to robot gossip ports."""
    if ports is None:
        ports = list(ROBOT_GOSSIP_PORTS.values())
    raw = json.dumps(payload).encode('utf-8')
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for port in ports:
        try:
            sock.sendto(raw, ('127.0.0.1', port))
        except Exception:
            pass
    sock.close()


def add_log(event: str, desc: str):
    logs.insert(0, {"event": event, "desc": desc, "ts": time.time()})
    if len(logs) > 100:
        logs.pop()


def add_ledger(entry: dict):
    ledger.insert(0, entry)
    if len(ledger) > 100:
        ledger.pop()


# ── MQTT Setup ────────────────────────────────────────────────────────
mqtt_client = mqtt.Client(client_id="observer-api")

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        system_status["mqtt"] = "ONLINE"
        client.subscribe("fleet/#")
    else:
        system_status["mqtt"] = "OFFLINE"

def on_disconnect(client, userdata, rc):
    system_status["mqtt"] = "OFFLINE"

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        topic = msg.topic

        if topic == "fleet/telemetry":
            rid = payload.get("robot_id")
            if rid:
                fleet_state[rid] = payload

        elif topic == "fleet/security/alerts":
            event = payload.get("event")
            rid = payload.get("robot_id")
            reason = payload.get("reason")
            add_log(event, f"{rid}: {reason}")

        elif topic == "fleet/ledger/append":
            add_ledger(payload)
            add_log(payload.get("event", "LEDGER"), payload.get("reason", ""))

    except Exception as e:
        print(f"MQTT Error: {e}")

mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message

def mqtt_loop():
    try:
        mqtt_client.connect("127.0.0.1", 1883, 60)
        mqtt_client.subscribe("fleet/#")
        mqtt_client.loop_forever()
    except Exception as e:
        system_status["mqtt"] = "OFFLINE"
        print(f"[Observer] MQTT unavailable: {e}")
        print("[Observer] Continuing with UDP fallback only.")

threading.Thread(target=mqtt_loop, daemon=True).start()


# ── UDP Fallback Listener (Port 5000) ─────────────────────────────────
def udp_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', 5000))
    system_status["udp"] = "ONLINE"
    while True:
        try:
            data, _ = sock.recvfrom(8192)
            payload = json.loads(data.decode('utf-8'))

            rid = payload.get("robot_id")

            # Telemetry (has "path" key)
            if "path" in payload and "pos" in payload:
                fleet_state[rid] = payload

            # Ledger / Event (has "event" + "hash")
            elif "event" in payload and "hash" in payload:
                add_ledger(payload)
                add_log(payload.get("event", "LEDGER"), payload.get("reason", ""))

            # Security alert
            elif "event" in payload and "anomaly_score" in payload:
                add_log(payload.get("event"), f"{rid}: {payload.get('reason')}")

        except Exception:
            pass

threading.Thread(target=udp_loop, daemon=True).start()


# ── Pydantic Models ───────────────────────────────────────────────────
class GoalRequest(BaseModel):
    x: int = Field(..., ge=0, lt=30)
    y: int = Field(..., ge=0, lt=20)

class ChaosRequest(BaseModel):
    scenario: str
    robot_id: str = "R02"

class ModeRequest(BaseModel):
    mode: str  # "auto" or "manual"


# ── API Endpoints ─────────────────────────────────────────────────────

@app.get("/")
def get_dashboard():
    with open(os.path.join(static_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()
    return HTMLResponse(content=content, media_type="text/html; charset=utf-8")


@app.get("/api/fleet")
def get_fleet():
    return list(fleet_state.values())


@app.get("/api/robots/{robot_id}")
def get_robot(robot_id: str):
    if robot_id not in VALID_ROBOT_IDS:
        return JSONResponse(status_code=404, content={"error": f"Unknown robot: {robot_id}"})
    if robot_id in fleet_state:
        return fleet_state[robot_id]
    return JSONResponse(status_code=404, content={"error": f"{robot_id} not yet reporting"})


@app.post("/api/robots/{robot_id}/goal")
async def set_robot_goal(robot_id: str, goal: GoalRequest):
    if robot_id not in VALID_ROBOT_IDS:
        return JSONResponse(status_code=404, content={"error": f"Unknown robot: {robot_id}"})

    command = {
        "command": "SET_GOAL",
        "robot_id": robot_id,
        "x": goal.x,
        "y": goal.y
    }

    # Try MQTT first, fall back to UDP
    sent = False
    try:
        if mqtt_client.is_connected():
            mqtt_client.publish("fleet/command", json.dumps(command))
            sent = True
    except Exception:
        pass

    if not sent:
        port = ROBOT_GOSSIP_PORTS.get(robot_id)
        if port:
            udp_send(command, [port])

    add_log("TASK_ASSIGNED", f"{robot_id} -> ({goal.x},{goal.y})")
    return {"status": "goal_sent", "robot_id": robot_id, "goal": [goal.x, goal.y]}


@app.post("/api/mode")
async def set_fleet_mode(req: ModeRequest):
    for rid, port in ROBOT_GOSSIP_PORTS.items():
        command = {
            "command": "SET_MODE",
            "robot_id": rid,
            "mode": req.mode
        }
        try:
            if mqtt_client.is_connected():
                mqtt_client.publish("fleet/command", json.dumps(command))
            else:
                udp_send(command, [port])
        except Exception:
            udp_send(command, [port])

    add_log("MODE_CHANGE", f"Fleet mode -> {req.mode}")
    return {"status": "mode_set", "mode": req.mode}


@app.post("/api/chaos")
async def inject_chaos(request: Request):
    data = await request.json()
    scenario = data.get("scenario")
    robot_id = data.get("robot_id", "R02")

    action_map = {
        "deadlock": "DEADLOCK",
        "obstacle": "OBSTACLE",
        "spoof": "SPOOF",
        "kill_broker": "KILL"
    }
    action = action_map.get(scenario, scenario)

    payload = {
        "action": action,
        "robot_id": robot_id
    }

    # Try MQTT, fall back to UDP
    sent = False
    try:
        if mqtt_client.is_connected():
            mqtt_client.publish("fleet/chaos", json.dumps(payload))
            sent = True
    except Exception:
        pass

    if not sent:
        udp_send(payload)

    add_log(f"CHAOS_{action}", f"Injected {action} targeting {robot_id}")
    return {"status": "chaos_injected", "action": action, "robot_id": robot_id}


@app.post("/api/reset")
async def reset_warehouse():
    payload = {
        "command": "RESET",
        "action": "RESET",  # Handle both formats
    }
    
    # Reset internal observer state
    fleet_state.clear()
    logs.clear()
    ledger.clear()
    
    # Broadcast to all agents
    try:
        if mqtt_client.is_connected():
            mqtt_client.publish("fleet/chaos", json.dumps(payload))
            mqtt_client.publish("fleet/command", json.dumps(payload))
    except Exception:
        pass

    for port in ROBOT_GOSSIP_PORTS.values():
        udp_send(payload, [port])

    add_log("SYSTEM_RESET", "Warehouse simulation reset to initial state")
    return {"status": "reset_complete"}


@app.get("/api/events")
def get_events():
    return logs[:30]


@app.get("/api/ledger")
def get_ledger():
    return ledger[:20]


@app.get("/api/system-status")
def get_system_status():
    return system_status


@app.get("/api/warehouse")
def get_warehouse():
    """Return warehouse layout for the dashboard grid."""
    config_path = os.path.join(os.path.dirname(__file__), "..", "edge-agent", "config", "warehouse_map.json")
    with open(config_path, "r") as f:
        return json.load(f)


# ── WebSocket ─────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            state_pkg = {
                "fleet": list(fleet_state.values()),
                "logs": logs[:20],
                "ledger": ledger[:15],
                "system": system_status,
            }
            await websocket.send_json(state_pkg)
            await asyncio.sleep(0.1)  # 10Hz is plenty for a dashboard
    except Exception:
        pass


if __name__ == "__main__":
    print("[Observer] Starting Mission Control on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
