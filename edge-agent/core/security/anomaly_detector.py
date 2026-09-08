import math
import time

class AnomalyDetector:
    def __init__(self, max_allowed_speed: float = 2.5):
        self.max_allowed_speed = max_allowed_speed
        self.last_reports = {}

    def check_telemetry(self, robot_id: str, pos: tuple, timestamp: float) -> tuple[bool, str, float]:
        if robot_id not in self.last_reports:
            self.last_reports[robot_id] = (pos, timestamp)
            return (True, "NORMAL", 0.0)

        prev_pos, prev_t = self.last_reports[robot_id]
        dt = max(0.001, timestamp - prev_t)
        dist = math.hypot(pos[0] - prev_pos[0], pos[1] - prev_pos[1])
        velocity = dist / dt

        self.last_reports[robot_id] = (pos, timestamp)

        if velocity > self.max_allowed_speed:
            score = round(min(1.0, (velocity - self.max_allowed_speed) / 5.0 + 0.6), 2)
            return (False, f"Velocity anomaly ({velocity:.2f} cells/sec exceeds {self.max_allowed_speed})", score)

        return (True, "NORMAL", 0.0)