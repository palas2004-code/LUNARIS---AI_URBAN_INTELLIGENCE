"""
LUNEX AI — Fine-Tuning Pipeline for YOLOv8 Pothole Detection Model
SIH 2026: SIH26124 (Urban Intelligence Road Safety)

Trains on single class '0: pothole' + 8 Hard Negative background categories with zero warmup delay.
"""

import os
import sys
import shutil
from pathlib import Path

def train_lunex_pothole_model():
    print("==================================================")
    print("       LUNEX-POTHOLE-V1 FAST CONVERGENCE TRAINING ")
    print("==================================================")

    from ultralytics import YOLO

    base_dir = Path(__file__).parent.resolve()
    data_yaml = base_dir / "pothole_dataset" / "data.yaml"
    weights_dir = base_dir / "models"
    weights_dir.mkdir(parents=True, exist_ok=True)

    # Initialize YOLOv8n
    model = YOLO("yolov8n.pt")

    print("[*] Training YOLOv8n with warmup_epochs=0 for direct convergence...")
    results = model.train(
        data=str(data_yaml),
        epochs=8,
        imgsz=320,
        batch=16,
        workers=0,
        warmup_epochs=0,
        lr0=0.01,
        lrf=0.01,
        name="pothole_v1_converged",
        project=str(base_dir / "runs"),
        exist_ok=True,
        verbose=True
    )

    print("[*] Locating best.pt...")
    best_pt = base_dir / "runs" / "pothole_v1_converged" / "weights" / "best.pt"
    if not best_pt.exists():
        best_pt = base_dir / "runs" / "pothole_v1_converged" / "weights" / "last.pt"

    dest_best = base_dir / "best.pt"
    dest_versioned = weights_dir / "lunex_pothole_v1.pt"

    if best_pt.exists():
        shutil.copy(best_pt, dest_best)
        shutil.copy(best_pt, dest_versioned)
        print(f"[OK] Exported trained model to: {dest_best}")
        print(f"[OK] Exported versioned model to: {dest_versioned}")

if __name__ == "__main__":
    train_lunex_pothole_model()
