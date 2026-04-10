/**
 * Three.js 3D Rubik's Cube Visualization - Dual Cube Mode
 *
 * Shows two cubes side by side:
 * - Left: Estimation cube (CV detection results) with accuracy indicators
 * - Right: Ground Truth cube (manually marked expected colors)
 *
 * Both cubes rotate together via shared OrbitControls.
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// ============================================
// Constants
// ============================================

const CUBIE_SIZE = 0.95;
const STICKER_SIZE = 0.85;
const STICKER_DEPTH = 0.02;
const CUBE_OFFSET = 2.8;  // Distance from center for each cube

const COLOR_MAP = {
    'W': 0xffffff,
    'Y': 0xffdd00,
    'O': 0xff8800,
    'R': 0xee0000,
    'G': 0x00bb00,
    'B': 0x0066ff,
    '?': 0x404040,
    null: 0x303030,  // Unmarked (darker gray)
};

const FACE_CONFIG = {
    'U': { axis: 'y', value: 1,  rotation: [-Math.PI/2, 0, 0] },
    'D': { axis: 'y', value: -1, rotation: [Math.PI/2, 0, 0] },
    'R': { axis: 'x', value: 1,  rotation: [0, Math.PI/2, 0] },
    'L': { axis: 'x', value: -1, rotation: [0, -Math.PI/2, 0] },
    'F': { axis: 'z', value: 1,  rotation: [0, 0, 0] },
    'B': { axis: 'z', value: -1, rotation: [0, Math.PI, 0] },
};

const FACE_GRID_TRANSFORMS = {
    'U': { rowFlip: false, colFlip: false },
    'D': { rowFlip: false, colFlip: false },
    'F': { rowFlip: false, colFlip: false },
    'B': { rowFlip: false, colFlip: false },
    'L': { rowFlip: false, colFlip: false },
    'R': { rowFlip: false, colFlip: true },
};

// ============================================
// Module State
// ============================================

let scene, camera, renderer, controls, labelRenderer;
let container;
let animationId;
let resizeObserver;

// Dual cube state
let estimationCube = null;  // { group, stickers, indicators }
let groundTruthCube = null; // { group, stickers }

// State caching
let currentOrientations = { U: 0, F: 0, R: 0, D: 0, L: 0, B: 0 };
let lastStateData = null;
let lastGroundTruth = null;

// Materials
const cubieMaterial = new THREE.MeshStandardMaterial({
    color: 0x111111,
    roughness: 0.4,
    metalness: 0.0,
});

// ============================================
// Initialization
// ============================================

export function initCube3D(containerElement) {
    if (!containerElement) {
        console.error('cube3d: No container element provided');
        return false;
    }

    container = containerElement;
    console.log('cube3d: Container found, size:', container.clientWidth, 'x', container.clientHeight);
    container.innerHTML = '';

    try {
        createScene();
        createLighting();

        // Create dual cubes
        estimationCube = createCubeGroup(-CUBE_OFFSET, true);   // Left, with indicators
        groundTruthCube = createCubeGroup(CUBE_OFFSET, false);  // Right, no indicators

        setupControls();
        setupResizeObserver();
        animate();

        console.log('cube3d: Dual cube initialization complete!');
        return true;
    } catch (error) {
        console.error('cube3d: Failed to initialize:', error);
        container.innerHTML = '<p style="color: #f44336; padding: 20px;">3D visualization failed: ' + error.message + '</p>';
        return false;
    }
}

function createScene() {
    let width = container.clientWidth;
    let height = container.clientHeight;
    if (width < 10) width = 400;
    if (height < 10) height = 300;

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1a1a1a);

    // Camera positioned for corner-on view of both cubes
    camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
    camera.position.set(0, 6, 10);  // Higher and further back to see both cubes
    camera.lookAt(0, 0, 0);

    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    labelRenderer = new CSS2DRenderer();
    labelRenderer.setSize(width, height);
    labelRenderer.domElement.style.position = 'absolute';
    labelRenderer.domElement.style.top = '0';
    labelRenderer.domElement.style.left = '0';
    labelRenderer.domElement.style.pointerEvents = 'none';
    container.style.position = 'relative';
    container.appendChild(labelRenderer.domElement);
}

function createLighting() {
    const ambient = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambient);

    const keyLight = new THREE.DirectionalLight(0xffffff, 0.8);
    keyLight.position.set(-3, 5, 4);
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0xffffff, 0.3);
    fillLight.position.set(4, 2, -2);
    scene.add(fillLight);

    const rimLight = new THREE.DirectionalLight(0xffffff, 0.2);
    rimLight.position.set(0, -2, -4);
    scene.add(rimLight);
}

function createCubeGroup(xOffset, withIndicators) {
    const group = new THREE.Group();
    group.position.x = xOffset;

    // Create cubies within group
    for (let x = -1; x <= 1; x++) {
        for (let y = -1; y <= 1; y++) {
            for (let z = -1; z <= 1; z++) {
                const geometry = new THREE.BoxGeometry(CUBIE_SIZE, CUBIE_SIZE, CUBIE_SIZE);
                const mesh = new THREE.Mesh(geometry, cubieMaterial);
                mesh.position.set(x, y, z);
                group.add(mesh);
            }
        }
    }

    // Create stickers for each face
    const stickers = {};
    for (const faceName of Object.keys(FACE_CONFIG)) {
        stickers[faceName] = [];
        for (let row = 0; row < 3; row++) {
            stickers[faceName].push([null, null, null]);
        }
    }

    for (const faceName of Object.keys(FACE_CONFIG)) {
        createFaceStickersForGroup(group, stickers, faceName);
    }

    scene.add(group);

    // Create indicators for estimation cube only
    let indicators = null;
    if (withIndicators) {
        indicators = createIndicators(group, stickers);
    }

    return { group, stickers, indicators };
}

function createFaceStickersForGroup(group, stickers, faceName) {
    const config = FACE_CONFIG[faceName];
    const geometry = new THREE.PlaneGeometry(STICKER_SIZE, STICKER_SIZE);

    for (let row = 0; row < 3; row++) {
        for (let col = 0; col < 3; col++) {
            const cubiePos = getCubiePosition(faceName, row, col);

            // Create sticker with cloned material for individual coloring
            const material = new THREE.MeshStandardMaterial({
                color: COLOR_MAP['?'],
                roughness: 0.3,
                metalness: 0.0,
            });
            const mesh = new THREE.Mesh(geometry, material);

            const offset = (CUBIE_SIZE / 2) + STICKER_DEPTH;

            if (config.axis === 'y') {
                mesh.position.set(cubiePos.x, cubiePos.y + (config.value * offset), cubiePos.z);
            } else if (config.axis === 'x') {
                mesh.position.set(cubiePos.x + (config.value * offset), cubiePos.y, cubiePos.z);
            } else {
                mesh.position.set(cubiePos.x, cubiePos.y, cubiePos.z + (config.value * offset));
            }

            mesh.rotation.set(...config.rotation);
            group.add(mesh);
            stickers[faceName][row][col] = mesh;
        }
    }
}

function getCubiePosition(faceName, row, col) {
    let x, y, z;

    switch (faceName) {
        case 'U':
            x = col - 1;
            y = 1;
            z = row - 1;
            break;
        case 'D':
            x = col - 1;
            y = -1;
            z = row - 1;
            break;
        case 'L':
            x = -1;
            y = 1 - row;
            z = 1 - col;
            break;
        case 'R':
            x = 1;
            y = 1 - row;
            z = 1 - col;
            break;
        case 'F':
            x = col - 1;
            y = 1 - row;
            z = 1;
            break;
        case 'B':
            x = 1 - col;
            y = 1 - row;
            z = -1;
            break;
        default:
            x = y = z = 0;
    }

    return { x, y, z };
}

function createIndicators(group, stickers) {
    const indicators = {};

    for (const faceName of ['U', 'F', 'R']) {  // Only visible faces
        indicators[faceName] = [];
        for (let row = 0; row < 3; row++) {
            indicators[faceName].push([]);
            for (let col = 0; col < 3; col++) {
                const div = document.createElement('div');
                div.className = 'sticker-indicator';
                div.style.cssText = 'font-size: 16px; font-weight: bold; pointer-events: none; text-shadow: 0 0 3px black, 0 0 3px black;';

                const indicator = new CSS2DObject(div);

                // Position at sticker location
                const stickerMesh = stickers[faceName][row][col];
                if (stickerMesh) {
                    indicator.position.copy(stickerMesh.position);
                }

                indicator.visible = false;
                group.add(indicator);
                indicators[faceName][row].push(indicator);
            }
        }
    }

    return indicators;
}

function setupControls() {
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.minDistance = 8;
    controls.maxDistance = 20;
    controls.enablePan = false;
    // Constrain vertical rotation
    controls.minPolarAngle = Math.PI / 6;
    controls.maxPolarAngle = Math.PI / 2;
}

function setupResizeObserver() {
    resizeObserver = new ResizeObserver((entries) => {
        for (const entry of entries) {
            const { width, height } = entry.contentRect;
            if (width > 0 && height > 0) {
                resize(width, height);
            }
        }
    });
    resizeObserver.observe(container);
}

function resize(width, height) {
    if (!camera || !renderer) return;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
    if (labelRenderer) {
        labelRenderer.setSize(width, height);
    }
}

function animate() {
    animationId = requestAnimationFrame(animate);
    if (controls) controls.update();
    if (renderer && scene && camera) {
        renderer.render(scene, camera);
        if (labelRenderer) {
            labelRenderer.render(scene, camera);
        }
    }
}

// ============================================
// Coordinate Transforms
// ============================================

function applyFaceGridTransform(row, col, faceName) {
    const transform = FACE_GRID_TRANSFORMS[faceName];
    if (!transform) return [row, col];

    let r = row, c = col;
    if (transform.rowFlip) r = 2 - r;
    if (transform.colFlip) c = 2 - c;

    return [r, c];
}

function transformGridPosition(row, col, rotation) {
    switch (rotation) {
        case 0:   return [row, col];
        case 90:  return [2 - col, row];
        case 180: return [2 - row, 2 - col];
        case 270: return [col, 2 - row];
        default:  return [row, col];
    }
}

// ============================================
// State Updates
// ============================================

/**
 * Update estimation cube with detection state and compare to ground truth.
 */
export function updateCubeState(stateData, orientations = null) {
    if (!stateData || !stateData.faces) {
        console.warn('cube3d: Invalid state data');
        return;
    }

    if (orientations) {
        currentOrientations = { ...currentOrientations, ...orientations };
    }

    lastStateData = stateData;

    if (estimationCube) {
        applyStateToStickers(estimationCube.stickers, stateData);

        // Update indicators if we have ground truth
        if (lastGroundTruth && estimationCube.indicators) {
            updateIndicators(stateData, lastGroundTruth);
        }
    }
}

/**
 * Update ground truth cube with expected colors.
 */
export function updateGroundTruthCube(groundTruth) {
    if (!groundTruth) return;

    lastGroundTruth = groundTruth;

    if (groundTruthCube) {
        applyGroundTruthToStickers(groundTruthCube.stickers, groundTruth);
    }

    // Update indicators on estimation cube
    if (lastStateData && estimationCube && estimationCube.indicators) {
        updateIndicators(lastStateData, groundTruth);
    }
}

function applyStateToStickers(stickers, stateData) {
    const faceConfidences = stateData.face_confidences || {};
    const autoMatch = stateData.auto_match;
    const useAutoMatch = autoMatch && autoMatch.valid;

    for (const [roiFace, grid] of Object.entries(stateData.faces)) {
        if (!grid) continue;

        const actualFace = useAutoMatch && autoMatch.roi_to_face
            ? (autoMatch.roi_to_face[roiFace] || roiFace)
            : roiFace;

        if (!stickers[actualFace]) continue;

        const confGrid = faceConfidences[roiFace] || null;
        const rotation = useAutoMatch && autoMatch.face_rotations
            ? (autoMatch.face_rotations[actualFace] || 0)
            : (currentOrientations[actualFace] || 0);

        for (let row = 0; row < 3; row++) {
            for (let col = 0; col < 3; col++) {
                const mesh = stickers[actualFace][row][col];
                if (!mesh) continue;

                const [rotRow, rotCol] = transformGridPosition(row, col, rotation);
                const [srcRow, srcCol] = applyFaceGridTransform(rotRow, rotCol, actualFace);

                let colorLetter = '?';
                if (grid && Array.isArray(grid[srcRow]) && grid[srcRow][srcCol]) {
                    colorLetter = grid[srcRow][srcCol];
                }

                const color = COLOR_MAP[colorLetter] ?? COLOR_MAP['?'];
                mesh.material.color.setHex(color);

                // Confidence visualization
                let confidence = 1.0;
                if (confGrid && Array.isArray(confGrid[srcRow]) && confGrid[srcRow][srcCol] !== undefined) {
                    confidence = confGrid[srcRow][srcCol];
                }
                applyConfidenceVisualization(mesh, colorLetter, confidence);
            }
        }
    }
}

function applyGroundTruthToStickers(stickers, groundTruth) {
    for (const faceName of ['U', 'F', 'R']) {
        const grid = groundTruth[faceName];
        if (!grid || !stickers[faceName]) continue;

        for (let row = 0; row < 3; row++) {
            for (let col = 0; col < 3; col++) {
                const mesh = stickers[faceName][row][col];
                if (!mesh) continue;

                const colorLetter = grid[row]?.[col];
                const color = COLOR_MAP[colorLetter] ?? COLOR_MAP[null];
                mesh.material.color.setHex(color);
                mesh.material.transparent = colorLetter == null;
                mesh.material.opacity = colorLetter == null ? 0.3 : 1.0;
            }
        }
    }

    // Set other faces to dark (not visible in ground truth)
    for (const faceName of ['D', 'L', 'B']) {
        if (!stickers[faceName]) continue;
        for (let row = 0; row < 3; row++) {
            for (let col = 0; col < 3; col++) {
                const mesh = stickers[faceName][row][col];
                if (mesh) {
                    mesh.material.color.setHex(0x202020);
                    mesh.material.transparent = true;
                    mesh.material.opacity = 0.3;
                }
            }
        }
    }
}

function updateIndicators(stateData, groundTruth) {
    if (!estimationCube || !estimationCube.indicators) return;

    const autoMatch = stateData.auto_match;
    const useAutoMatch = autoMatch && autoMatch.valid;

    for (const faceName of ['U', 'F', 'R']) {
        const gtGrid = groundTruth[faceName];
        if (!gtGrid) continue;

        // Find which ROI maps to this face
        let roiFace = faceName;
        if (useAutoMatch && autoMatch.roi_to_face) {
            for (const [roi, face] of Object.entries(autoMatch.roi_to_face)) {
                if (face === faceName) {
                    roiFace = roi;
                    break;
                }
            }
        }

        const detGrid = stateData.faces?.[roiFace];
        const rotation = useAutoMatch && autoMatch.face_rotations
            ? (autoMatch.face_rotations[faceName] || 0)
            : (currentOrientations[faceName] || 0);

        for (let row = 0; row < 3; row++) {
            for (let col = 0; col < 3; col++) {
                const indicator = estimationCube.indicators[faceName]?.[row]?.[col];
                if (!indicator) continue;

                const gtColor = gtGrid[row]?.[col];

                // Get detected color (with transforms)
                const [rotRow, rotCol] = transformGridPosition(row, col, rotation);
                const [srcRow, srcCol] = applyFaceGridTransform(rotRow, rotCol, faceName);
                const detColor = detGrid?.[srcRow]?.[srcCol];

                const div = indicator.element;

                if (!gtColor || gtColor === null) {
                    // No ground truth for this sticker
                    indicator.visible = false;
                } else if (!detColor || detColor === '?') {
                    // Ground truth exists but no detection
                    div.textContent = '?';
                    div.style.color = '#888888';
                    indicator.visible = true;
                } else if (detColor === gtColor) {
                    // Correct
                    div.textContent = '✓';
                    div.style.color = '#00ff00';
                    indicator.visible = true;
                } else {
                    // Incorrect
                    div.textContent = '✗';
                    div.style.color = '#ff0000';
                    indicator.visible = true;
                }
            }
        }
    }
}

function applyConfidenceVisualization(mesh, colorLetter, confidence) {
    if (colorLetter === '?') {
        mesh.material.transparent = true;
        mesh.material.opacity = 0.5;
        mesh.material.emissive = new THREE.Color(0x000000);
        return;
    }

    if (confidence >= 0.7) {
        mesh.material.transparent = false;
        mesh.material.opacity = 1.0;
        mesh.material.emissive = new THREE.Color(0x000000);
        return;
    }

    if (confidence >= 0.4) {
        mesh.material.transparent = true;
        mesh.material.opacity = 0.7 + (confidence - 0.4) * 1.0;
        mesh.material.emissive = new THREE.Color(0x000000);
        return;
    }

    mesh.material.transparent = true;
    mesh.material.opacity = 0.5 + confidence * 0.5;
    const emissiveIntensity = (0.4 - confidence) * 0.15;
    mesh.material.emissive = new THREE.Color(emissiveIntensity * 2, 0, 0);
}

// ============================================
// Legacy API (for compatibility)
// ============================================

export function setOrientations(orientations) {
    currentOrientations = { ...currentOrientations, ...orientations };
    if (lastStateData) {
        updateCubeState(lastStateData);
    }
}

export function getOrientations() {
    return { ...currentOrientations };
}

// These functions operate on estimation cube for compatibility
export function highlightFace(faceName) {
    if (!estimationCube) return;

    // Clear all highlights first
    for (const face of Object.keys(estimationCube.stickers)) {
        for (let r = 0; r < 3; r++) {
            for (let c = 0; c < 3; c++) {
                const mesh = estimationCube.stickers[face]?.[r]?.[c];
                if (mesh) {
                    mesh.material.emissive.setHex(0x000000);
                }
            }
        }
    }

    // Apply highlight to selected face
    if (faceName && estimationCube.stickers[faceName]) {
        for (let r = 0; r < 3; r++) {
            for (let c = 0; c < 3; c++) {
                const mesh = estimationCube.stickers[faceName][r][c];
                if (mesh) {
                    mesh.material.emissive.setHex(0x444400);
                }
            }
        }
    }
}

export function showFaceLabels(faceName) {
    throw new Error('showFaceLabels not implemented in dual cube mode');
}

export function enableFaceClickMode(callback) {
    throw new Error('enableFaceClickMode not implemented in dual cube mode');
}

export function disableFaceClickMode() {
    // No-op: Face click mode not supported in dual cube mode
}

export function dispose() {
    if (animationId) {
        cancelAnimationFrame(animationId);
        animationId = null;
    }
    if (resizeObserver) {
        resizeObserver.disconnect();
        resizeObserver = null;
    }
    if (controls) {
        controls.dispose();
        controls = null;
    }
    if (renderer) {
        renderer.dispose();
        if (container && renderer.domElement.parentNode === container) {
            container.removeChild(renderer.domElement);
        }
        renderer = null;
    }
    scene = null;
    camera = null;
    estimationCube = null;
    groundTruthCube = null;
}
