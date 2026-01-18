# T6 Handoff: Streaming & Debug Improvements

## Completed This Session

### 1. MJPEG Live Streaming (`/stream` endpoint)
- Added `generate_stream_frames()` in `server.py` that captures frames, runs pipeline, and yields MJPEG
- No artificial delay - streams as fast as possible per user preference
- Toggle button in UI switches between live stream and static debug.jpg

### 2. Grid Lines on Debug Overlay
- Added `draw_grid_lines()` in `pipeline.py` that draws perspective-correct yellow lines
- Created `grid_edge_point()` function (separate from `perspective_grid_point()`) that maps raw grid coordinates 0-3 without the +0.5 cell-center offset
- Lines show the inner edges between stickers (2 horizontal + 2 vertical per face)

### 3. HSV Offset Sliders
- Global HSV offsets stored in `server.py` (`hsv_offsets` dict)
- `/settings/hsv` GET/POST endpoints for reading/updating offsets
- Sliders in UI overlay: Hue ±30, Saturation ±50, Value ±50
- `classify_color_with_offsets()` applies offsets before color classification

### 4. UI Improvements
- Sticky header (navbar-style) with controls
- Stream toggle button with live badge indicator
- HSV settings panel (toggle via ⚙ button)

### 5. run.sh Script
- Kills any existing process on port 8000
- Starts uvicorn with `--reload` for auto-restart on file changes

## Known Issues From Screenshots

### Issue 1: Debug vs 3D View Position Mismatch
**Observed**: User reported that a sticker missing in the debug image (top-middle white) showed up as a different missing sticker in the 3D view (edge between right/red faces).

**Root Cause**: The mapping between grid positions in `pipeline.py` detection and face positions in `cube3d.js` rendering is inconsistent. The 3D grid mapping doesn't match the 2D debug overlay positions.

**Location**: `cube3d.js` face mapping logic needs to match `pipeline.py` grid ordering.

### Issue 2: Inconsistent Detection Under Same Lighting
**Observed**: Screenshots showed color detection giving different results for the same physical setup between captures.

**Possible Causes**:
- Single-point HSV sampling is sensitive to noise/glare
- Auto-exposure on camera causing subtle brightness shifts
- Edge cases in HSV thresholds (orange/red overlap, green detection)

**Fix Needed**: Multi-point sampling within each sticker cell, possibly with outlier rejection.

### Issue 3: Grid Lines Initially Wrong
**Fixed**: Original implementation used `perspective_grid_point()` which adds +0.5 offset for cell centers. Created separate `grid_edge_point()` without offset for edge lines.

## Pending Tasks

1. **Fix 3D cube grid mapping** (`cube3d.js`) - Align face/sticker positions with debug overlay
2. **Improve detection robustness** - Multi-point sampling per sticker, outlier rejection

## Files Modified

- `server.py` - Streaming endpoint, HSV settings
- `pipeline.py` - `process_frame_for_stream()`, `draw_grid_lines()`, `grid_edge_point()`, `classify_color_with_offsets()`
- `static/index.html` - Stream button, HSV panel
- `static/app.js` - Stream toggle, slider handlers
- `static/style.css` - Sticky header, HSV overlay, stream badge
- `run.sh` (new) - Server startup script

## How to Test

```bash
./run.sh
# Open http://localhost:8000
# Click "▶ Live Stream" to see real-time detection
# Click "⚙ HSV" to adjust color sensitivity
# Watch grid lines align with sticker edges
```
