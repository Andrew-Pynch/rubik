# PRD-04: Three.js 3D Visualization

**Status:** Not Started
**Dependencies:** PRD-03 complete
**Estimated effort:** Medium

## Goal

Create interactive 3D Rubik's cube visualization that displays detected cube state in real-time.

## Deliverables

### 1. `static/cube3d.js` - Three.js cube renderer

```javascript
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

class RubiksCube3D {
    constructor(container) {
        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(...);
        this.renderer = new THREE.WebGLRenderer(...);
        this.controls = new OrbitControls(...);
        this.cubies = [];  // 27 small cubes

        this.init();
    }

    init() {
        // Create 3x3x3 cube structure
        // Each cubie has up to 3 visible faces
    }

    updateState(stateJson) {
        // Map detected colors to cube faces
        // Handle partial state (only 3 faces visible)
    }

    animate() {
        requestAnimationFrame(() => this.animate());
        this.controls.update();
        this.renderer.render(this.scene, this.camera);
    }
}
```

### 2. Update `static/index.html`

```html
<!-- Add Three.js from CDN -->
<script type="importmap">
{
    "imports": {
        "three": "https://unpkg.com/three@0.160.0/build/three.module.js",
        "three/addons/": "https://unpkg.com/three@0.160.0/examples/jsm/"
    }
}
</script>

<!-- 3D container -->
<div id="cube-3d-container"></div>

<script type="module" src="/static/cube3d.js"></script>
```

### 3. Update `static/app.js`

```javascript
// Initialize 3D cube
const cube3d = new RubiksCube3D(document.getElementById('cube-3d-container'));

// On update, also refresh cube state
async function refreshImages() {
    // ... existing image refresh ...

    // Fetch and apply cube state
    const response = await fetch(`/output/state.json?t=${Date.now()}`);
    const state = await response.json();
    cube3d.updateState(state);
}
```

## 3D Cube Structure

### Cubie Layout
- 27 cubies total (3×3×3)
- Each cubie is a small cube with colored faces
- Corner cubies: 3 visible faces
- Edge cubies: 2 visible faces
- Center cubies: 1 visible face
- Core cubie: hidden

### Face Colors
```javascript
const FACE_COLORS = {
    'U': 0xFFFFFF,  // White - Up
    'D': 0xFFFF00,  // Yellow - Down
    'F': 0x00FF00,  // Green - Front
    'B': 0x0000FF,  // Blue - Back
    'L': 0xFF8000,  // Orange - Left
    'R': 0xFF0000,  // Red - Right
    'unknown': 0x808080  // Gray - undetected
};
```

### State Mapping

Camera detects 3 faces (U, L, R in current setup):
- Apply detected colors to corresponding cubie faces
- Mark undetected faces as gray
- Smooth color transitions (lerp over 200ms)

## OrbitControls

- Mouse drag to rotate view
- Scroll to zoom
- Double-click to reset view
- Damping for smooth motion

## Acceptance Criteria

- [ ] 3D Rubik's cube renders in browser
- [ ] Cube has correct structure (27 cubies, colored faces)
- [ ] OrbitControls allow rotating/zooming the view
- [ ] `updateState()` applies colors from state.json
- [ ] Detected faces show correct colors
- [ ] Undetected faces show gray
- [ ] Colors update smoothly (not jarring)
- [ ] WebSocket triggers state refresh

## References

- joews/rubik-js: Clean Three.js implementation
- irisxu02/rubik: FastAPI + Three.js example
- Three.js documentation for OrbitControls
