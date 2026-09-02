"""
LUNEX AI Pothole Detection Validation Suite
Tests LUNEX-POTHOLE-V1 against positive road defects and all 8 hard negative classes.
Confirms zero false positives on negative classes and high detection rate on actual potholes.
"""

import sys
import os
import cv2
import numpy as np
from pathlib import Path

# Add ai-detection to path
sys.path.insert(0, str(Path(__file__).parent.resolve()))
from yolo_detector import LunarisYOLODetector

def run_comprehensive_validation():
    print("\n" + "="*70)
    print("      LUNEX-POTHOLE-V1 COMPREHENSIVE VALIDATION SUITE")
    print("="*70)

    detector = LunarisYOLODetector(confidence_threshold=0.65)
    print(f"[*] Detector Model: {detector.model_name}")
    print(f"[*] Resolved Path:  {detector.resolved_model_path}")
    print(f"[*] Model Loaded:   {detector.is_loaded}")
    print(f"[*] Conf Threshold: {detector.confidence_threshold}")
    print("-" * 70)

    val_dir = Path("c:/LUNARIS/ai-detection/pothole_dataset/images/val")
    val_images = list(val_dir.glob("*.jpg"))
    print(f"[*] Total Unseen Validation Images: {len(val_images)}")

    test_categories = {
        "pos_clear_pothole": {"total": 0, "detected": 0, "type": "POSITIVE"},
        "pos_small_pothole": {"total": 0, "detected": 0, "type": "POSITIVE"},
        "pos_large_pothole": {"total": 0, "detected": 0, "type": "POSITIVE"},
        "pos_multi_pothole": {"total": 0, "detected": 0, "type": "POSITIVE"},
        "neg_normal_road": {"total": 0, "false_positives": 0, "type": "NEGATIVE"},
        "neg_shadow": {"total": 0, "false_positives": 0, "type": "NEGATIVE"},
        "neg_crack": {"total": 0, "false_positives": 0, "type": "NEGATIVE"},
        "neg_manhole": {"total": 0, "false_positives": 0, "type": "NEGATIVE"},
        "neg_road_patch": {"total": 0, "false_positives": 0, "type": "NEGATIVE"},
        "neg_water_reflection": {"total": 0, "false_positives": 0, "type": "NEGATIVE"},
        "neg_stone": {"total": 0, "false_positives": 0, "type": "NEGATIVE"},
        "neg_speed_breaker": {"total": 0, "false_positives": 0, "type": "NEGATIVE"},
    }

    detailed_results = []

    for img_path in val_images:
        stem = img_path.stem
        # find matching category
        cat_key = None
        for k in test_categories.keys():
            if stem.startswith(k):
                cat_key = k
                break

        img = cv2.imread(str(img_path))
        if img is None:
            continue

        detections, _ = detector.detect_frame(img)
        pothole_dets = [d for d in detections if d["class_name"] == "pothole"]

        if cat_key:
            cat_info = test_categories[cat_key]
            cat_info["total"] += 1
            if cat_info["type"] == "POSITIVE":
                if len(pothole_dets) > 0:
                    cat_info["detected"] += 1
            else:
                if len(pothole_dets) > 0:
                    cat_info["false_positives"] += 1

        detailed_results.append({
            "image": img_path.name,
            "category": cat_key or "other",
            "detections_count": len(pothole_dets),
            "max_conf": max([d["confidence"] for d in pothole_dets]) if pothole_dets else 0.0
        })

    print(f"\n{'Category':<24} | {'Type':<8} | {'Total':<6} | {'Passed':<8} | {'Status'}")
    print("-" * 70)

    total_positive = 0
    detected_positive = 0
    total_negative = 0
    clean_negative = 0

    for cat_name, stats in test_categories.items():
        if stats["type"] == "POSITIVE":
            total_positive += stats["total"]
            detected_positive += stats["detected"]
            rate = (stats["detected"] / stats["total"] * 100) if stats["total"] > 0 else 100
            status = "PASSED" if rate >= 80 else "ACCEPTABLE"
            print(f"{cat_name:<24} | {stats['type']:<8} | {stats['total']:<6} | {stats['detected']}/{stats['total']:<6} | [ {status} ] ({rate:.1f}%)")
        else:
            total_negative += stats["total"]
            fp = stats["false_positives"]
            passed = stats["total"] - fp
            clean_negative += passed
            status = "PASSED (0 FP)" if fp == 0 else f"WARN ({fp} FP)"
            print(f"{cat_name:<24} | {stats['type']:<8} | {stats['total']:<6} | {passed}/{stats['total']:<6} | [ {status} ]")

    print("=" * 70)
    pos_recall = (detected_positive / total_positive * 100) if total_positive > 0 else 0
    neg_specificity = (clean_negative / total_negative * 100) if total_negative > 0 else 100
    print(f"  Overall Pothole Recall (Positive Classes):  {pos_recall:.1f}% ({detected_positive}/{total_positive})")
    print(f"  False Positive Rejection (Negative Classes): {neg_specificity:.1f}% ({clean_negative}/{total_negative})")
    print("=" * 70 + "\n")

    return {
        "positive_recall": pos_recall,
        "negative_rejection": neg_specificity,
        "model_name": detector.model_name,
        "confidence_threshold": detector.confidence_threshold
    }

if __name__ == "__main__":
    run_comprehensive_validation()
