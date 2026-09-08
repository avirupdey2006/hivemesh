class CBSNegotiator:
    PRIORITY_WEIGHTS = {"HEAVY": 300, "LIGHT": 200, "EMPTY": 100}

    @staticmethod
    def evaluate_priority(prio_class: str, battery: float, wait_time: float, robot_id: str) -> float:
        base = CBSNegotiator.PRIORITY_WEIGHTS.get(prio_class, 100)
        # Lower battery receives higher urgency to prevent stranding
        battery_urgency = (100.0 - battery) * 0.5
        starvation_bonus = wait_time * 10.0
        deterministic_hash = (hash(robot_id) % 10) * 0.01
        return base + battery_urgency + starvation_bonus + deterministic_hash

    @staticmethod
    def detect_conflict(path_a: list, path_b: list) -> tuple:
        """Returns (conflict_pos, time_step) if an intersection exists."""
        # 1. VERTEX CONFLICT: Check if both robots occupy the exact same (x, y) at the exact same time (t)
        pos_time_a = {(p[0], p[1], p[2]) for p in path_a}
        for (bx, by, bt) in path_b:
            if (bx, by, bt) in pos_time_a:
                return ((bx, by), bt)
                
        # 2. EDGE / SWAP CONFLICT: Check if robots swap cells
        edge_a = {}
        for i in range(len(path_a) - 1):
            u = (path_a[i][0], path_a[i][1])
            v = (path_a[i+1][0], path_a[i+1][1])
            t = path_a[i+1][2]
            edge_a[(u, v, t)] = True
            
        for i in range(len(path_b) - 1):
            u = (path_b[i][0], path_b[i][1])
            v = (path_b[i+1][0], path_b[i+1][1])
            t = path_b[i+1][2]
            # If B moves u->v, an edge conflict happens if A moves v->u at the same time t
            if (v, u, t) in edge_a:
                return (v, t)
                
        return (None, None)

    @staticmethod
    def negotiate(r_self: dict, r_other: dict, conflict_info: tuple) -> dict:
        p1 = CBSNegotiator.evaluate_priority(r_self["prio"], r_self["battery"], r_self["wait"], r_self["id"])
        p2 = CBSNegotiator.evaluate_priority(r_other["prio"], r_other["battery"], r_other["wait"], r_other["id"])

        if p1 >= p2:
            return {
                "decision": "PROCEED",
                "yielding_robot": r_other["id"],
                "reason": f"{r_self['id']} (prio={r_self['prio']}, score={p1:.1f}) won right-of-way over {r_other['id']} (prio={r_other['prio']}, score={p2:.1f})"
            }
        else:
            return {
                "decision": "YIELD",
                "yielding_robot": r_self["id"],
                "reason": f"{r_self['id']} yielded to {r_other['id']} at {conflict_info[0]} due to payload urgency & battery priority"
            }