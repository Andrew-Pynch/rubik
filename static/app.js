// WebSocket client for Rubik's Cube CV Debugger

import { initCube3D, updateCubeState } from './cube3d.js';

const WS_URL = `ws://${location.host}/ws`;
const RECONNECT_BASE_DELAY = 1000;
const RECONNECT_MAX_DELAY = 30000;

let ws = null;
let reconnectAttempts = 0;
let reconnectTimeout = null;

// DOM elements
const statusIndicator = document.getElementById('status-indicator');
const statusText = document.getElementById('status-text');
const connectionState = document.getElementById('connection-state');
const lastUpdateEl = document.getElementById('last-update');
const rawImg = document.getElementById('raw-img');
const debugImg = document.getElementById('debug-img');

// Calibration elements
const calibrateBtn = document.getElementById('calibrate-btn');
const calibrationOverlay = document.getElementById('calibration-overlay');
const calibrationCanvas = document.getElementById('calibration-canvas');
const rawContainer = document.getElementById('raw-container');
const calibrationReset = document.getElementById('calibration-reset');
const calibrationSave = document.getElementById('calibration-save');
const calibrationCancel = document.getElementById('calibration-cancel');
const vertexElements = document.querySelectorAll('.vertex');

// Calibration state
let calibrationMode = false;
let calibrationVertices = []; // Array of [x, y] in image coordinates
const VERTEX_NAMES = [
    'u_top_left',
    'u_top_right',
    'l_top_left',
    'center',
    'l_bottom_left',
    'bottom_center',
    'r_top_right',
    'r_bottom_right'
];

function connect() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        return;
    }

    setConnectionStatus('connecting');

    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        console.log('WebSocket connected');
        reconnectAttempts = 0;
        setConnectionStatus('connected');
        refreshImages();
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleMessage(data);
        } catch (e) {
            console.error('Failed to parse message:', e);
        }
    };

    ws.onclose = () => {
        console.log('WebSocket disconnected');
        setConnectionStatus('disconnected');
        scheduleReconnect();
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        ws.close();
    };
}

function handleMessage(data) {
    switch (data.type) {
        case 'connected':
            console.log('Server acknowledged connection');
            break;
        case 'update':
            refreshImages();
            break;
        case 'ping':
            // Respond to keep-alive ping
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send('pong');
            }
            break;
        default:
            console.log('Unknown message type:', data.type);
    }
}

async function fetchCubeState() {
    try {
        const response = await fetch(`/output/state.json?t=${Date.now()}`);
        if (!response.ok) {
            if (response.status === 404) return null;  // Normal on startup
            throw new Error(`HTTP ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.warn('Failed to fetch cube state:', error.message);
        return null;
    }
}

async function refreshImages() {
    const timestamp = Date.now();

    // Refresh images with cache-busting query parameter
    rawImg.src = `/output/raw.jpg?t=${timestamp}`;
    debugImg.src = `/output/debug.jpg?t=${timestamp}`;

    // Fetch and update 3D cube state
    const state = await fetchCubeState();
    if (state) {
        updateCubeState(state);
    }

    // Update last update time
    const now = new Date();
    lastUpdateEl.textContent = now.toLocaleTimeString();
}

function setConnectionStatus(status) {
    statusIndicator.className = 'indicator ' + status;

    switch (status) {
        case 'connected':
            statusText.textContent = 'Connected';
            connectionState.textContent = 'Connected';
            break;
        case 'disconnected':
            statusText.textContent = 'Disconnected';
            connectionState.textContent = 'Disconnected';
            break;
        case 'connecting':
            statusText.textContent = 'Connecting...';
            connectionState.textContent = 'Connecting...';
            break;
    }
}

function scheduleReconnect() {
    if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
    }

    // Exponential backoff with max delay
    const delay = Math.min(
        RECONNECT_BASE_DELAY * Math.pow(2, reconnectAttempts),
        RECONNECT_MAX_DELAY
    );

    console.log(`Reconnecting in ${delay}ms (attempt ${reconnectAttempts + 1})`);
    reconnectAttempts++;

    reconnectTimeout = setTimeout(connect, delay);
}

// Handle image load errors gracefully
rawImg.onerror = () => {
    console.log('Raw image not available');
};

debugImg.onerror = () => {
    console.log('Debug image not available');
};

// Start connection when page loads
connect();

// Refresh images on page visibility change (when tab becomes active)
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
        refreshImages();
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            connect();
        }
    }
});

// ============================================
// Calibration Functions
// ============================================

function enterCalibrationMode() {
    calibrationMode = true;
    calibrationVertices = [];
    calibrateBtn.classList.add('active');
    calibrationOverlay.classList.remove('hidden');
    rawContainer.classList.add('calibrating');
    updateVertexDisplay();
    setupCanvas();
    drawCalibration();
}

function exitCalibrationMode() {
    calibrationMode = false;
    calibrateBtn.classList.remove('active');
    calibrationOverlay.classList.add('hidden');
    rawContainer.classList.remove('calibrating');
    clearCanvas();
}

function resetCalibration() {
    calibrationVertices = [];
    calibrationSave.disabled = true;
    updateVertexDisplay();
    drawCalibration();
}

function updateVertexDisplay() {
    vertexElements.forEach((el, idx) => {
        el.classList.remove('active', 'done');
        if (idx < calibrationVertices.length) {
            el.classList.add('done');
        } else if (idx === calibrationVertices.length) {
            el.classList.add('active');
        }
    });

    calibrationSave.disabled = calibrationVertices.length < 8;
}

function setupCanvas() {
    // Match canvas size and position to displayed image
    const imgRect = rawImg.getBoundingClientRect();
    const containerRect = rawContainer.getBoundingClientRect();

    // Canvas size matches image
    calibrationCanvas.width = imgRect.width;
    calibrationCanvas.height = imgRect.height;
    calibrationCanvas.style.width = imgRect.width + 'px';
    calibrationCanvas.style.height = imgRect.height + 'px';

    // Position canvas exactly over image (accounting for flex centering)
    const offsetX = imgRect.left - containerRect.left;
    const offsetY = imgRect.top - containerRect.top;
    calibrationCanvas.style.position = 'absolute';
    calibrationCanvas.style.left = offsetX + 'px';
    calibrationCanvas.style.top = offsetY + 'px';
    calibrationCanvas.style.transform = 'none';
}

function clearCanvas() {
    const ctx = calibrationCanvas.getContext('2d');
    ctx.clearRect(0, 0, calibrationCanvas.width, calibrationCanvas.height);
}

function drawCalibration() {
    const ctx = calibrationCanvas.getContext('2d');
    ctx.clearRect(0, 0, calibrationCanvas.width, calibrationCanvas.height);

    if (calibrationVertices.length === 0) return;

    // Get scale factors between image natural size and display size
    const scaleX = calibrationCanvas.width / rawImg.naturalWidth;
    const scaleY = calibrationCanvas.height / rawImg.naturalHeight;

    // Draw vertices as circles
    calibrationVertices.forEach((vertex, idx) => {
        const x = vertex[0] * scaleX;
        const y = vertex[1] * scaleY;

        ctx.beginPath();
        ctx.arc(x, y, 8, 0, Math.PI * 2);
        ctx.fillStyle = '#4caf50';
        ctx.fill();
        ctx.strokeStyle = 'white';
        ctx.lineWidth = 2;
        ctx.stroke();

        // Draw index number
        ctx.fillStyle = 'white';
        ctx.font = 'bold 12px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText((idx + 1).toString(), x, y);
    });

    // Draw face polygons if we have enough vertices
    if (calibrationVertices.length >= 4) {
        const faces = computeFacePolygons();

        ctx.lineWidth = 2;

        // Draw U face (vertices 0, 1, 3, 2)
        if (faces.U) {
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.8)';
            drawPolygon(ctx, faces.U, scaleX, scaleY);
        }

        // Draw L face (vertices 2, 3, 5, 4)
        if (faces.L) {
            ctx.strokeStyle = 'rgba(255, 0, 0, 0.8)';
            drawPolygon(ctx, faces.L, scaleX, scaleY);
        }

        // Draw R face (vertices 3, 6, 7, 5)
        if (faces.R) {
            ctx.strokeStyle = 'rgba(0, 100, 255, 0.8)';
            drawPolygon(ctx, faces.R, scaleX, scaleY);
        }
    }
}

function drawPolygon(ctx, vertices, scaleX, scaleY) {
    if (vertices.length < 3) return;

    ctx.beginPath();
    ctx.moveTo(vertices[0][0] * scaleX, vertices[0][1] * scaleY);
    for (let i = 1; i < vertices.length; i++) {
        ctx.lineTo(vertices[i][0] * scaleX, vertices[i][1] * scaleY);
    }
    ctx.closePath();
    ctx.stroke();
}

function computeFacePolygons() {
    const v = calibrationVertices;
    const faces = {};

    // U face: vertices 0 (top-left), 1 (top-right), 3 (center), 2 (l top-left)
    if (v.length >= 4) {
        faces.U = [v[0], v[1], v[3], v[2]];
    }

    // L face: vertices 2 (l top-left), 3 (center), 5 (bottom-center), 4 (l bottom-left)
    if (v.length >= 6) {
        faces.L = [v[2], v[3], v[5], v[4]];
    }

    // R face: vertices 3 (center), 6 (r top-right), 7 (r bottom-right), 5 (bottom-center)
    if (v.length >= 8) {
        faces.R = [v[3], v[6], v[7], v[5]];
    }

    return faces;
}

function handleImageClick(event) {
    if (!calibrationMode || calibrationVertices.length >= 8) return;

    // Get click position relative to image
    const rect = rawImg.getBoundingClientRect();
    const clickX = event.clientX - rect.left;
    const clickY = event.clientY - rect.top;

    // Convert to image coordinates (natural size)
    const imgX = Math.round(clickX * rawImg.naturalWidth / rect.width);
    const imgY = Math.round(clickY * rawImg.naturalHeight / rect.height);

    calibrationVertices.push([imgX, imgY]);
    updateVertexDisplay();
    drawCalibration();

    console.log(`Vertex ${calibrationVertices.length}: (${imgX}, ${imgY})`);
}

async function saveCalibration() {
    if (calibrationVertices.length < 8) return;

    const faces = computeFacePolygons();

    // Build vertices object
    const vertices = {};
    VERTEX_NAMES.forEach((name, idx) => {
        vertices[name] = calibrationVertices[idx];
    });

    const data = {
        vertices: vertices,
        face_polygons: faces
    };

    try {
        const response = await fetch('/calibrate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            console.log('Calibration saved');
            exitCalibrationMode();
            alert('Calibration saved! Run pipeline to see results.');
        } else {
            const error = await response.text();
            alert('Failed to save calibration: ' + error);
        }
    } catch (e) {
        alert('Error saving calibration: ' + e.message);
    }
}

// Calibration event listeners
calibrateBtn.addEventListener('click', () => {
    if (calibrationMode) {
        exitCalibrationMode();
    } else {
        enterCalibrationMode();
    }
});

calibrationReset.addEventListener('click', resetCalibration);
calibrationSave.addEventListener('click', saveCalibration);
calibrationCancel.addEventListener('click', exitCalibrationMode);
rawImg.addEventListener('click', handleImageClick);

// Re-setup canvas when image loads or resizes
rawImg.addEventListener('load', () => {
    if (calibrationMode) {
        setupCanvas();
        drawCalibration();
    }
});

window.addEventListener('resize', () => {
    if (calibrationMode) {
        setupCanvas();
        drawCalibration();
    }
});

// ============================================
// 3D Cube Initialization
// ============================================

// Initialize cube after a short delay to ensure container is sized
setTimeout(() => {
    const cubeContainer = document.getElementById('cube-3d');
    if (cubeContainer) {
        console.log('Initializing 3D cube, container size:',
            cubeContainer.clientWidth, 'x', cubeContainer.clientHeight);
        const success = initCube3D(cubeContainer);
        if (success) {
            console.log('3D cube initialized successfully');
            // Fetch initial state
            fetchCubeState().then(state => {
                if (state) updateCubeState(state);
            });
        } else {
            console.error('Failed to initialize 3D cube');
        }
    }
}, 100);
