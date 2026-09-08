import os
import sys
import torch
import torch.nn as nn

class TinyConflictMLP(nn.Module):
    def __init__(self):
        super().__init__()
        # Input features: [dx, dy, rel_speed, dist_junction, priority_self, priority_other]
        self.net = nn.Sequential(
            nn.Linear(6, 16),
            nn.ReLU(),
            nn.Linear(16, 8),
            nn.ReLU(),
            nn.Linear(8, 1),
            nn.Sigmoid()
        )

    def forward(self, x):
        return self.net(x)

def build():
    try:
        sys.stdout.reconfigure(encoding='utf-8')  # type: ignore
    except Exception:
        pass
    os.makedirs(os.path.dirname(__file__), exist_ok=True)
    out_path = os.path.join(os.path.dirname(__file__), "conflict_predictor.onnx")
    model = TinyConflictMLP()
    model.eval()
    dummy_input = torch.randn(1, 6, dtype=torch.float32)
    torch.onnx.export(
        model,
        (dummy_input,),
        out_path,
        input_names=['features'],
        output_names=['conflict_prob'],
        dynamic_axes={'features': {0: 'batch'}}
    )
    print(f"Generated ONNX model: {out_path}")

if __name__ == "__main__":
    build()