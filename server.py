#!/usr/bin/env python3
"""FastAPI web server with WebSocket for live CV debugging."""
from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Set

import cv2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from capture_session import CaptureSession
from pipeline import detect_current_frame, detect_from_frames

# Shared frame buffer for stream -> capture
import threading
_stream_lock = threading.Lock()
_stream_frame: tuple | None = None  # (bgr, hsv) or None when stream not running

# Paths
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
STATIC_DIR = BASE_DIR / "static"

# WebSocket client management
connected_clients: Set[WebSocket] = set()

# Multi-capture session (in-memory only)
capture_session = CaptureSession()

# Debounce settings
DEBOUNCE_MS = 100
last_broadcast_time = 0.0
pending_broadcast = False

# Global HSV offsets (applied to all color classifications)
hsv_offsets = {'h': 0, 's': 0, 'v': 0}


class OutputWatcher(FileSystemEventHandler):
    """Watch output directory for changes and trigger broadcasts."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    def on_modified(self, event):
        if event.is_directory:
            return
        # Schedule broadcast in the event loop
        asyncio.run_coroutine_threadsafe(schedule_broadcast(), self.loop)

    def on_created(self, event):
        if event.is_directory:
            return
        asyncio.run_coroutine_threadsafe(schedule_broadcast(), self.loop)


async def schedule_broadcast():
    """Schedule a debounced broadcast to all clients."""
    global last_broadcast_time, pending_broadcast

    current_time = time.time() * 1000  # Convert to milliseconds
    time_since_last = current_time - last_broadcast_time

    if time_since_last >= DEBOUNCE_MS:
        # Enough time has passed, broadcast immediately
        await broadcast_update()
    elif not pending_broadcast:
        # Schedule a delayed broadcast
        pending_broadcast = True
        delay = (DEBOUNCE_MS - time_since_last) / 1000  # Convert to seconds
        await asyncio.sleep(delay)
        pending_broadcast = False
        await broadcast_update()


async def broadcast_update():
    """Send update message to all connected WebSocket clients."""
    global last_broadcast_time

    if not connected_clients:
        return

    last_broadcast_time = time.time() * 1000
    message = {"type": "update", "timestamp": int(last_broadcast_time)}

    # Send to all clients, removing disconnected ones
    disconnected = set()
    for client in connected_clients:
        try:
            await client.send_json(message)
        except Exception:
            disconnected.add(client)

    connected_clients.difference_update(disconnected)


# File watcher setup
observer: Observer | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage file watcher lifecycle."""
    global observer

    # Start file watcher
    loop = asyncio.get_event_loop()
    event_handler = OutputWatcher(loop)
    observer = Observer()
    observer.schedule(event_handler, str(OUTPUT_DIR), recursive=False)
    observer.start()
    print(f"Watching {OUTPUT_DIR} for changes...")

    yield

    # Stop file watcher
    if observer:
        observer.stop()
        observer.join()


# FastAPI app
app = FastAPI(title="Rubik's Cube CV Debugger", lifespan=lifespan)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main debugger page."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>Rubik's Cube CV Debugger</h1><p>static/index.html not found</p>")


@app.get("/output/{filename}")
async def get_output_file(filename: str):
    """Serve files from the output directory."""
    file_path = OUTPUT_DIR / filename
    if file_path.exists() and file_path.is_file():
        # Determine media type
        suffix = file_path.suffix.lower()
        media_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".json": "application/json",
        }
        media_type = media_types.get(suffix, "application/octet-stream")
        return FileResponse(file_path, media_type=media_type)
    return {"error": "File not found"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await websocket.accept()
    connected_clients.add(websocket)
    print(f"Client connected. Total clients: {len(connected_clients)}")

    try:
        # Send initial update
        await websocket.send_json({"type": "connected", "timestamp": int(time.time() * 1000)})

        # Keep connection alive and handle incoming messages
        while True:
            # Wait for any message (ping/pong or close)
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_json({"type": "ping"})

    except WebSocketDisconnect:
        pass
    finally:
        connected_clients.discard(websocket)
        print(f"Client disconnected. Total clients: {len(connected_clients)}")


class CalibrationData(BaseModel):
    """Calibration data from the web UI."""
    vertices: dict[str, list[int]]
    face_polygons: dict[str, list[list[int]]]


@app.post("/calibrate")
async def save_calibration(data: CalibrationData):
    """Save face calibration data to calibration.json."""
    calibration_path = OUTPUT_DIR / "calibration.json"

    calibration = {
        "vertices": data.vertices,
        "face_polygons": data.face_polygons,
    }

    with open(calibration_path, 'w') as f:
        json.dump(calibration, f, indent=2)

    print(f"Calibration saved to {calibration_path}")
    return {"status": "ok", "path": str(calibration_path)}


@app.post("/save-calibration-defaults")
async def save_calibration_defaults():
    """Copy current calibration to defaults folder."""
    import shutil

    current = OUTPUT_DIR / "calibration.json"
    defaults_dir = BASE_DIR / "defaults"
    defaults_path = defaults_dir / "calibration.json"

    if not current.exists():
        return {"error": "No calibration exists to save"}

    defaults_dir.mkdir(exist_ok=True)

    # Copy current calibration to defaults
    shutil.copy(current, defaults_path)

    print(f"Calibration defaults saved to {defaults_path}")
    return {"status": "ok", "message": "Calibration saved as default"}


def get_current_frame():
    """Get current frame - from stream buffer if available, otherwise fresh capture."""
    global _stream_frame

    # Try stream buffer first (instant if stream is running)
    with _stream_lock:
        if _stream_frame is not None:
            return _stream_frame

    # No stream running, do fresh capture
    from pipeline import capture_frame, preprocess
    frame = capture_frame()
    if frame is None:
        return None
    return preprocess(frame)


@app.post("/capture")
async def trigger_capture():
    """Trigger pipeline capture and merge into session state."""
    try:
        # Get frame from stream buffer or fresh capture
        frame_result = await asyncio.to_thread(get_current_frame)
        if frame_result is None:
            return {
                "success": False,
                "error": "Failed to capture frame",
                "captured": capture_session.get_captured_faces(),
                "missing": capture_session.get_missing_faces(),
                "progress": {"count": len(capture_session.get_captured_faces()), "total": 6},
                "is_complete": capture_session.is_complete,
                "hint": capture_session.get_rotation_hint(),
            }

        bgr, hsv = frame_result
        # Run detection on the frame
        detected = await asyncio.to_thread(detect_from_frames, bgr, hsv)
        if detected is None:
            return {
                "success": False,
                "error": "Capture or detection failed",
                "captured": capture_session.get_captured_faces(),
                "missing": capture_session.get_missing_faces(),
                "progress": {"count": len(capture_session.get_captured_faces()), "total": 6},
                "is_complete": capture_session.is_complete,
                "hint": capture_session.get_rotation_hint(),
            }

        # Process through session (identifies faces by center color)
        result = capture_session.process_capture(detected)

        # Save accumulated state to state.json for 3D visualization
        cube_state = capture_session.to_cube_state()
        state_path = OUTPUT_DIR / "state.json"
        with open(state_path, 'w') as f:
            json.dump(cube_state.to_json(), f, indent=2)

        # Broadcast update to trigger UI refresh
        await schedule_broadcast()

        return result

    except Exception as e:
        print(f"Capture error: {e}")
        return {
            "success": False,
            "error": str(e),
            "captured": capture_session.get_captured_faces(),
            "missing": capture_session.get_missing_faces(),
            "progress": {"count": len(capture_session.get_captured_faces()), "total": 6},
            "is_complete": capture_session.is_complete,
            "hint": capture_session.get_rotation_hint(),
        }


@app.post("/reset")
async def reset_session():
    """Reset the capture session."""
    capture_session.reset()

    # Clear state.json
    state_path = OUTPUT_DIR / "state.json"
    if state_path.exists():
        state_path.unlink()

    # Broadcast update
    await schedule_broadcast()

    return {
        "status": "ok",
        "captured": [],
        "missing": ["U", "D", "F", "B", "L", "R"],
        "progress": {"count": 0, "total": 6},
        "is_complete": False,
        "hint": capture_session.get_rotation_hint(),
    }


@app.get("/session")
async def get_session_state():
    """Get current capture session state."""
    return capture_session.to_json()


@app.get("/debug/hsv")
async def get_hsv_samples():
    """Sample HSV values at face polygon centers for color calibration."""
    import numpy as np
    from pipeline import capture_frame, preprocess
    from config import load_face_polygons

    frame = capture_frame()
    if frame is None:
        return {"error": "Failed to capture frame"}

    bgr, hsv = preprocess(frame)
    polygons = load_face_polygons()

    if not polygons:
        return {"error": "No calibration found"}

    samples = {}
    for face, polygon in polygons.items():
        # Get center point of polygon
        cx = sum(p[0] for p in polygon) // 4
        cy = sum(p[1] for p in polygon) // 4

        # Sample 15x15 region around center
        y1, y2 = max(0, cy - 7), min(hsv.shape[0], cy + 8)
        x1, x2 = max(0, cx - 7), min(hsv.shape[1], cx + 8)
        region = hsv[y1:y2, x1:x2]

        if region.size > 0:
            h = float(np.median(region[:, :, 0]))
            s = float(np.median(region[:, :, 1]))
            v = float(np.median(region[:, :, 2]))
            samples[face] = {'h': round(h, 1), 's': round(s, 1), 'v': round(v, 1)}

    return {"samples": samples, "timestamp": time.time()}


@app.get("/debug/state")
async def get_debug_state():
    """Get full debug state including raw detection and session info."""
    from pipeline import detect_current_frame

    detected = detect_current_frame()

    return {
        "raw_detection": detected,  # What pipeline detected (positional: U, F, R)
        "session": capture_session.to_json(),
        "timestamp": time.time(),
    }


# ============================================
# Real-time MJPEG Streaming
# ============================================

def generate_stream_frames():
    """Generate MJPEG frames with detection overlay - no artificial delay."""
    global _stream_frame
    from pipeline import capture_frame, preprocess, process_frame_for_stream

    while True:
        frame = capture_frame()
        if frame is None:
            time.sleep(0.05)  # Brief wait only on capture failure
            continue

        bgr, hsv = preprocess(frame)

        # Store frame for capture endpoint to use
        with _stream_lock:
            _stream_frame = (bgr.copy(), hsv.copy())

        # Run detection and draw overlay
        debug_frame = process_frame_for_stream(bgr, hsv, hsv_offsets)

        # Encode as JPEG
        _, jpeg = cv2.imencode('.jpg', debug_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        # No sleep - run as fast as capture + processing allows


@app.get("/stream")
async def video_stream():
    """MJPEG stream with pipeline overlays - runs as fast as possible."""
    return StreamingResponse(
        generate_stream_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


# ============================================
# HSV Offset Settings
# ============================================

@app.get("/settings/hsv")
async def get_hsv_offsets():
    """Get current HSV offset values."""
    return hsv_offsets


@app.post("/settings/hsv")
async def update_hsv_offsets(data: dict):
    """Update global HSV offsets."""
    global hsv_offsets
    hsv_offsets = {
        'h': int(data.get('h', 0)),  # -30 to +30
        's': int(data.get('s', 0)),  # -50 to +50
        'v': int(data.get('v', 0)),  # -50 to +50
    }
    return {"status": "ok", "offsets": hsv_offsets}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
