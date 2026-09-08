import sys
import os
import time
import yaml
import json
from core.world_model import WorldModel
from core.planner import DStarLitePlanner
from core.cbs_negotiator import CBSNegotiator
from core.safety_controller import SafetyController
from core.security.auth import SecurityAuth
from core.security.anomaly_detector import AnomalyDetector
from core.ledger.hash_chain import HashLedger
from core.ml.conflict_predictor import ConflictPredictor
from core.comms.gossip_udp import GossipNode
from core.comms.mqtt_client import RobustMQTTClient

class EdgeAgent:
    def __init__(self, robot_id: str, config_dir: str = None):
        if config_dir is None:
            config_dir = os.path.join(os.path.dirname(__file__), "config")

        self.robot_id = robot_id
        with open(os.path.join(config_dir, "robot_config.yaml"), "r") as f:
            cfg = yaml.safe_load(f)

        self.robot_cfg = next(r for r in cfg["robots"] if r["id"] == robot_id)
        all_ports = [r["gossip_port"] for r in cfg["robots"]]
        all_ports.append(5000)  # Observer API UDP fallback

        self.auth = SecurityAuth(cfg["fleet_key"])
        self.world = WorldModel(os.path.join(config_dir, "warehouse_map.json"))
        self.planner = DStarLitePlanner(self.world)
        self.safety = SafetyController()
        self.ledger = HashLedger()
        self.anomaly_detector = AnomalyDetector()
        self.ml_predictor = ConflictPredictor()

        self.pos = tuple(self.robot_cfg["start_pos"])
        self.battery = float(self.robot_cfg["battery"])
        self.priority = self.robot_cfg["priority_class"]
        self.seq = 0
        self.status = "IDLE"
        self.current_path = []
        self.wait_time = 0.0
        self.goal = None
        self.last_plan_ms = 0.0

        # Mode: "auto" or "manual"
        self.mode = "auto"

        # Auto-demo deterministic missions
        self.auto_missions = {
            "R01": ((5, 2), (5, 18)),
            "R02": ((12, 2), (12, 18)),
            "R03": ((20, 2), (20, 18)),
            "R04": ((27, 2), (27, 18))
        }
        self.mission_state = "IDLE"  # IDLE, TO_PICKUP, TO_DROPOFF

        self.known_intents = {}
        self.other_positions = {}
        self.comm_degraded = False

        # Dual-stack Comms
        self.gossip = GossipNode(self.robot_id, self.robot_cfg["gossip_port"], all_ports)
        self.mqtt = RobustMQTTClient(self.robot_id)
        self.mqtt.subscribe("fleet/intent", self._on_mqtt_intent)
        self.mqtt.subscribe("fleet/telemetry", self._on_mqtt_telemetry)
        self.mqtt.subscribe("fleet/chaos", self._on_chaos)
        self.mqtt.subscribe("fleet/command", self._on_command)
        self.mqtt.start()

    # ── Command Handling ──────────────────────────────────────────────

    def _do_reset(self):
        import yaml
        import os
        config_path = os.path.join(os.path.dirname(__file__), "config", "robot_config.yaml")
        with open(config_path, "r") as f:
            conf = yaml.safe_load(f)
        for r in conf["robots"]:
            if r["id"] == self.robot_id:
                self.pos = tuple(r["start_pos"])
                self.battery = r["battery"]
                self.priority = r["priority_class"]
                break
        self.status = "IDLE"
        self.security_status = "NORMAL"
        
        # Determine mode-specific reset state (preserve current mode)
        if self.mode == "auto":
            self.mission_state = "IDLE"
        else:
            self.mission_state = "MANUAL"
            
        self.goal = None
        self.current_path = []
        self.known_intents.clear()
        self.other_positions.clear()
        self.world.clear_dynamic_obstacles()
        
        # Reinitialize planner
        from core.planner import DStarLitePlanner
        self.planner = DStarLitePlanner(self.world)
        
        print(f"[RESET] {self.robot_id} reset to initial configuration.")

    def _on_command(self, payload):
        """Handle goal/mode commands from Observer API."""
        cmd = payload.get("command")
        if cmd == "RESET":
            self._do_reset()
            return
            
        target = payload.get("robot_id")
        if target != self.robot_id:
            return
            
        if getattr(self, "security_status", "NORMAL") == "SPOOFED":
            print(f"[{self.robot_id}] Ignoring command {cmd} while SPOOFED")
            return
            
        if cmd == "SET_GOAL":
            x = payload.get("x")
            y = payload.get("y")
            if x is not None and y is not None:
                self.mode = "manual"
                self.mission_state = "MANUAL"
                self.goal = (int(x), int(y))
                self.assign_goal(self.goal)
                block = self.ledger.append_block(
                    "TASK_ASSIGNED", [self.robot_id],
                    f"{self.robot_id} assigned manual goal ({x},{y})"
                )
                self.gossip.broadcast(block)
                print(f"[{self.robot_id}] Received manual goal: ({x},{y})")
        elif cmd == "SET_MODE":
            new_mode = payload.get("mode", "auto")
            self.mode = new_mode
            if new_mode == "auto":
                self.mission_state = "IDLE"
                self.goal = None
                self.current_path = []
                print(f"[{self.robot_id}] Switched to AUTO mode")
            else:
                self.mission_state = "MANUAL"
                self.goal = None
                self.current_path = []
                print(f"[{self.robot_id}] Switched to MANUAL mode")

    def _on_chaos(self, payload):
        target = payload.get("robot_id")
        action = payload.get("action")

        if action == "RESET":
            self._do_reset()
            return

        if action == "SHARED_OBSTACLE":
            obs_x = payload.get("x")
            obs_y = payload.get("y")
            if obs_x is not None and obs_y is not None:
                if not self.world.is_blocked(obs_x, obs_y):
                    self.world.add_dynamic_obstacle(obs_x, obs_y)
                    print(f"[D* LITE] {self.robot_id} shared obstacle at ({obs_x},{obs_y}). Replanning...")
                    if self.goal:
                        t0 = time.perf_counter()
                        self.planner.init_search(self.pos, self.goal)
                        self.current_path = self.planner.plan(self.pos, self.goal, self._get_reservations())
                        self.last_plan_ms = (time.perf_counter() - t0) * 1000
            return

        if action == "DEADLOCK":
            # Force this robot to target the same cell as another robot
            conflict_target = (15, 10)
            self.mode = "manual"
            self.mission_state = "MANUAL"
            self.goal = conflict_target
            self.assign_goal(conflict_target)
            block = self.ledger.append_block(
                "CHAOS_DEADLOCK", [self.robot_id],
                f"Deadlock scenario: {self.robot_id} forced toward {conflict_target}"
            )
            self.gossip.broadcast(block)
            print(f"[CHAOS] {self.robot_id} forced toward deadlock cell {conflict_target}")
            return

        if target != self.robot_id:
            return

        if action == "KILL":
            self.status = "OFFLINE"
            block = self.ledger.append_block(
                "CHAOS_KILL", [self.robot_id],
                f"{self.robot_id} terminated by chaos injection"
            )
            self.gossip.broadcast(block)
            print(f"[CHAOS] {self.robot_id} KILLED")

        elif action == "SPOOF":
            old_pos = self.pos
            self.pos = (self.pos[0] + 12, self.pos[1] + 12)
            self.security_status = "SPOOFED"
            self.status = "ISOLATED"
            block = self.ledger.append_block(
                "CHAOS_SPOOF", [self.robot_id],
                f"{self.robot_id} position spoofed from {old_pos} to {self.pos}"
            )
            self.gossip.broadcast(block)
            print(f"[CHAOS] {self.robot_id} SPOOFED {old_pos} -> {self.pos}")

        elif action == "OBSTACLE":
            # Find a cell ahead on the current path to place the obstacle
            if len(self.current_path) >= 3:
                obs_cell = self.current_path[2][:2]
            elif len(self.current_path) >= 1:
                obs_cell = self.current_path[0][:2]
            else:
                obs_cell = (self.pos[0] + 2, self.pos[1])
            obs_x, obs_y = int(obs_cell[0]), int(obs_cell[1])

            # Broadcast the shared obstacle to all other robots
            shared_payload = {"action": "SHARED_OBSTACLE", "x": obs_x, "y": obs_y}
            self.gossip.broadcast(shared_payload)
            self.mqtt.publish("fleet/chaos", shared_payload)

            # Process it locally
            self._on_chaos(shared_payload)

            block = self.ledger.append_block(
                "DYNAMIC_OBSTACLE", [self.robot_id],
                f"Obstacle at ({obs_x},{obs_y}), generated by {self.robot_id}"
            )
            self.gossip.broadcast(block)

    def _on_mqtt_intent(self, data):
        self._process_intent(data)

    def _on_mqtt_telemetry(self, data):
        if not self.auth.verify(data):
            return
        rid = data.get("robot_id")
        if rid != self.robot_id:
            pos = tuple(data["pos"])
            ts = data.get("timestamp", time.time())
            is_normal, reason, score = self.anomaly_detector.check_telemetry(rid, pos, ts)
            if not is_normal:
                alert = {
                    "event": "SPOOF_SUSPECTED",
                    "robot_id": rid,
                    "reason": reason,
                    "anomaly_score": score,
                    "timestamp": time.time()
                }
                self.mqtt.publish("fleet/security/alerts", alert)
                self.gossip.broadcast(alert)
                block = self.ledger.append_block(
                    "SECURITY_ALERT", [rid],
                    f"Spoof suspected on {rid}: {reason}"
                )
                self.gossip.broadcast(block)
                print(f"[SECURITY] Anomaly detected for {rid}: {reason}")
                return
            self.other_positions[rid] = pos

    def _process_intent(self, data):
        if not self.auth.verify(data):
            return
        rid = data.get("robot_id")
        if rid != self.robot_id:
            self.known_intents[rid] = data

    def _get_reservations(self):
        reservations = set()
        for rid, item in self.known_intents.items():
            for pt in item.get("reserved_path", []):
                reservations.add(tuple(pt))
        return reservations

    # ── Planning ──────────────────────────────────────────────────────

    def assign_goal(self, goal: tuple):
        reservations = self._get_reservations()
        t0 = time.perf_counter()
        self.current_path = self.planner.plan(self.pos, goal, reservations)
        t1 = time.perf_counter()
        self.last_plan_ms = (t1 - t0) * 1000
        self.goal = goal
        self.status = "MOVING"
        print(f"[D* LITE] {self.robot_id} planning {self.pos} -> {goal}")
        print(f"[D* LITE] {self.robot_id} path_len={len(self.current_path)} time={self.last_plan_ms:.2f}ms")

    # ── Main Tick ─────────────────────────────────────────────────────

    def tick(self):
        if self.status == "OFFLINE":
            self.broadcast_telemetry()
            return

        self.seq += 1

        # ── Process UDP Gossip Messages ──
        gossip_msgs = self.gossip.get_latest()
        for msg in gossip_msgs:
            # Handle commands received via UDP
            if "command" in msg:
                self._on_command(msg)
                continue
            # Handle chaos received via UDP
            if "action" in msg and "command" not in msg:
                self._on_chaos(msg)
                continue
            # Handle telemetry from other robots
            rid = msg.get("robot_id")
            if rid and rid != self.robot_id and "pos" in msg:
                self.other_positions[rid] = tuple(msg["pos"])

        # ── Check network degradation ──
        self.comm_degraded = not self.mqtt.is_connected

        # ── Spoofed Safety Stop ──
        if getattr(self, "security_status", "NORMAL") == "SPOOFED":
            self.status = "STOPPED_SPOOF"
            self.broadcast_telemetry()
            return

        # ── Dynamic Charging Station & Robot Occupancy ──
        charging_cells = {(c['x'], c['y']) for c in self.world.data.get('charging_stations', [])}
        occupied_by_others = set()
        for rid, pos in self.other_positions.items():
            if pos in charging_cells:
                occupied_by_others.add(pos)
        self.world.charging_obstacles = occupied_by_others
        self.world.robot_obstacles = set(self.other_positions.values())

        # ── Safety Check (Non-negotiable E-Stop) ──
        neighbor_pts = list(self.other_positions.values())
        if self.safety.evaluate_immediate_threat(self.pos, neighbor_pts):
            self.status = "STOPPED_SAFETY_OVERRIDE"
            block = self.ledger.append_block(
                "SAFETY_OVERRIDE", [self.robot_id],
                f"{self.robot_id} emergency stop at {self.pos}"
            )
            self.gossip.broadcast(block)
            self.broadcast_telemetry()
            return

        # ── Conflict Detection & Negotiation ──
        for rid, item in list(self.known_intents.items()):
            o_path = item.get("reserved_path", [])
            conflict_pos, conflict_t = CBSNegotiator.detect_conflict(self.current_path, o_path)
            if conflict_pos:
                try:
                    prob = self.ml_predictor.predict_conflict_probability(
                        self.pos, tuple(item["current_pos"]), 1.0, 2.0, 1.0, 0.5
                    )
                except Exception:
                    prob = 0.5

                if prob > 0.4:
                    res = CBSNegotiator.negotiate(
                        {"id": self.robot_id, "prio": self.priority,
                         "battery": self.battery, "wait": self.wait_time},
                        {"id": rid, "prio": item["priority_class"],
                         "battery": item["battery"], "wait": 0},
                        (conflict_pos, conflict_t)
                    )
                    block = self.ledger.append_block(
                        "CBS_NEGOTIATION", [self.robot_id, rid], res["reason"]
                    )
                    self.mqtt.publish("fleet/ledger/append", block)
                    self.gossip.broadcast(block)
                    print(f"[CBS] {res['reason']}")

                    if res["decision"] == "YIELD":
                        self.status = "YIELDING"
                        self.wait_time += 1.0
                        self.current_path = [(self.pos[0], self.pos[1], 0)] + self.current_path
                        self.broadcast_telemetry()
                        return  # Skip movement this tick

        # ── Auto Demo Mission State Machine ──
        if self.mode == "auto":
            pickup, dropoff = self.auto_missions.get(self.robot_id, (None, None))
            if pickup:
                if self.mission_state == "IDLE":
                    self.mission_state = "TO_PICKUP"
                    self.assign_goal(pickup)
                elif self.mission_state == "TO_PICKUP" and self.pos == pickup:
                    print(f"[{self.robot_id}] PICKUP completed at {pickup}")
                    block = self.ledger.append_block(
                        "GOAL_REACHED", [self.robot_id],
                        f"{self.robot_id} reached pickup {pickup}"
                    )
                    self.gossip.broadcast(block)
                    self.mission_state = "TO_DROPOFF"
                    self.assign_goal(dropoff)
                elif self.mission_state == "TO_DROPOFF" and self.pos == dropoff:
                    print(f"[{self.robot_id}] DROPOFF completed at {dropoff}")
                    block = self.ledger.append_block(
                        "GOAL_REACHED", [self.robot_id],
                        f"{self.robot_id} reached dropoff {dropoff}"
                    )
                    self.gossip.broadcast(block)
                    self.mission_state = "IDLE"

        # ── Manual Mode: check goal reached ──
        elif self.mode == "manual" and self.goal:
            if self.pos == self.goal:
                print(f"[{self.robot_id}] GOAL_REACHED {self.goal}")
                block = self.ledger.append_block(
                    "GOAL_REACHED", [self.robot_id],
                    f"{self.robot_id} reached goal {self.goal}"
                )
                self.gossip.broadcast(block)
                self.goal = None
                self.current_path = []
                self.status = "IDLE"
                self.broadcast_telemetry()
                return

        # ── Path Execution ──
        # Pop current position if it matches where we already are
        while len(self.current_path) > 0 and (self.current_path[0][0], self.current_path[0][1]) == self.pos:
            self.current_path.pop(0)

        # Safety Check: Is next waypoint an occupied charging station or occupied by another robot?
        if len(self.current_path) > 0:
            next_step = (self.current_path[0][0], self.current_path[0][1])
            is_charging = hasattr(self.world, 'charging_obstacles') and next_step in self.world.charging_obstacles
            is_robot = hasattr(self.world, 'robot_obstacles') and next_step in self.world.robot_obstacles
            
            if is_charging or is_robot:
                obstacle_type = "occupied charging station" if is_charging else "another robot"
                print(f"[SAFETY] {self.robot_id} waypoint {next_step} blocked by {obstacle_type}. Replanning...")
                if self.goal:
                    t0 = time.perf_counter()
                    self.planner.init_search(self.pos, self.goal)
                    self.current_path = self.planner.plan(self.pos, self.goal, self._get_reservations())
                    self.last_plan_ms = (time.perf_counter() - t0) * 1000
                self.status = "YIELDING"
                self.wait_time += 1.0
                self.broadcast_telemetry()
                return

        # Move one step
        if len(self.current_path) > 0:
            next_step = self.current_path.pop(0)
            self.pos = (next_step[0], next_step[1])
            self.battery = max(5.0, self.battery - 0.1)
            self.status = "MOVING"
            self.wait_time = 0.0
        else:
            if self.status != "YIELDING":
                self.status = "IDLE"

        self.broadcast_telemetry()

    # ── Telemetry Broadcasting ────────────────────────────────────────

    def broadcast_telemetry(self):
        payload = {
            "robot_id": self.robot_id,
            "seq": self.seq,
            "pos": list(self.pos),
            "battery": round(self.battery, 1),
            "status": self.status,
            "security_status": getattr(self, "security_status", "NORMAL"),
            "comm_degraded": self.comm_degraded,
            "path": [list(p[:2]) for p in self.current_path],
            "priority": self.priority,
            "goal": list(self.goal) if self.goal else None,
            "mode": self.mode,
            "mission_state": self.mission_state,
            "plan_ms": round(self.last_plan_ms, 2),
            "dynamic_obstacles": list(self.world.dynamic_obstacles) if hasattr(self.world, 'dynamic_obstacles') else [],
            "timestamp": time.time()
        }
        payload["signature"] = self.auth.sign_payload(payload)

        # Broadcast across both MQTT and UDP Gossip Mesh
        self.mqtt.publish("fleet/telemetry", payload)

        intent_payload = {
            "robot_id": self.robot_id,
            "seq": self.seq,
            "current_pos": list(self.pos),
            "reserved_path": [list(p) for p in self.current_path],
            "priority_class": self.priority,
            "battery": round(self.battery, 1),
            "timestamp": time.time()
        }
        intent_payload["signature"] = self.auth.sign_payload(intent_payload)
        self.mqtt.publish("fleet/intent", intent_payload)

        self.gossip.broadcast(payload)


if __name__ == "__main__":
    rid = sys.argv[1] if len(sys.argv) > 1 else "R01"
    agent = EdgeAgent(rid)
    print(f"[{rid}] Edge Agent Online | Priority: {agent.priority} | Mode: {agent.mode}")
    while True:
        agent.tick()
        time.sleep(0.5)