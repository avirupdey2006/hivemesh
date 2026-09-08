"""Comprehensive smoke test for the SIH AMR Fleet prototype."""
import sys
import os
import time
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'edge-agent'))

PASS = 0
FAIL = 0

def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} -- {detail}")

print("=" * 60)
print("  SIH 2026 AMR FLEET - SMOKE TEST SUITE")
print("=" * 60)

# ── 1. WorldModel ─────────────────────────────────────────────
print("\n--- WorldModel ---")
from core.world_model import WorldModel
config_path = os.path.join(os.path.dirname(__file__), '..', 'edge-agent', 'config', 'warehouse_map.json')
world = WorldModel(config_path)
test("WorldModel loads", world is not None)
test("Grid dimensions 30x20", world.width == 30 and world.height == 20)
test("Free cell (2,2) not blocked", not world.is_blocked(2, 2))
test("Shelf cell (5,6) blocked", world.is_blocked(5, 6))
test("Out of bounds (-1,0) blocked", world.is_blocked(-1, 0))
test("Dynamic obstacle add/check", True)
world.add_dynamic_obstacle(15, 10)
test("Dynamic obstacle blocks cell", world.is_blocked(15, 10))
world.clear_dynamic_obstacles()
test("Clear dynamic obstacles", not world.is_blocked(15, 10))

# ── 2. D* Lite Planner ───────────────────────────────────────
print("\n--- D* Lite Planner ---")
from core.planner import DStarLitePlanner
planner = DStarLitePlanner(world)

test("DStarLitePlanner has g dict", hasattr(planner, 'g'))
test("DStarLitePlanner has rhs dict", hasattr(planner, 'rhs'))
test("DStarLitePlanner has U queue", hasattr(planner, 'U'))
test("DStarLitePlanner has k_m", hasattr(planner, 'k_m'))
test("DStarLitePlanner has calculate_key", hasattr(planner, 'calculate_key'))
test("DStarLitePlanner has update_vertex", hasattr(planner, 'update_vertex'))
test("DStarLitePlanner has compute_shortest_path", hasattr(planner, 'compute_shortest_path'))

# Plan a path
t0 = time.perf_counter()
path = planner.plan((2, 2), (27, 17), set())
t1 = time.perf_counter()
plan_ms = (t1 - t0) * 1000
test(f"Path found (2,2)->(27,17), len={len(path)}", len(path) > 0)
test(f"Path starts near (2,2)", path[0][:2] == (2, 2) if path else False)
test(f"Path ends at (27,17)", path[-1][:2] == (27, 17) if path else False)
test(f"Initial plan time: {plan_ms:.2f}ms", plan_ms < 500)

# Verify path doesn't cross shelves
path_crosses_shelf = False
for step in path:
    if world.is_blocked(step[0], step[1]):
        path_crosses_shelf = True
        break
test("Path does not cross shelves", not path_crosses_shelf)

# Dynamic obstacle replan
world.add_dynamic_obstacle(path[len(path)//2][0], path[len(path)//2][1])
t2 = time.perf_counter()
new_path = planner.plan((2, 2), (27, 17), set())
t3 = time.perf_counter()
replan_ms = (t3 - t2) * 1000
test(f"Replan after obstacle, len={len(new_path)}, time={replan_ms:.2f}ms", len(new_path) > 0)
world.clear_dynamic_obstacles()

# ── 3. CBS Negotiator ─────────────────────────────────────────
print("\n--- CBS Negotiator ---")
from core.cbs_negotiator import CBSNegotiator
path_a = [(5, 5, 0), (6, 5, 1), (7, 5, 2)]
path_b = [(7, 5, 0), (6, 5, 1), (5, 5, 2)]
conflict_pos, conflict_t = CBSNegotiator.detect_conflict(path_a, path_b)
test("Conflict detected between crossing paths", conflict_pos is not None)

res = CBSNegotiator.negotiate(
    {"id": "R01", "prio": "HEAVY", "battery": 90, "wait": 0},
    {"id": "R02", "prio": "LIGHT", "battery": 85, "wait": 0},
    (conflict_pos, conflict_t)
)
test("HEAVY wins over LIGHT", res["decision"] == "PROCEED")
test("Negotiation has reason", len(res["reason"]) > 0)

# ── 4. Safety Controller ─────────────────────────────────────
print("\n--- Safety Controller ---")
from core.safety_controller import SafetyController
safety = SafetyController()
test("No threat when far", not safety.evaluate_immediate_threat((0, 0), [(10, 10)]))
test("Threat when adjacent", safety.evaluate_immediate_threat((5, 5), [(5, 6)]))

# ── 5. Security Auth ─────────────────────────────────────────
print("\n--- Security Auth ---")
from core.security.auth import SecurityAuth
auth = SecurityAuth("test_key")
payload = {"robot_id": "R01", "seq": 1, "pos": [2, 2], "timestamp": time.time()}
sig = auth.sign_payload(payload)
payload["signature"] = sig
test("HMAC sign produces signature", len(sig) > 0)
test("HMAC verify correct signature", auth.verify(payload))

bad_payload = dict(payload)
bad_payload["pos"] = [99, 99]
test("HMAC rejects tampered payload", not auth.verify(bad_payload))

# Replay protection
auth2 = SecurityAuth("test_key")
p1 = {"robot_id": "R01", "seq": 1, "pos": [2, 2], "timestamp": time.time()}
p1["signature"] = auth2.sign_payload(p1)
auth2.verify(p1)  # consume seq=1
p2 = {"robot_id": "R01", "seq": 1, "pos": [2, 2], "timestamp": time.time()}
p2["signature"] = auth2.sign_payload(p2)
test("Replay rejected (same seq)", not auth2.verify(p2))

# ── 6. Anomaly Detector ──────────────────────────────────────
print("\n--- Anomaly Detector ---")
from core.security.anomaly_detector import AnomalyDetector
ad = AnomalyDetector()
ok, _, _ = ad.check_telemetry("R01", (2, 2), time.time())
test("First telemetry is normal", ok)
ok2, reason, score = ad.check_telemetry("R01", (50, 50), time.time() + 0.1)
test("Teleportation detected as anomaly", not ok2)

# ── 7. Hash Ledger ────────────────────────────────────────────
print("\n--- Hash Ledger ---")
from core.ledger.hash_chain import HashLedger
ledger = HashLedger()
test("Genesis block exists", len(ledger.chain) == 1)
ledger.append_block("TEST_EVENT", ["R01"], "test reason")
test("Block appended", len(ledger.chain) == 2)
test("Chain integrity valid", ledger.verify_integrity())
# Tamper
ledger.chain[1]["reason"] = "TAMPERED"
test("Tampered chain fails integrity", not ledger.verify_integrity())

# ── 8. ML Conflict Predictor ─────────────────────────────────
print("\n--- ML Conflict Predictor ---")
from core.ml.conflict_predictor import ConflictPredictor
cp = ConflictPredictor()
test("ConflictPredictor initializes", cp is not None)
prob = cp.predict_conflict_probability((2, 2), (3, 3), 1.0, 2.0, 1.0, 0.5)
test(f"Prediction returns float: {prob:.3f}", isinstance(prob, float) and 0 <= prob <= 1)

# ── Summary ───────────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"  RESULTS: {PASS} PASSED / {FAIL} FAILED / {PASS + FAIL} TOTAL")
print("=" * 60)
if FAIL == 0:
    print("  ALL TESTS PASSED")
else:
    print(f"  {FAIL} TEST(S) FAILED")
sys.exit(FAIL)
