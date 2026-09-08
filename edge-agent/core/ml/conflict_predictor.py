import os
import math

class ConflictPredictor:
    def __init__(self):
        self.session = None
        self.degraded_mode = False
        
        try:
            import numpy as np
            import onnxruntime as ort
            
            model_path = os.path.join(os.path.dirname(__file__), "conflict_predictor.onnx")
            if not os.path.exists(model_path):
                from .generate_models import build
                build()
            self.session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
            self.np = np
        except Exception as e:
            print(f"[!] ML ConflictPredictor degraded/fallback mode active. Reason: {e}")
            self.degraded_mode = True

    def predict_conflict_probability(self, pos_a, pos_b, speed_rel, dist_junction, prio_a, prio_b) -> float:
        dx = abs(pos_a[0] - pos_b[0])
        dy = abs(pos_a[1] - pos_b[1])
        
        if self.degraded_mode or self.session is None:
            # Fallback deterministic heuristic for demo when ML is unavailable
            distance = math.sqrt(dx**2 + dy**2)
            if distance < 2.0:
                return 0.8
            return 0.2
            
        features = self.np.array([[dx, dy, speed_rel, dist_junction, prio_a, prio_b]], dtype=self.np.float32)
        outputs = self.session.run(None, {'features': features})
        return float(outputs[0][0][0])