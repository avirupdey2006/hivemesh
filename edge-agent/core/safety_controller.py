import math

class SafetyController:
    def __init__(self, safe_distance: float = 0.1):
        self.safe_distance = safe_distance
        self.emergency_stop_active = False

    def evaluate_immediate_threat(self, current_pos: tuple, neighbor_positions: list) -> bool:
        for n_pos in neighbor_positions:
            dist = math.hypot(current_pos[0] - n_pos[0], current_pos[1] - n_pos[1])
            if dist < self.safe_distance:
                self.emergency_stop_active = True
                return True
        self.emergency_stop_active = False
        return False