import time
import urllib.request
import urllib.error
import json

def get_json(url):
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read().decode())

def post_json(url, data=None):
    req = urllib.request.Request(url, method="POST")
    if data:
        req.add_header('Content-Type', 'application/json')
        data = json.dumps(data).encode()
    with urllib.request.urlopen(req, data=data) as response:
        if response.read():
            pass

API_URL = "http://127.0.0.1:8000/api"

def reset():
    post_json(f"{API_URL}/reset")
    time.sleep(1)

def get_fleet():
    return get_json(f"{API_URL}/fleet")

def test_spoofed():
    print("\n--- TEST 6-9: SPOOF ATTACK ---")
    reset()
    
    # Send R02 a goal so it starts moving
    post_json(f"{API_URL}/robots/R02/goal", {"x": 20, "y": 2})
    time.sleep(1)
    
    # Trigger spoof
    print("Spoofing R02...")
    post_json(f"{API_URL}/chaos", {"robot_id": "R02", "scenario": "spoof"})
    time.sleep(2)
    
    fleet = get_fleet()
    r02 = next(r for r in fleet if r["robot_id"] == "R02")
    print(f"R02 Status: {r02['status']}, Sec: {r02['security_status']}")
    if r02["status"] != "STOPPED_SPOOF" or r02["security_status"] != "SPOOFED":
        print("FAIL: R02 did not stop or spoof correctly.")
        
    pos = r02["pos"]
    
    # Send another goal
    post_json(f"{API_URL}/robots/R02/goal", {"x": 10, "y": 2})
    time.sleep(2)
    
    fleet2 = get_fleet()
    r02_2 = next(r for r in fleet2 if r["robot_id"] == "R02")
    if r02_2["pos"] != pos:
        print("FAIL: R02 moved despite being spoofed!")
    else:
        print("PASS: R02 ignored goal while spoofed.")
        
def test_charging_occupancy():
    print("\n--- TEST 1-5: CHARGING OCCUPANCY ---")
    reset()
    
    # We want R03 to occupy (1,5). Start pos for R03 is (2,17).
    # Let's send R03 to (1,5).
    post_json(f"{API_URL}/robots/R03/goal", {"x": 1, "y": 5})
    
    # Wait for R03 to arrive at (1,5)
    print("Waiting for R03 to reach (1,5)...")
    for _ in range(15):
        fleet = get_fleet()
        r03 = next(r for r in fleet if r["robot_id"] == "R03")
        if r03["pos"] == [1, 5]:
            break
        time.sleep(1)
        
    print(f"R03 is at {r03['pos']}")
    
    # Now R03 is at (1,5). Send R01 to (1, 6) through (1,5). R01 start is (2,2).
    # Path from (2,2) to (1,6) naturally passes (1,5).
    post_json(f"{API_URL}/robots/R01/goal", {"x": 1, "y": 6})
    
    time.sleep(3)
    fleet = get_fleet()
    r01 = next(r for r in fleet if r["robot_id"] == "R01")
    # check R01 path
    path = r01.get("path", [])
    print(f"R01 Path: {path}")
    if [1, 5] in path:
        print("FAIL: R01 path contains occupied charging station (1,5)!")
    else:
        print("PASS: R01 routed around occupied charging station.")

if __name__ == "__main__":
    import subprocess
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
    
    try:
        test_spoofed()
        test_charging_occupancy()
        print("\nAll tests completed.")
    finally:
        print("Killing processes...")
        observer.kill()
        for a in agents:
            a.kill()
        print("Done.")
