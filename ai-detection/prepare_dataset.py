"""
LUNARIS — Fast & High-Precision Pothole & Road Defect Dataset Generator
"""

import os
import random
import cv2
import numpy as np
from pathlib import Path

random.seed(42)
np.random.seed(42)

DATASET_ROOT = Path("c:/LUNARIS/ai-detection/pothole_dataset")
IMG_SIZE = (640, 640)

def create_base_road_canvas():
    base_color = random.randint(35, 65)
    canvas = np.full((IMG_SIZE[1], IMG_SIZE[0], 3), base_color, dtype=np.uint8)
    noise = np.random.normal(0, random.uniform(8, 18), (IMG_SIZE[1], IMG_SIZE[0], 3)).astype(np.int16)
    canvas = np.clip(canvas.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    if random.random() > 0.4:
        color = (0, 210, 240) if random.random() > 0.5 else (220, 220, 220)
        cv2.line(canvas, (int(IMG_SIZE[0] * 0.1), int(IMG_SIZE[1] * 0.2)), 
                         (int(IMG_SIZE[0] * 0.05), IMG_SIZE[1]), color, random.randint(3, 7))
        cv2.line(canvas, (int(IMG_SIZE[0] * 0.9), int(IMG_SIZE[1] * 0.2)), 
                         (int(IMG_SIZE[0] * 0.95), IMG_SIZE[1]), color, random.randint(3, 7))
    return canvas

def generate_pothole_sample(pothole_type="standard"):
    canvas = create_base_road_canvas()
    bboxes = []
    num_potholes = random.randint(1, 3) if pothole_type == "multi" else 1

    for _ in range(num_potholes):
        if pothole_type == "small":
            w = random.randint(60, 110)
            h = random.randint(45, 85)
        elif pothole_type == "large":
            w = random.randint(180, 310)
            h = random.randint(120, 220)
        else:
            w = random.randint(90, 200)
            h = random.randint(70, 150)

        cx = random.randint(w // 2 + 50, IMG_SIZE[0] - w // 2 - 50)
        cy = random.randint(h // 2 + 100, IMG_SIZE[1] - h // 2 - 40)

        num_vertices = random.randint(16, 28)
        angles = np.linspace(0, 2 * np.pi, num_vertices, endpoint=False)
        rx = w / 2.0
        ry = h / 2.0
        
        pts = []
        for a in angles:
            jitter = random.uniform(0.72, 1.28)
            px = int(cx + rx * np.cos(a) * jitter)
            py = int(cy + ry * np.sin(a) * jitter)
            pts.append([px, py])
        pts = np.array(pts, dtype=np.int32)

        # Fractured light gray border
        cv2.drawContours(canvas, [pts], -1, (random.randint(90, 125), random.randint(90, 125), random.randint(90, 125)), 
                         thickness=random.randint(4, 9))

        # Inner cavity
        inner_color = random.randint(10, 24)
        inner_pts = []
        for a in angles:
            jitter = random.uniform(0.60, 1.05)
            px = int(cx + (rx - 6) * np.cos(a) * jitter)
            py = int(cy + (ry - 6) * np.sin(a) * jitter)
            inner_pts.append([px, py])
        inner_pts = np.array(inner_pts, dtype=np.int32)
        cv2.fillPoly(canvas, [inner_pts], (inner_color, inner_color, inner_color))

        # Pebbles in crater
        for _ in range(random.randint(8, 25)):
            pebble_x = int(cx + random.uniform(-rx * 0.7, rx * 0.7))
            pebble_y = int(cy + random.uniform(-ry * 0.7, ry * 0.7))
            p_size = random.randint(2, 6)
            p_col = random.randint(40, 80)
            cv2.circle(canvas, (pebble_x, pebble_y), p_size, (p_col, p_col, p_col), -1)

        x_min = max(0, int(np.min(pts[:, 0]) - 3))
        y_min = max(0, int(np.min(pts[:, 1]) - 3))
        x_max = min(IMG_SIZE[0], int(np.max(pts[:, 0]) + 3))
        y_max = min(IMG_SIZE[1], int(np.max(pts[:, 1]) + 3))

        box_w = x_max - x_min
        box_h = y_max - y_min
        norm_cx = (x_min + box_w / 2.0) / IMG_SIZE[0]
        norm_cy = (y_min + box_h / 2.0) / IMG_SIZE[1]
        norm_w = box_w / IMG_SIZE[0]
        norm_h = box_h / IMG_SIZE[1]

        bboxes.append(f"0 {norm_cx:.6f} {norm_cy:.6f} {norm_w:.6f} {norm_h:.6f}")

    return canvas, bboxes

def generate_negative_sample(neg_type):
    canvas = create_base_road_canvas()

    if neg_type == "normal_road":
        pass
    elif neg_type == "shadow":
        overlay = canvas.copy()
        if random.random() > 0.5:
            for _ in range(random.randint(3, 8)):
                pt1 = (random.randint(0, IMG_SIZE[0]), 0)
                pt2 = (random.randint(0, IMG_SIZE[0]), IMG_SIZE[1])
                cv2.line(overlay, pt1, pt2, (8, 8, 10), thickness=random.randint(25, 80))
        else:
            poly = np.array([[0, random.randint(100, 300)], [IMG_SIZE[0], random.randint(300, 500)], 
                             [IMG_SIZE[0], IMG_SIZE[1]], [0, IMG_SIZE[1]]], dtype=np.int32)
            cv2.fillPoly(overlay, [poly], (12, 12, 16))
        cv2.addWeighted(overlay, 0.65, canvas, 0.35, 0, canvas)
    elif neg_type == "crack":
        start_x = random.randint(100, IMG_SIZE[0] - 100)
        curr_x, curr_y = start_x, random.randint(50, 200)
        for _ in range(random.randint(15, 30)):
            next_x = curr_x + random.randint(-18, 18)
            next_y = curr_y + random.randint(12, 28)
            cv2.line(canvas, (curr_x, curr_y), (next_x, next_y), (20, 20, 20), thickness=random.randint(1, 3))
            curr_x, curr_y = next_x, next_y
    elif neg_type == "manhole":
        mx = random.randint(150, IMG_SIZE[0] - 150)
        my = random.randint(200, IMG_SIZE[1] - 150)
        radius = random.randint(50, 95)
        cv2.circle(canvas, (mx, my), radius, (55, 55, 58), -1)
        cv2.circle(canvas, (mx, my), radius, (75, 75, 80), 3)
        cv2.circle(canvas, (mx, my), radius - 15, (40, 40, 42), 2)
        cv2.circle(canvas, (mx, my), radius - 30, (70, 70, 72), 2)
        cv2.circle(canvas, (mx, my), 8, (30, 30, 32), -1)
    elif neg_type == "road_patch":
        px = random.randint(100, IMG_SIZE[0] - 250)
        py = random.randint(150, IMG_SIZE[1] - 200)
        pw = random.randint(140, 260)
        ph = random.randint(80, 180)
        patch_color = random.randint(20, 32)
        cv2.rectangle(canvas, (px, py), (px + pw, py + ph), (patch_color, patch_color, patch_color), -1)
        cv2.rectangle(canvas, (px, py), (px + pw, py + ph), (10, 10, 12), 2)
    elif neg_type == "water_reflection":
        wx = random.randint(150, IMG_SIZE[0] - 150)
        wy = random.randint(200, IMG_SIZE[1] - 150)
        rw = random.randint(80, 180)
        rh = random.randint(40, 90)
        overlay = canvas.copy()
        cv2.ellipse(overlay, (wx, wy), (rw, rh), random.randint(0, 30), 0, 360, (140, 160, 180), -1)
        cv2.addWeighted(overlay, 0.4, canvas, 0.6, 0, canvas)
    elif neg_type == "stone":
        for _ in range(random.randint(6, 18)):
            sx = random.randint(100, IMG_SIZE[0] - 100)
            sy = random.randint(150, IMG_SIZE[1] - 100)
            scolor = random.randint(150, 210)
            cv2.circle(canvas, (sx, sy), random.randint(3, 8), (scolor, scolor, scolor), -1)
    elif neg_type == "speed_breaker":
        by = random.randint(250, IMG_SIZE[1] - 200)
        bh = random.randint(50, 90)
        cv2.rectangle(canvas, (0, by), (IMG_SIZE[0], by + bh), (45, 45, 50), -1)
        for x_pos in range(0, IMG_SIZE[0], 60):
            pts = np.array([[x_pos, by], [x_pos + 30, by], [x_pos + 50, by + bh], [x_pos + 20, by + bh]], dtype=np.int32)
            cv2.fillPoly(canvas, [pts], (0, 215, 255))

    return canvas, []

def build_dataset():
    print("[+] Initializing LUNEX Pothole Dataset Generation...")
    
    for split in ["train", "val"]:
        p_img = DATASET_ROOT / "images" / split
        p_lbl = DATASET_ROOT / "labels" / split
        if p_img.exists():
            shutil.rmtree(p_img)
        if p_lbl.exists():
            shutil.rmtree(p_lbl)
        p_img.mkdir(parents=True, exist_ok=True)
        p_lbl.mkdir(parents=True, exist_ok=True)

    positive_configs = [
        ("clear_pothole", 25),
        ("small_pothole", 20),
        ("large_pothole", 20),
        ("multi_pothole", 15),
    ]

    negative_configs = [
        ("normal_road", 12),
        ("shadow", 16),
        ("crack", 12),
        ("manhole", 10),
        ("road_patch", 10),
        ("water_reflection", 8),
        ("stone", 6),
        ("speed_breaker", 6),
    ]

    all_samples = []
    for p_type, count in positive_configs:
        for i in range(count):
            all_samples.append(("positive", p_type, f"pos_{p_type}_{i:03d}"))

    for n_type, count in negative_configs:
        for i in range(count):
            all_samples.append(("negative", n_type, f"neg_{n_type}_{i:03d}"))

    random.shuffle(all_samples)
    split_idx = int(len(all_samples) * 0.8)
    train_samples = all_samples[:split_idx]
    val_samples = all_samples[split_idx:]

    print(f"[*] Total Dataset: {len(all_samples)} images (Train: {len(train_samples)}, Val: {len(val_samples)})")

    for split_name, samples in [("train", train_samples), ("val", val_samples)]:
        img_dir = DATASET_ROOT / "images" / split_name
        lbl_dir = DATASET_ROOT / "labels" / split_name
        pos_count = 0
        neg_count = 0

        for category, sub_type, filename in samples:
            if category == "positive":
                subtype_arg = "small" if "small" in sub_type else ("large" if "large" in sub_type else ("multi" if "multi" in sub_type else "standard"))
                img, bboxes = generate_pothole_sample(subtype_arg)
                pos_count += 1
            else:
                img, bboxes = generate_negative_sample(sub_type)
                neg_count += 1

            cv2.imwrite(str(img_dir / f"{filename}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            with open(lbl_dir / f"{filename}.txt", "w") as f:
                if bboxes:
                    f.write("\n".join(bboxes) + "\n")

        print(f"  [OK] [{split_name.upper()}]: {len(samples)} images ({pos_count} positive, {neg_count} hard negatives)")

    yaml_content = f"""# LUNEX Road Defect & Pothole Dataset YAML
path: c:/LUNARIS/ai-detection/pothole_dataset
train: images/train
val: images/val

names:
  0: pothole
"""
    with open(DATASET_ROOT / "data.yaml", "w") as f:
        f.write(yaml_content)

    print(f"[+] Generated {DATASET_ROOT / 'data.yaml'}")
    print("[+] Dataset generation completed successfully!")

if __name__ == "__main__":
    import shutil
    build_dataset()
