#!/usr/bin/env python3
"""FastAPI web server with WebSocket for live CV debugging."""
from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# Paths
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
STATIC_DIR = BASE_DIR / "static"

# WebSocket client management
connected_clients: Set[WebSocket] = set()

# Debounce settings
DEBOUNCE_MS = 100
last_broadcast_time = 0.0
pending_broadcast = False


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
