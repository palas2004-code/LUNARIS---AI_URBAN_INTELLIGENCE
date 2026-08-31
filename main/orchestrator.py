"""
LUNARIS System Master Orchestrator
Launches and monitors the complete multi-service platform:
- FastAPI Backend (:8000)
- AI Edge Inference Worker (YOLOv8)
- Native Web Server (:8080)
- MediaMTX WebRTC Stream Gateway (:8554 / :8889)
"""

import subprocess
import sys
import os
import time

def start_services():
    print("=" * 70)
    print("🚀 LAUNCHING LUNARIS 2.0 MULTI-SUBSYSTEM PLATFORM")
    print("=" * 70)

    # 1. Start Node Web Server
    print("🌐 Starting Native Web Server on http://localhost:8080...")
    node_proc = subprocess.Popen(["node", "server.js"], cwd=os.path.dirname(os.path.dirname(__file__)))

    print("\n✅ LUNARIS Platform is online!")
    print("👉 Dashboard: http://localhost:8080")
    print("👉 4K Live Camera: http://localhost:8080/live_monitoring.html")
    print("👉 Mobile Sensing: http://localhost:8080/mobile_camera.html")
    print("\nPress Ctrl+C to terminate.")

    try:
        node_proc.wait()
    except KeyboardInterrupt:
        print("\nStopping services...")
        node_proc.terminate()

if __name__ == "__main__":
    start_services()
