import hashlib
import json
import time

class HashLedger:
    def __init__(self):
        self.chain = []
        self.append_block("GENESIS", ["SYSTEM"], "Ledger initialized", 0)

    def append_block(self, event: str, robots: list, reason: str, timestamp: float | None = None):
        timestamp = timestamp or time.time()
        prev_hash = self.chain[-1]["hash"] if self.chain else "0" * 64
        block_index = len(self.chain)

        payload = {
            "index": block_index,
            "prev_hash": prev_hash,
            "event": event,
            "robots": robots,
            "reason": reason,
            "timestamp": timestamp
        }

        block_str = json.dumps(payload, sort_keys=True)
        block_hash = hashlib.sha256(block_str.encode('utf-8')).hexdigest()
        payload["hash"] = block_hash
        self.chain.append(payload)
        return payload

    def verify_integrity(self) -> bool:
        for i in range(1, len(self.chain)):
            curr = self.chain[i]
            prev = self.chain[i - 1]
            if curr["prev_hash"] != prev["hash"]:
                return False
            recalculated = {k: v for k, v in curr.items() if k != "hash"}
            expected = hashlib.sha256(json.dumps(recalculated, sort_keys=True).encode('utf-8')).hexdigest()
            if curr["hash"] != expected:
                return False
        return True