import heapq

class DStarLitePlanner:
    def __init__(self, world_model):
        self.world = world_model
        self.U = []  # Priority Queue
        self.k_m = 0.0 # Key modifier for moving start
        self.rhs = {}
        self.g = {}
        self.s_start = None
        self.s_goal = None
        self.last_start = None

    def heuristic(self, a: tuple, b: tuple) -> float:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def calculate_key(self, s: tuple) -> tuple:
        min_g_rhs = min(self.g.get(s, float('inf')), self.rhs.get(s, float('inf')))
        if self.s_start is None:
            return (min_g_rhs + self.k_m, min_g_rhs)
        return (min_g_rhs + self.heuristic(self.s_start, s) + self.k_m, min_g_rhs)

    def update_vertex(self, u: tuple):
        if u != self.s_goal:
            min_rhs = float('inf')
            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                s_prime = (u[0] + dx, u[1] + dy)
                if not self.world.is_blocked(s_prime[0], s_prime[1]):
                    min_rhs = min(min_rhs, self.g.get(s_prime, float('inf')) + 1)
            self.rhs[u] = min_rhs
        
        # Remove u from priority queue if it exists (O(N) heap rebuild is fine for 30x20 grid)
        self.U = [item for item in self.U if item[1] != u]
        heapq.heapify(self.U)

        if self.g.get(u, float('inf')) != self.rhs.get(u, float('inf')):
            heapq.heappush(self.U, (self.calculate_key(u), u))

    def compute_shortest_path(self):
        if self.s_start is None:
            return
        while self.U and (self.U[0][0] < self.calculate_key(self.s_start) or 
                          self.rhs.get(self.s_start, float('inf')) != self.g.get(self.s_start, float('inf'))):
            k_old, u = heapq.heappop(self.U)
            if k_old < self.calculate_key(u):
                heapq.heappush(self.U, (self.calculate_key(u), u))
            elif self.g.get(u, float('inf')) > self.rhs.get(u, float('inf')):
                self.g[u] = self.rhs.get(u, float('inf'))
                for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                    s_pred = (u[0] + dx, u[1] + dy)
                    if not self.world.is_blocked(s_pred[0], s_pred[1]):
                        self.update_vertex(s_pred)
            else:
                self.g[u] = float('inf')
                self.update_vertex(u)
                for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                    s_pred = (u[0] + dx, u[1] + dy)
                    if not self.world.is_blocked(s_pred[0], s_pred[1]):
                        self.update_vertex(s_pred)

    def init_search(self, start: tuple, goal: tuple):
        self.U = []
        self.k_m = 0.0
        self.rhs = {}
        self.g = {}
        self.s_start = start
        self.s_goal = goal
        self.last_start = start
        self.rhs[self.s_goal] = 0
        heapq.heappush(self.U, (self.calculate_key(self.s_goal), self.s_goal))
        self.compute_shortest_path()

    def extract_2d_path(self) -> list:
        if self.s_start is None:
            return []
        path = [self.s_start]
        curr = self.s_start
        while curr != self.s_goal and curr is not None:
            min_cost = float('inf')
            next_node = None
            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                nxt = (curr[0] + dx, curr[1] + dy)
                if not self.world.is_blocked(nxt[0], nxt[1]):
                    cost = self.g.get(nxt, float('inf'))
                    if cost < min_cost:
                        min_cost = cost
                        next_node = nxt
            
            # Break if trapped or caught in a loop
            if next_node is None or next_node in path: 
                break
            
            path.append(next_node)
            curr = next_node
        return path
        
    def plan(self, start: tuple, goal: tuple, time_reservations: set, start_t: int = 0) -> list:
        """
        The Bridge:
        1. Uses D* Lite for lightning-fast 2D incremental repair.
        2. Converts the 2D path into a 3D space-time path for the CBS negotiator.
        """
        if self.s_goal != goal or self.s_start is None:
            # New task: initialize fresh D* Lite search
            self.init_search(start, goal)
        elif start != self.last_start:
            # Robot moved: update k_m and incrementally repair graph
            if self.last_start is not None:
                self.k_m += self.heuristic(self.last_start, start)
            self.s_start = start
            self.last_start = start
            self.compute_shortest_path()
        
        # Pull the repaired 2D route
        path_2d = self.extract_2d_path()
        
        # Elevate to 3D Space-Time path, avoiding CBS reservations
        st_path = []
        t = start_t
        for pos in path_2d:
            # If cell is reserved by another robot, inject a Wait action at current pos
            while (pos[0], pos[1], t) in time_reservations:
                if st_path:
                    st_path.append((st_path[-1][0], st_path[-1][1], t))
                else:
                    st_path.append((pos[0], pos[1], t))
                t += 1
            
            st_path.append((pos[0], pos[1], t))
            t += 1
            
        return st_path