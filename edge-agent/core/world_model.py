import json
import numpy as np

class WorldModel:
    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self.data = json.load(f)
        self.width = self.data["width"]
        self.height = self.data["height"]
        self.static_grid = np.zeros((self.width, self.height), dtype=np.int8)
        self.dynamic_obstacles = set()

        for s in self.data["shelves"]:
            for x in range(s["x1"], s["x2"] + 1):
                for y in range(s["y1"], s["y2"] + 1):
                    if 0 <= x < self.width and 0 <= y < self.height:
                        self.static_grid[x, y] = 1

    def is_blocked(self, x: int, y: int) -> bool:
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return True
        if self.static_grid[x, y] == 1:
            return True
        if (x, y) in self.dynamic_obstacles:
            return True
        if hasattr(self, 'charging_obstacles') and (x, y) in self.charging_obstacles:
            return True
        if hasattr(self, 'robot_obstacles') and (x, y) in self.robot_obstacles:
            return True
        return False

    def add_dynamic_obstacle(self, x: int, y: int):
        self.dynamic_obstacles.add((x, y))

    def clear_dynamic_obstacles(self):
        self.dynamic_obstacles.clear()