"""
LUNARIS Privacy & Redaction Engine
Blurs faces and vehicle license plates before storing evidence to protect citizen PII.
"""

import logging

logger = logging.getLogger("lunaris.privacy")

try:
    import cv2
    import numpy as np
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    plate_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_russian_plate_number.xml")
    CV2_AVAILABLE = True
except Exception:
    CV2_AVAILABLE = False
    face_cascade = None
    plate_cascade = None

def redact_sensitive_pii(image_bgr):
    """
    Applies Gaussian blur to any detected human faces or license plates in the image.
    Preserves road surface defects while obscuring identifying features.
    """
    if not CV2_AVAILABLE or image_bgr is None:
        return image_bgr

    try:
        redacted = image_bgr.copy()
        gray = cv2.cvtColor(redacted, cv2.COLOR_BGR2GRAY)

        # 1. Detect and Blur Human Faces
        if face_cascade is not None:
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(24, 24))
            for (x, y, w, h) in faces:
                x1, y1 = max(0, x - 5), max(0, y - 5)
                x2, y2 = min(redacted.shape[1], x + w + 5), min(redacted.shape[0], y + h + 5)
                roi = redacted[y1:y2, x1:x2]
                blurred = cv2.GaussianBlur(roi, (51, 51), 30)
                redacted[y1:y2, x1:x2] = blurred
                cv2.rectangle(redacted, (x1, y1), (x2, y2), (0, 165, 255), 1)

        # 2. Detect and Blur Vehicle Number Plates
        if plate_cascade is not None:
            plates = plate_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(30, 15))
            for (x, y, w, h) in plates:
                roi = redacted[y:y+h, x:x+w]
                blurred = cv2.GaussianBlur(roi, (35, 35), 20)
                redacted[y:y+h, x:x+w] = blurred
                cv2.rectangle(redacted, (x, y), (x + w, y + h), (0, 200, 255), 1)

        return redacted
    except Exception as e:
        logger.debug(f"Redaction processing note: {e}")
        return image_bgr
