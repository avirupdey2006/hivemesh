import subprocess
import time
import urllib.request
import urllib.error
import json
import socket
import os

python_exe = r"venv\Scripts\python.exe"

print("Starting Observer...")
observer = subprocess.Popen([python_exe, "observer-api/main.py"])
time.sleep(2)

print("Starting Agents...")
agents = []
for i in range(1, 5):
    p = subprocess.Popen([python_exe, "edge-agent/main.py", f"R0{i}"])
    agents.append(p)

time.sleep(5)

def get_json(url):
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read().decode())

def post_json(url, data=None):
    req = urllib.request.Request(url, method="POST")
    if data:
        req.add_header('Content-Type', 'application/json')
        data = json.dumps(data).encode()
    with urllib.request.urlopen(req, data=data) as response:
        return json.loads(response.read().decode())

print("Testing initial state...")
try:
    fleet = get_json("http://127.0.0.1:8000/api/fleet")
    print("Initial fleet:", [r['robot_id'] + " at " + str(r['pos']) for r in fleet])
except Exception as e:
    print(e)

print("Moving R01 manually...")
post_json("http://127.0.0.1:8000/api/robots/R01/goal", {"x": 5, "y": 5})

print("Adding dynamic obstacle to R02...")
post_json("http://127.0.0.1:8000/api/chaos", {"scenario": "obstacle", "robot_id": "R02"})

print("Spoofing R03...")
post_json("http://127.0.0.1:8000/api/chaos", {"scenario": "spoof", "robot_id": "R03"})

time.sleep(3)

print("Pre-Reset fleet state:")
fleet = get_json("http://127.0.0.1:8000/api/fleet")
for r in fleet:
    print(f"{r['robot_id']} - Pos: {r['pos']}, Mode: {r['mode']}, Sec: {r.get('security_status')}, Obs: {r.get('dynamic_obstacles')}")

print("Triggering RESET...")
post_json("http://127.0.0.1:8000/api/reset")

time.sleep(3)

print("Post-Reset fleet state:")
fleet = get_json("http://127.0.0.1:8000/api/fleet")
for r in fleet:
    print(f"{r['robot_id']} - Pos: {r['pos']}, Mode: {r['mode']}, Sec: {r.get('security_status')}, Obs: {r.get('dynamic_obstacles')}")

print("Killing processes...")
observer.kill()
for a in agents:
    a.kill()
print("Done.")
