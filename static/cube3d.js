/**
 * Three.js 3D Rubik's Cube Visualization
 *
 * Realistic cube with black plastic cubies and raised colored stickers.
 * Integrates with the CV pipeline via state.json updates.
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// ============================================
// Constants
// ============================================

const CUBIE_SIZE = 0.95;      // Size of each cubie (gap = 1 - 0.95 = 0.05)
const STICKER_SIZE = 0.85;    // Sticker slightly smaller than cubie face
const STICKER_DEPTH = 0.02;   // How much sticker is raised

// Color mapping from state.json letters to hex colors
const COLOR_MAP = {
    'W': 0xffffff,  // White
    'Y': 0xffdd00,  // Yellow
    'O': 0xff8800,  // Orange
    'R': 0xee0000,  // Red
    'G': 0x00bb00,  // Green
    'B': 0x0066ff,  // Blue
    '?': 0x404040,  // Unknown (dark gray)
};

// Face configuration: which direction each face points
const FACE_CONFIG = {
    'U': { axis: 'y', value: 1,  rotation: [-Math.PI/2, 0, 0] },
    'D': { axis: 'y', value: -1, rotation: [Math.PI/2, 0, 0] },
    'R': { axis: 'x', value: 1,  rotation: [0, Math.PI/2, 0] },
    'L': { axis: 'x', value: -1, rotation: [0, -Math.PI/2, 0] },
    'F': { axis: 'z', value: 1,  rotation: [0, 0, 0] },
    'B': { axis: 'z', value: -1, rotation: [0, Math.PI, 0] },
};

// ============================================
// Module State
// ============================================

let scene, camera, renderer, controls;
let container;
let stickers = {};  // { 'U': [[mesh, mesh, mesh], ...], ... }
let animationId;
let resizeObserver;

// ============================================
// Materials
// ============================================

// Black plastic for cubie bodies
const cubieMaterial = new THREE.MeshStandardMaterial({
    color: 0x111111,
    roughness: 0.4,
    metalness: 0.0,
});

// Create sticker materials (shared across all stickers of same color)
const stickerMaterials = {};
for (const [letter, color] of Object.entries(COLOR_MAP)) {
    stickerMaterials[letter] = new THREE.MeshStandardMaterial({
        color: color,
        roughness: 0.3,
        metalness: 0.0,
    });
}

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
    container.innerHTML = '';  // Clear placeholder

    try {
        console.log('cube3d: Creating scene...');
        createScene();
        console.log('cube3d: Creating lighting...');
        createLighting();
        console.log('cube3d: Creating cube...');
        createCube();
        console.log('cube3d: Setting up controls...');
        setupControls();
        console.log('cube3d: Setting up resize observer...');
        setupResizeObserver();
        console.log('cube3d: Starting animation loop...');
        animate();
        console.log('cube3d: Initialization complete!');
        return true;
    } catch (error) {
        console.error('cube3d: Failed to initialize:', error);
        console.error('cube3d: Stack trace:', error.stack);
        container.innerHTML = '<p style="color: #f44336; padding: 20px;">3D visualization failed to load: ' + error.message + '</p>';
        return false;
    }
}

function createScene() {
    // Ensure container has dimensions (use parent or fallback)
    let width = container.clientWidth;
    let height = container.clientHeight;

    // If container has no size yet, use reasonable defaults
    if (width < 10) width = 300;
    if (height < 10) height = 300;

    // Scene
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1a1a1a);

    // Camera positioned to see U, F, R faces (matching physical camera view)
    // Physical camera sees: U (top/white), F (front/red), R (right/blue)
    // Position camera in front-right-above to see corner where these three faces meet
    camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
    camera.position.set(4, 4, 4);  // Front-right-above corner view
    camera.lookAt(0, 0, 0);

    // Renderer
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);
}

function createLighting() {
    // Ambient light for base visibility
    const ambient = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambient);

    // Key light (main, from upper-front-left)
    const keyLight = new THREE.DirectionalLight(0xffffff, 0.8);
    keyLight.position.set(-3, 5, 4);
    scene.add(keyLight);

    // Fill light (softer, from right)
    const fillLight = new THREE.DirectionalLight(0xffffff, 0.3);
    fillLight.position.set(4, 2, -2);
    scene.add(fillLight);

    // Rim light (back lighting for depth)
    const rimLight = new THREE.DirectionalLight(0xffffff, 0.2);
    rimLight.position.set(0, -2, -4);
    scene.add(rimLight);
}

function createCube() {
    // Create 27 cubies in a 3x3x3 grid
    for (let x = -1; x <= 1; x++) {
        for (let y = -1; y <= 1; y++) {
            for (let z = -1; z <= 1; z++) {
                createCubie(x, y, z);
            }
        }
    }

    // Initialize sticker tracking
    for (const faceName of Object.keys(FACE_CONFIG)) {
        stickers[faceName] = [];
        for (let row = 0; row < 3; row++) {
            stickers[faceName].push([null, null, null]);
        }
    }

    // Create stickers on outer faces
    createFaceStickers('U');
    createFaceStickers('D');
    createFaceStickers('L');
    createFaceStickers('R');
    createFaceStickers('F');
    createFaceStickers('B');
}

function createCubie(x, y, z) {
    const geometry = new THREE.BoxGeometry(CUBIE_SIZE, CUBIE_SIZE, CUBIE_SIZE);
    const mesh = new THREE.Mesh(geometry, cubieMaterial);
    mesh.position.set(x, y, z);
    scene.add(mesh);
}

function createFaceStickers(faceName) {
    const config = FACE_CONFIG[faceName];
    const geometry = new THREE.PlaneGeometry(STICKER_SIZE, STICKER_SIZE);

    for (let row = 0; row < 3; row++) {
        for (let col = 0; col < 3; col++) {
            // Calculate cubie position for this sticker
            const cubiePos = getCubiePosition(faceName, row, col);

            // Create sticker mesh
            const mesh = new THREE.Mesh(geometry, stickerMaterials['?'].clone());

            // Position sticker on the outer face of the cubie
            const offset = (CUBIE_SIZE / 2) + STICKER_DEPTH;

            if (config.axis === 'y') {
                mesh.position.set(
                    cubiePos.x,
                    cubiePos.y + (config.value * offset),
                    cubiePos.z
                );
            } else if (config.axis === 'x') {
                mesh.position.set(
                    cubiePos.x + (config.value * offset),
                    cubiePos.y,
                    cubiePos.z
                );
            } else {  // z
                mesh.position.set(
                    cubiePos.x,
                    cubiePos.y,
                    cubiePos.z + (config.value * offset)
                );
            }

            // Rotate sticker to face outward
            mesh.rotation.set(...config.rotation);

            scene.add(mesh);
            stickers[faceName][row][col] = mesh;
        }
    }
}

function getCubiePosition(faceName, row, col) {
    // Convert (row, col) grid position to (x, y, z) cubie coordinates
    // row 0 = top/back, row 2 = bottom/front
    // col 0 = left, col 2 = right

    const config = FACE_CONFIG[faceName];
    let x, y, z;

    switch (faceName) {
        case 'U':  // Looking down at top face
            x = col - 1;
            y = 1;
            z = 1 - row;  // row 0 = back (z=1), row 2 = front (z=-1)
            break;
        case 'D':  // Looking up at bottom face
            x = col - 1;
            y = -1;
            z = row - 1;  // row 0 = front, row 2 = back
            break;
        case 'L':  // Looking at left face from left side
            x = -1;
            y = 1 - row;
            z = 1 - col;  // col 0 = back, col 2 = front
            break;
        case 'R':  // Looking at right face from right side
            x = 1;
            y = 1 - row;
            z = col - 1;  // col 0 = front, col 2 = back
            break;
        case 'F':  // Looking at front face
            x = col - 1;
            y = 1 - row;
            z = 1;
            break;
        case 'B':  // Looking at back face (from behind)
            x = 1 - col;  // mirrored
            y = 1 - row;
            z = -1;
            break;
        default:
            x = y = z = 0;
    }

    return { x, y, z };
}

function setupControls() {
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.minDistance = 4;
    controls.maxDistance = 12;
    controls.enablePan = false;
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
}

function animate() {
    animationId = requestAnimationFrame(animate);
    if (controls) controls.update();
    if (renderer && scene && camera) {
        renderer.render(scene, camera);
    }
}

// ============================================
// State Update
// ============================================

export function updateCubeState(stateData) {
    if (!stateData || !stateData.faces) {
        console.warn('cube3d: Invalid state data');
        return;
    }

    for (const [faceName, grid] of Object.entries(stateData.faces)) {
        if (!stickers[faceName]) continue;

        for (let row = 0; row < 3; row++) {
            for (let col = 0; col < 3; col++) {
                const mesh = stickers[faceName][row][col];
                if (!mesh) continue;

                // Get color letter (or '?' if null/undefined)
                let colorLetter = '?';
                if (grid && Array.isArray(grid[row]) && grid[row][col]) {
                    colorLetter = grid[row][col];
                }

                // Update material color
                const color = COLOR_MAP[colorLetter] ?? COLOR_MAP['?'];
                mesh.material.color.setHex(color);
            }
        }
    }
}

// ============================================
// Cleanup
// ============================================

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
    stickers = {};
}
