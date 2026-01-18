# T4 Handoff Prompt - Fix 3D Cube Face Orientation

## Project Location
~/personal/rubik

## Current State

### What's Working
- **Detection Pipeline**: 100% accurate (27/27 stickers)
  - Grid-based sampling works for stickerless cubes
  - Majority voting fixes center logo detection
  - Run: `.venv/bin/python pipeline.py`

- **Web Debugger**: Running at localhost:8000
  - WebSocket auto-refresh
  - Calibration UI
  - Debug overlay with grid sampling points

- **3D Cube**: Renders with Three.js, updates from state.json
  - But face orientation is WRONG (see below)

### The Problem

**The 3D cube shows L (red) and R (blue) as OPPOSITE faces, but in the camera view they are ADJACENT faces that share an edge.**

Looking at the debug image:
```
        [U - White]
           /\
          /  \
    [L-Red]  [R-Blue]
         \  /
          \/
```

The camera sees THREE faces meeting at a corner vertex. In standard Rubik's cube notation, L and R are opposite faces and can NEVER share an edge. But in our camera view, the "L" and "R" labeled faces DO share an edge.

**Root Cause**: The CV system labels faces by their CAMERA POSITION (left side = L, right side = R), not by standard Rubik's cube notation. The actual cube faces visible are likely U, F, R or similar adjacent triplet.

### What Needs to Be Fixed

The 3D cube visualization (`static/cube3d.js`) needs to map the CV face labels to 3D positions that match the camera view:

**Option 1: Remap face positions**
- CV "U" → 3D top face (correct)
- CV "L" → 3D front-left face (NOT standard L position)
- CV "R" → 3D front-right face (adjacent to "L")

**Option 2: Use visual-based positioning**
Instead of using standard cube notation in 3D, position faces based on where they appear:
- Create geometry where U, "L", "R" all meet at a visible corner
- Camera views this corner from above

### Key Files

| File | Purpose |
|------|---------|
| `static/cube3d.js` | Three.js 3D cube - **NEEDS FIXING** |
| `pipeline.py` | CV detection - working |
| `output/state.json` | Detection output - correct |
| `output/debug.jpg` | Visual reference for face positions |

### Current 3D Cube Structure (cube3d.js)

```javascript
// Current face config - uses standard notation (WRONG for our case)
const FACE_CONFIG = {
    'U': { axis: 'y', value: 1, ... },   // Top
    'D': { axis: 'y', value: -1, ... },  // Bottom
    'R': { axis: 'x', value: 1, ... },   // Right (opposite of L!)
    'L': { axis: 'x', value: -1, ... },  // Left (opposite of R!)
    'F': { axis: 'z', value: 1, ... },   // Front
    'B': { axis: 'z', value: -1, ... },  // Back
};
```

This creates L and R as opposite faces. Need to restructure so CV labels map to adjacent 3D faces.

### Verification

When fixed, the 3D cube should:
1. Show white (U) on top
2. Show red ("L") and blue ("R") meeting at an edge, both visible
3. Match the orientation in debug.jpg
4. Update correctly when running `python pipeline.py`

### Physical Camera Setup (from CLAUDE.md)
- Camera views cube from above at 53.5° pitch
- Sees U (top/white), L (left/red), R (right/blue)
- These three faces share a common vertex in the camera view

### Reference
- `output/debug.jpg` - Shows correct face layout
- `output/calibration.json` - Has the face polygon coordinates
- joews/rubik-js on GitHub - Reference Three.js implementation
