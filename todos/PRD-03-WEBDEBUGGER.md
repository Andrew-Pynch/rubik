# PRD-03: FastAPI Web Debugger

**Status:** ✅ Complete (T2)
**Dependencies:** PRD-02 complete
**Estimated effort:** Medium

## Goal

Create hot-reloading web interface that displays raw frame, debug frame, and prepares for 3D cube visualization.

## Deliverables

### 1. `server.py` - FastAPI application

```python
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

app = FastAPI()

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve output images
@app.get("/output/{filename}")
async def get_output_file(filename: str):
    ...

# WebSocket for real-time updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    ...

# File watcher broadcasts updates
class OutputWatcher(FileSystemEventHandler):
    def on_modified(self, event):
        # Broadcast "update" to all WebSocket clients
        ...
```

### 2. `static/index.html` - Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Rubik's Cube CV Debugger                              [ws] │
├───────────────────┬───────────────────┬─────────────────────┤
│                   │                   │                     │
│    Raw Frame      │   Debug Frame     │    3D Cube          │
│   (output/raw)    │  (output/debug)   │   (placeholder)     │
│                   │                   │                     │
├───────────────────┴───────────────────┴─────────────────────┤
│  Status: Connected | Last update: 12:30:45                  │
└─────────────────────────────────────────────────────────────┘
```

### 3. `static/style.css` - Styling

- Dark theme (easier on eyes during development)
- 3-column grid layout
- Responsive images that maintain aspect ratio
- Status bar at bottom

### 4. `static/app.js` - WebSocket client

```javascript
// Connect to WebSocket
const ws = new WebSocket(`ws://${location.host}/ws`);

// Handle update messages
ws.onmessage = (event) => {
    if (event.data === 'update') {
        refreshImages();
    }
};

// Reload images with cache-busting
function refreshImages() {
    const timestamp = Date.now();
    document.getElementById('raw-img').src = `/output/raw.jpg?t=${timestamp}`;
    document.getElementById('debug-img').src = `/output/debug.jpg?t=${timestamp}`;
    updateStatus();
}
```

## Server Features

### File Watching
- Use `watchdog` to monitor `output/` directory
- Trigger on any file modification
- Debounce rapid changes (100ms)

### WebSocket Broadcasting
- Maintain set of connected clients
- Broadcast "update" message when files change
- Handle client disconnect gracefully

### Static File Serving
- Serve `static/` for HTML/CSS/JS
- Serve `output/` for generated images
- Set appropriate MIME types

## Running the Server

```bash
# Development with auto-reload
uvicorn server:app --reload --host 0.0.0.0 --port 8000

# Open in browser
firefox http://localhost:8000
```

## Acceptance Criteria

- [ ] `uvicorn server:app` starts server on :8000
- [ ] Browser shows 3-panel layout at http://localhost:8000
- [ ] WebSocket connection established (indicator shows "Connected")
- [ ] Running `python pipeline.py` triggers automatic image refresh
- [ ] No manual browser refresh needed
- [ ] Status bar shows last update time

## Hyprland Note

To open on workspace 0:
```bash
hyprctl dispatch workspace 0 && firefox http://localhost:8000
```

Or add window rule in hyprland.conf:
```
windowrulev2 = workspace 0, class:^(firefox)$, title:^(Rubik)
```
