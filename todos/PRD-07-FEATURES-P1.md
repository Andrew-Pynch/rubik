# PRD-07: Complete Existing Features (Phase 1)

**Status:** Pending
**Dependencies:** PRD-05 (partial - multi-capture workflow infrastructure exists)
**Estimated Effort:** 5-8 hours total

## Overview

This PRD addresses three outstanding features that complete the existing Rubik's Cube CV detection pipeline:

1. **Fix 3D Mapping Mismatch** (S) - Align grid indexing between cube3d.js and pipeline.py
2. **Implement Edge Validation** (M) - Complete stubbed edge consistency checks
3. **Integrate Kociemba Solver** (M) - Add solve endpoint and UI

---

## 1.1 Fix 3D Mapping Mismatch

**Complexity:** Small (1-2 hours)

### Problem
Grid indexing in `cube3d.js` doesn't match `pipeline.py` sticker ordering. Documented in CLAUDE.md and T6-HANDOFF.md.

### Relevant Code
- `cube3d.js` lines 44-52: `FACE_GRID_TRANSFORMS` with row/col flip settings
- `cube3d.js` lines 232-270: `getCubiePosition()` for 3D coordinates
- `auto_match.py`: `CORNER_POSITIONS` for 8 cube corners
- `pipeline.py`: Grid detection coordinates

### Requirements

#### 1.1.1 Create Debug Test Harness
Create `experiments/test_3d_mapping.py`:
- Load debug.jpg and state.json from output/
- For each face (U/F/R), for each sticker (0-8):
  - Extract pixel position from debug overlay
  - Map to expected 3D grid position
  - Compare detected color with state.json
  - Output mismatches with position details

#### 1.1.2 Verify CORNER_POSITIONS
Review `auto_match.py` lines 27-36:
```python
CORNER_POSITIONS = {
    frozenset(['U', 'F', 'R']): {'U': (2, 2), 'F': (0, 2), 'R': (0, 0)},
    # ...
}
```
UFR corner should have:
- U face: position (2, 2) = bottom-right of U
- F face: position (0, 2) = top-right of F
- R face: position (0, 0) = top-left of R

#### 1.1.3 Update FACE_GRID_TRANSFORMS
Modify `static/cube3d.js` lines 44-52 based on test harness results.

#### 1.1.4 Verify getCubiePosition Mapping
Review `cube3d.js` lines 232-270:
- U face: `x = col - 1, y = 1, z = row - 1`
- F face: `x = col - 1, y = 1 - row, z = 1`
- R face: `x = 1, y = 1 - row, z = 1 - col`

### Acceptance Criteria
- [ ] Test harness identifies any remaining mismatches
- [ ] Debug.jpg sticker at [0,0] of U matches 3D cube U[0,0]
- [ ] All 27 visible stickers (3 faces x 9) map correctly

---

## 1.2 Implement Edge Validation

**Complexity:** Medium (2-3 hours)

### Problem
`capture_session.py` has `EDGE_ADJACENCIES` (lines 87-104) but validation is stubbed.

### Edge Adjacency Semantics
```python
EDGE_ADJACENCIES = {
    ('U', 'F'): [((2, 0), (0, 0)), ((2, 1), (0, 1)), ((2, 2), (0, 2))],
    # means: U[2,0] adjacent to F[0,0], etc.
}
```

**Important:** Adjacent edge stickers DON'T have the same color - they're on different pieces. Validation checks for physically impossible combinations.

### Requirements

#### 1.2.1 Add Color Validation Constants
Add to `capture_session.py`:
```python
# Opposite face colors (can't appear on same edge piece)
OPPOSITE_COLORS = {
    ('W', 'Y'), ('Y', 'W'),  # U/D
    ('R', 'O'), ('O', 'R'),  # F/B
    ('B', 'G'), ('G', 'B'),  # R/L
}

# Valid edge pieces (12 edges, each with 2 colors)
VALID_EDGES = {
    frozenset(['W', 'R']), frozenset(['W', 'O']),
    frozenset(['W', 'B']), frozenset(['W', 'G']),
    frozenset(['Y', 'R']), frozenset(['Y', 'O']),
    frozenset(['Y', 'B']), frozenset(['Y', 'G']),
    frozenset(['R', 'B']), frozenset(['R', 'G']),
    frozenset(['O', 'B']), frozenset(['O', 'G']),
}
```

#### 1.2.2 Implement Edge Validation Logic
Replace no-op in `capture_session.py:224-235`:
```python
for (f1, f2), adjacencies in self.EDGE_ADJACENCIES.items():
    f1_grid = new_faces.get(f1) or self.global_state.get(f1)
    f2_grid = new_faces.get(f2) or self.global_state.get(f2)

    if f1_grid is None or f2_grid is None:
        continue

    for (pos1, pos2) in adjacencies:
        color1 = f1_grid[pos1[0]][pos1[1]]
        color2 = f2_grid[pos2[0]][pos2[1]]

        if color1 == '?' or color2 == '?':
            continue

        if (color1, color2) in self.OPPOSITE_COLORS:
            issues.append(Inconsistency(
                face=f1,
                position=pos1,
                existing_color=color1,
                new_color=color2,
                source="edge_mismatch"
            ))
```

#### 1.2.3 Display Warnings in UI
Update `static/app.js` `triggerCapture()`:
```javascript
if (result.inconsistencies && result.inconsistencies.length > 0) {
    const edgeIssues = result.inconsistencies.filter(i => i.source === 'edge_mismatch');
    if (edgeIssues.length > 0) {
        showToast(`Warning: ${edgeIssues.length} invalid edge combinations`, 'warning');
    }
}
```

### Acceptance Criteria
- [ ] `validate_consistency()` detects impossible edge color combinations
- [ ] Inconsistency objects created with `source="edge_mismatch"`
- [ ] UI displays edge mismatch warnings
- [ ] Test: W-Y edge (impossible) shows warning

---

## 1.3 Integrate Kociemba Solver

**Complexity:** Medium (2-3 hours)

### Current State
- `kociemba` library available in requirements.txt
- `cube_model.py` has `to_kociemba()` method returning 54-char string
- No `/api/solve` endpoint or UI

### Requirements

#### 1.3.1 Create Solver Module
Create `solver.py`:
```python
"""Kociemba solver integration for Rubik's cube."""
import kociemba
from cube_model import CubeState


class SolveError(Exception):
    """Error during cube solving."""
    pass


def solve(cube_state: CubeState) -> list[str]:
    """Solve a complete cube state.

    Args:
        cube_state: CubeState with all 6 faces captured.

    Returns:
        List of move strings (e.g., ["R", "U'", "F2", ...])

    Raises:
        SolveError: If cube is incomplete or invalid.
    """
    missing = [f for f, grid in cube_state.faces.items() if grid is None]
    if missing:
        raise SolveError(f"Missing faces: {', '.join(missing)}")

    kociemba_str = cube_state.to_kociemba()
    if not kociemba_str or len(kociemba_str) != 54:
        raise SolveError("Invalid cube state")

    if '?' in kociemba_str:
        raise SolveError("Cube state contains unknown stickers")

    try:
        solution = kociemba.solve(kociemba_str)
        return solution.split() if solution else []
    except Exception as e:
        raise SolveError(f"Solver failed: {e}")
```

#### 1.3.2 Add Solve API Endpoint
Add to `server.py`:
```python
from solver import solve, SolveError

@app.post("/api/solve")
async def solve_cube():
    if not capture_session.is_complete:
        return {
            "success": False,
            "solution": None,
            "move_count": 0,
            "error": f"Missing: {', '.join(capture_session.get_missing_faces())}"
        }

    cube_state = capture_session.to_cube_state()

    try:
        moves = solve(cube_state)
        return {
            "success": True,
            "solution": moves,
            "move_count": len(moves),
            "error": None
        }
    except SolveError as e:
        return {
            "success": False,
            "solution": None,
            "move_count": 0,
            "error": str(e)
        }
```

#### 1.3.3 Add Solve Button to UI
Update `static/index.html` footer:
```html
<button id="solve-btn" class="btn btn-success btn-large" disabled>Solve</button>
```

#### 1.3.4 Add Solution Display Panel
Add to `static/index.html`:
```html
<div id="solution-panel" class="hidden">
    <h3>Solution (<span id="solution-count">0</span> moves)</h3>
    <div id="solution-moves" class="solution-moves"></div>
    <button id="solution-close" class="btn">Close</button>
</div>
```

#### 1.3.5 Implement Solve UI Logic
Add to `static/app.js`:
```javascript
const solveBtn = document.getElementById('solve-btn');

function updateSolveButton(isComplete) {
    if (solveBtn) {
        solveBtn.disabled = !isComplete;
    }
}

async function triggerSolve() {
    solveBtn.disabled = true;
    solveBtn.textContent = 'Solving...';

    try {
        const response = await fetch('/api/solve', { method: 'POST' });
        const result = await response.json();

        if (result.success) {
            displaySolution(result.solution);
            showToast(`Solved in ${result.move_count} moves!`, 'success');
        } else {
            showToast('Solve failed: ' + result.error, 'error');
        }
    } finally {
        solveBtn.disabled = false;
        solveBtn.textContent = 'Solve';
    }
}

function displaySolution(moves) {
    document.getElementById('solution-count').textContent = moves.length;
    document.getElementById('solution-moves').innerHTML =
        moves.map(m => `<span class="solution-move">${m}</span>`).join('');
    document.getElementById('solution-panel').classList.remove('hidden');
}

solveBtn?.addEventListener('click', triggerSolve);
```

### Acceptance Criteria
- [ ] `POST /api/solve` returns solution for complete valid cube
- [ ] `POST /api/solve` returns error for incomplete cube
- [ ] `POST /api/solve` returns error for invalid states
- [ ] Solve button disabled when `is_complete=false`
- [ ] Solve button enabled when all 6 faces captured
- [ ] Solution moves display in UI panel

---

## Files to Create

| File | Purpose |
|------|---------|
| `solver.py` | Kociemba solver wrapper |
| `experiments/test_3d_mapping.py` | 3D mapping verification |

## Files to Modify

| File | Changes |
|------|---------|
| `capture_session.py` | Edge validation implementation |
| `server.py` | `/api/solve` endpoint |
| `static/cube3d.js` | `FACE_GRID_TRANSFORMS` adjustments |
| `static/index.html` | Solve button, solution panel |
| `static/app.js` | Solve handler, solution display |
| `static/style.css` | Solution panel styling |
| `auto_match.py` | Verify `CORNER_POSITIONS` |

## Estimated Effort

| Feature | Complexity | Time |
|---------|------------|------|
| 1.1 3D Mapping Fix | Small | 1-2 hours |
| 1.2 Edge Validation | Medium | 2-3 hours |
| 1.3 Solver Integration | Medium | 2-3 hours |
| **Total** | | **5-8 hours** |
