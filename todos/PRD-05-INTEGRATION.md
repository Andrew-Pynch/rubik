# PRD-05: Multi-Capture Guided Workflow & Integration

**Status:** 🔄 ~70% Complete (T5 + T6)
**Dependencies:** PRD-04 complete
**Estimated effort:** Medium-Large

**Progress Notes (T5):**
- ✅ Session handoff structure established

**Progress Notes (T6):**
- ✅ MJPEG live streaming endpoint (`/stream`)
- ✅ HSV offset sliders in UI for color tuning
- ✅ Grid lines overlay on debug view
- ✅ `run.sh` startup script with auto-reload
- ✅ Sticky header UI with controls
- ✅ Capture button and `/capture` endpoint
- ✅ `/reset` and `/session` endpoints
- ✅ CaptureSession class with multi-capture state
- ✅ Face identification by center color
- ✅ Progress UI (X/6 faces captured)
- ✅ Rotation hints
- ✅ auto_match.py for 3D orientation
- 🔄 3D mapping mismatch (grid indexing inconsistent)

**Remaining Work:**
1. Fix 3D cube sticker positions to match debug.jpg
2. Solver integration (Kociemba)
3. Solution animation playback

## Goal

Enable capturing all 6 cube faces through a guided multi-capture workflow, then integrate with the Kociemba solver.

## User Story

As a user, I want to place my Rubik's cube in any orientation, capture the visible faces, then have the system guide me through rotating and capturing the remaining faces until the complete cube state is known and I can solve it.

## Part 1: Multi-Capture Workflow

### 1.1 Web UI Capture Controls
- Add "Capture" button to web UI status bar
- Trigger pipeline.py execution from browser via WebSocket/API
- Show capture status and results in real-time

### 1.2 Face Identification by Center Color
Use center sticker color to identify which face is being viewed:
| Center Color | Face |
|--------------|------|
| White | U (Up) |
| Yellow | D (Down) |
| Red | F (Front) |
| Orange | B (Back) |
| Blue | R (Right) |
| Green | L (Left) |

### 1.3 Multi-Capture State Accumulation
- Store partial cube state across captures in `output/accumulated_state.json`
- Merge new face detections with existing state
- Handle conflicts (same face detected twice)
- Track captured vs. missing faces

### 1.4 Guided Workflow UI
- Show which faces are still needed (progress: 3/6 faces)
- Suggest rotation instructions for next capture
- Visual indicator on 3D cube (gray = uncaptured)
- "Complete" state when all 6 faces detected

### 1.5 Cube State Model Updates
Extend `CubeState` class:
```python
class CubeState:
    def merge_capture(self, new_faces: dict) -> None:
        """Merge newly detected faces into accumulated state."""

    def get_missing_faces(self) -> list[str]:
        """Return list of faces not yet captured."""

    def is_complete(self) -> bool:
        """True if all 6 faces captured."""

    def get_rotation_hint(self) -> str:
        """Suggest how to rotate cube to capture missing faces."""
```

## Part 2: Solver Integration (after multi-capture works)

### 2.1 Kociemba Solver
```python
import kociemba

def solve(cube_state: CubeState) -> list[str]:
    """Return solution moves for complete cube state."""
    if not cube_state.is_complete():
        raise ValueError("Need all 6 faces")
    return kociemba.solve(cube_state.to_kociemba()).split()
```

### 2.2 UI Additions
- "Solve" button (enabled when all 6 faces captured)
- Solution move list display
- Animation playback controls (Play/Step/Reset/Speed)

### 2.3 Solution Animation
In `cube3d.js`:
- `playSolution(moves)` - animate move sequence
- `animateMove(move)` - rotate layer for single move
- Playback controls integration

## Files to Modify

| File | Changes |
|------|---------|
| `server.py` | Add `/api/capture` endpoint |
| `pipeline.py` | Return detection results, identify faces by center |
| `cube_model.py` | Multi-capture state management |
| `static/index.html` | Capture button, progress display |
| `static/app.js` | Capture triggering, state accumulation |
| `static/cube3d.js` | Partial state display, solution animation |
| `solver.py` | New file for Kociemba integration |

## Acceptance Criteria

### Multi-Capture
- [ ] User can trigger capture from web UI button
- [ ] System identifies faces by center sticker color
- [ ] State accumulates across multiple captures
- [ ] UI shows which faces are missing (e.g., "3/6 captured")
- [ ] UI provides rotation guidance
- [ ] 3D cube shows gray for uncaptured faces
- [ ] Works regardless of initial cube orientation

### Solver
- [ ] "Solve" button enabled when 6/6 faces captured
- [ ] Solver returns valid solution
- [ ] Solution displays as move list
- [ ] Solution animates on 3D cube
- [ ] Playback controls work

## Technical Notes

- WebSocket already exists at `/ws` - use for capture notifications
- Face identification: sample center sticker (position [1][1]) color
- Standard color mapping assumes standard cube (white opposite yellow, etc.)
