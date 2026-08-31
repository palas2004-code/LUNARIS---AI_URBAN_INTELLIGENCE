"""
LUNARIS AI Stream Processor & Debouncing Tracker
Runs on Edge Device (Mini PC / Jetson / GPU Worker).
Processes local RTSP/Camera feed with configurable inference FPS,
Centroid/IoU defect tracking, and multi-frame debouncing.
"""

import cv2
import time
import math
import base64
import asyncio
import logging
import urllib.request
import json
from datetime import datetime
from typing import Optional, Dict, List, Any
from yolo_detector import LunarisYOLODetector

logger = logging.getLogger("lunaris.ai.processor")

class TrackedDefect:
    def __init__(self, track_id: int, class_name: str, bbox: Dict[str, float], confidence: float):
        self.track_id = track_id
        self.class_name = class_name
        self.bbox = bbox
        self.confidence = confidence
        self.centroid = self._calc_centroid(bbox)
        self.first_seen = time.time()
        self.last_seen = time.time()
        self.frame_count = 1
        self.dispatched = False  # Critical debouncing flag

    def _calc_centroid(self, bbox: Dict[str, float]):
        cx = (bbox["x_min"] + bbox["x_max"]) / 2.0
        cy = (bbox["y_min"] + bbox["y_max"]) / 2.0
        return (cx, cy)

    def update(self, bbox: Dict[str, float], confidence: float):
        self.bbox = bbox
        self.confidence = max(self.confidence, confidence)
        self.centroid = self._calc_centroid(bbox)
        self.last_seen = time.time()
        self.frame_count += 1

class StreamProcessor:
    def __init__(
        self,
        bus_id: str = "BUS-07",
        stream_url: str = "rtsp://localhost:8554/bus07",
        backend_url: str = "http://localhost:8080/api/v1/detections/ingest",
        inference_fps: int = 10,
        debounce_cooldown_seconds: float = 6.0
    ):
        self.bus_id = bus_id
        self.stream_url = stream_url
        self.backend_url = backend_url
        self.inference_fps = max(1, min(30, inference_fps))  # 5-15 FPS recommended
        self.debounce_cooldown = debounce_cooldown_seconds
        
        self.detector = LunarisYOLODetector()
        self.is_running = False
        self.last_frame = None
        self.last_annotated_frame = None
        
        # Debouncing & Tracking State
        self.active_tracks: Dict[int, TrackedDefect] = {}
        self.next_track_id = 1
        self.tracking_distance_threshold = 0.15  # Normalized distance for matching

    async def start(self):
        self.is_running = True
        logger.info(f"Starting Edge StreamProcessor for {self.bus_id} at {self.inference_fps} FPS on {self.stream_url}")
        asyncio.create_task(self._process_loop())

    def stop(self):
        self.is_running = False
        logger.info(f"Stopped StreamProcessor for {self.bus_id}")

    async def _process_loop(self):
        cap = cv2.VideoCapture(self.stream_url)
        use_synthetic = not cap.isOpened()

        frame_count = 0
        target_frame_time = 1.0 / self.inference_fps

        while self.is_running:
            t_start = time.time()

            if not use_synthetic and cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    await asyncio.sleep(0.05)
                    continue
            else:
                frame = self._generate_synthetic_road_frame(frame_count)

            self.last_frame = frame
            frame_count += 1

            # 1. Run YOLO Inference at configured FPS rate
            raw_detections, annotated = self.detector.detect_frame(frame)
            self.last_annotated_frame = annotated

            # 2. Update Multi-Frame Spatial/Temporal Tracker & Debouncer
            await self._update_tracker_and_debounce(raw_detections, frame)

            # 3. FPS Limiter
            elapsed = time.time() - t_start
            sleep_time = max(0.001, target_frame_time - elapsed)
            await asyncio.sleep(sleep_time)

        if cap.isOpened():
            cap.release()

    async def _update_tracker_and_debounce(self, detections: List[Dict[str, Any]], frame):
        """
        Critical Debouncing Algorithm:
        Matches detections across consecutive frames using Euclidean centroid distance.
        If a pothole appears in 100 consecutive frames, it maps to the SAME track_id
        and only 1 consolidated physical event is dispatched to the cloud.
        """
        now = time.time()
        matched_track_ids = set()

        # Filter road surface defects
        defect_detections = [d for d in detections if d["class_name"] in ["pothole", "road_damage", "waterlogging"]]

        for det in defect_detections:
            cx = (det["x_min"] + det["x_max"]) / 2.0
            cy = (det["y_min"] + det["y_max"]) / 2.0

            best_match_id = None
            min_dist = float("inf")

            for t_id, track in self.active_tracks.items():
                if track.class_name == det["class_name"]:
                    dist = math.hypot(cx - track.centroid[0], cy - track.centroid[1])
                    if dist < min_dist and dist <= self.tracking_distance_threshold:
                        min_dist = dist
                        best_match_id = t_id

            if best_match_id is not None:
                # Update existing track
                self.active_tracks[best_match_id].update(det, det["confidence"])
                matched_track_ids.add(best_match_id)
            else:
                # Create new track
                new_track = TrackedDefect(self.next_track_id, det["class_name"], det, det["confidence"])
                self.active_tracks[self.next_track_id] = new_track
                matched_track_ids.add(self.next_track_id)
                self.next_track_id += 1

        # Evaluate tracks for single debounced dispatch
        for t_id, track in list(self.active_tracks.items()):
            # Dispatch when track is confirmed (seen in >= 2 frames) and not yet dispatched
            if not track.dispatched and track.frame_count >= 2 and track.confidence >= 80.0:
                await self._dispatch_debounced_event(track, frame)
                track.dispatched = True

            # Prune stale tracks (not seen for > 3.0 seconds)
            if now - track.last_seen > 3.0:
                del self.active_tracks[t_id]

    async def _dispatch_debounced_event(self, track: TrackedDefect, frame):
        """
        Dispatches ONE consolidated physical detection event to the backend.
        Never floods Supabase with redundant frame-by-frame rows.
        """
        logger.info(f"🎯 [DEBOUNCED CLUSTER] Track #{track.track_id}: {track.class_name.upper()} ({track.confidence:.1f}%) confirmed across {track.frame_count} frames. Dispatching to Cloud...")

        _, buffer = cv2.imencode('.jpg', self.last_annotated_frame if self.last_annotated_frame is not None else frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        evidence_b64 = base64.b64encode(buffer).decode('utf-8')

        payload = {
            "bus_id": self.bus_id,
            "bus_plate": "WB-04-E-2910",
            "type": track.class_name.capitalize(),
            "category": track.class_name.capitalize(),
            "location": "Park Street, Kolkata",
            "lat": 22.5512,
            "lng": 88.3524,
            "severity": "HIGH" if track.confidence > 90 else "MEDIUM",
            "confidence": track.confidence,
            "bounding_boxes": [{
                "class_name": track.class_name,
                "confidence": track.confidence / 100.0,
                "x_min": track.bbox["x_min"],
                "y_min": track.bbox["y_min"],
                "x_max": track.bbox["x_max"],
                "y_max": track.bbox["y_max"],
                "track_id": track.track_id,
                "clustered_frames": track.frame_count
            }],
            "evidence_image_base64": f"data:image/jpeg;base64,{evidence_b64}",
            "details": f"Debounced Physical Defect (Track #{track.track_id}, {track.frame_count} frames accumulated)"
        }

        try:
            req = urllib.request.Request(
                self.backend_url,
                data=json.dumps(payload).encode('utf-8'),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                logger.info(f"✅ Dispatched event for Track #{track.track_id}. Status: {resp.status}")
        except Exception as e:
            logger.debug(f"Cloud dispatch note: {e}")

    def _generate_synthetic_road_frame(self, count: int):
        frame = cv2.UMat(720, 1280, cv2.CV_8UC3) if hasattr(cv2, 'UMat') else None
        # fallback simple frame
        import numpy as np
        f = np.full((720, 1280, 3), 32, dtype=np.uint8)
        cv2.line(f, (640, 260), (100, 720), (255, 255, 255), 4)
        cv2.line(f, (640, 260), (1180, 720), (255, 255, 255), 4)
        cv2.ellipse(f, (780, 500), (60, 30), 0, 0, 360, (20, 20, 22), -1)
        return f

    def get_latest_jpeg(self) -> bytes:
        frame = self.last_annotated_frame if self.last_annotated_frame is not None else self.last_frame
        if frame is None:
            import numpy as np
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
        _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        return jpeg.tobytes()
