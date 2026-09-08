from pydantic import BaseModel, Field
from typing import List, Tuple, Optional

class TelemetryMessage(BaseModel):
    robot_id: str
    seq: int
    pos: Tuple[int, int]
    target: Optional[Tuple[int, int]] = None
    battery: float
    status: str  # IDLE, MOVING, YIELDING, STOPPED, COMM_DEGRADED
    path: List[Tuple[int, int]] = []
    priority: str
    signature: str = ""
    timestamp: float

class IntentMessage(BaseModel):
    robot_id: str
    seq: int
    current_pos: Tuple[int, int]
    reserved_path: List[Tuple[int, int, int]]  # [(x, y, t)]
    priority_class: str
    battery: float
    timestamp: float
    signature: str = ""

class SecurityAlert(BaseModel):
    event: str
    robot_id: str
    reason: str
    anomaly_score: float
    timestamp: float