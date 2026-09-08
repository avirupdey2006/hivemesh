import hmac
import hashlib
import json

class SecurityAuth:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key.encode('utf-8')
        self.last_seen_seq = {}

    def sign_payload(self, data: dict) -> str:
        # Canonical stringification excluding existing signature
        cleaned = {k: v for k, v in data.items() if k != "signature"}
        serialized = json.dumps(cleaned, sort_keys=True)
        return hmac.new(self.secret_key, serialized.encode('utf-8'), hashlib.sha256).hexdigest()

    def verify(self, data: dict) -> bool:
        signature = data.get("signature", "")
        if not signature:
            return False
        expected = self.sign_payload(data)
        if not hmac.compare_digest(signature, expected):
            return False

        robot_id = data.get("robot_id")
        seq = data.get("seq", 0)
        # Anti-Replay: Sequence must strictly advance
        if robot_id in self.last_seen_seq and seq <= self.last_seen_seq[robot_id]:
            return False
            
        self.last_seen_seq[robot_id] = seq
        return True