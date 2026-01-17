# PRD-05: End-to-End Integration & Solver

**Status:** Not Started
**Dependencies:** PRD-04 complete
**Estimated effort:** Medium

## Goal

Polish the system, integrate Kociemba solver, add UI controls, and complete documentation.

## Deliverables

### 1. `solver.py` - Kociemba integration

```python
import kociemba
from cube_model import CubeState

def solve(cube_state: CubeState) -> list[str]:
    """
    Solve the cube and return list of moves.

    Args:
        cube_state: Current cube state (must have all 6 faces)

    Returns:
        List of moves in standard notation, e.g. ["R", "U'", "D2", "F"]

    Raises:
        ValueError: If cube state is incomplete or invalid
    """
    kociemba_string = cube_state.to_kociemba()
    solution = kociemba.solve(kociemba_string)
    return solution.split()

def validate_state(cube_state: CubeState) -> tuple[bool, str]:
    """Check if cube state is valid and complete."""
    # Each color should appear exactly 9 times
    # Each face should have 9 stickers
    # Center pieces define face colors
    ...
```

### 2. UI Additions to `static/index.html`

```html
<div class="controls">
    <button id="capture-btn">Capture</button>
    <button id="solve-btn" disabled>Solve</button>
    <span id="face-count">Faces: 3/6</span>
</div>

<div class="solution-panel">
    <h3>Solution</h3>
    <div id="move-list"></div>
    <div class="playback">
        <button id="play-btn">Play</button>
        <button id="step-btn">Step</button>
        <button id="reset-btn">Reset</button>
        <input type="range" id="speed-slider" min="0.5" max="3" step="0.5" value="1">
    </div>
</div>
```

### 3. Solution Animation in `static/cube3d.js`

```javascript
class RubiksCube3D {
    // ... existing code ...

    async playSolution(moves) {
        for (const move of moves) {
            await this.animateMove(move);
            await this.delay(500 / this.speed);
        }
    }

    animateMove(move) {
        // Parse move: face, direction, double
        // Rotate appropriate layer
        // Use TWEEN.js or manual animation
    }
}
```

### 4. API Endpoints in `server.py`

```python
@app.post("/api/capture")
async def trigger_capture():
    """Run pipeline.py to capture new frame."""
    subprocess.run(["python", "pipeline.py"])
    return {"status": "ok"}

@app.post("/api/solve")
async def solve_cube():
    """Compute solution for current cube state."""
    state = load_state_json()
    if not state.is_complete():
        return {"error": "Need all 6 faces scanned"}

    solution = solver.solve(state)
    return {"solution": solution}
```

### 5. Documentation

Update `README.md`:
- Project overview
- Setup instructions
- Usage guide
- Architecture diagram
- API reference
- Troubleshooting

## Workflow for Scanning All Faces

Since camera only sees 3 faces at a time:

1. **Initial scan**: Capture U, L, R (current orientation)
2. **Rotate cube**: User physically rotates cube in mount
3. **Second scan**: Capture D, F, B
4. **Merge states**: Combine into complete cube state
5. **Solve**: Generate and display solution

### State Merging

```python
def merge_scans(scan1: CubeState, scan2: CubeState) -> CubeState:
    """Combine two partial scans into complete state."""
    merged = CubeState()
    for face in ['U', 'D', 'L', 'R', 'F', 'B']:
        if scan1.faces[face] is not None:
            merged.faces[face] = scan1.faces[face]
        elif scan2.faces[face] is not None:
            merged.faces[face] = scan2.faces[face]
    return merged
```

## Acceptance Criteria

- [ ] Can scan all 6 faces (with cube rotation)
- [ ] State persists between captures
- [ ] "Solve" button enabled when all faces scanned
- [ ] Solver returns valid solution
- [ ] Solution displays as move list
- [ ] Solution animates on 3D cube
- [ ] Playback controls work (play/pause/step/speed)
- [ ] README fully documents the project

## Performance Targets

- Frame capture: <500ms
- CV processing: <200ms
- Solver: <100ms
- Animation: 60fps

## Future Enhancements (Out of Scope)

- Automatic cube rotation detection
- Multi-angle camera setup
- Mobile app
- Bluetooth cube integration
