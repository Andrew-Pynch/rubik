// WebSocket client for Rubik's Cube CV Debugger

import {
    initCube3D,
    updateCubeState,
    updateGroundTruthCube,
    setOrientations,
    getOrientations,
    highlightFace,
    showFaceLabels,
    enableFaceClickMode,
    disableFaceClickMode
} from './cube3d.js';

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

// Capture workflow elements
const captureBtn = document.getElementById('capture-btn');
const resetBtn = document.getElementById('reset-btn');
const progressText = document.getElementById('progress-text');
const rotationHint = document.getElementById('rotation-hint');
const faceIcons = document.querySelectorAll('.face-icon');

// Capture state
let isCapturing = false;

// Face color mapping for icons
const FACE_COLORS = {
    'U': '#ffffff', // White
    'D': '#ffff00', // Yellow
    'F': '#ff0000', // Red
    'B': '#ff8c00', // Orange
    'L': '#00ff00', // Green
    'R': '#0000ff', // Blue
};

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
    'f_top_left',
    'center',
    'f_bottom_left',
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
        startCameraStatusPolling();
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
        stopCameraStatusPolling();
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
            // Fetch initial session state
            fetchSessionState();
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

function setConnectionStatus(status, cameraStatus = null) {
    statusIndicator.className = 'indicator ' + status;

    switch (status) {
        case 'connected':
            if (cameraStatus && !cameraStatus.connected) {
                statusText.textContent = 'Camera: ' + (cameraStatus.error || 'Disconnected');
                connectionState.textContent = 'Camera Offline';
                statusIndicator.className = 'indicator camera-error';
            } else {
                statusText.textContent = 'Connected';
                connectionState.textContent = 'Connected';
            }
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

// Camera status polling
let cameraStatusInterval = null;

async function fetchCameraStatus() {
    try {
        const response = await fetch('/camera/status');
        if (response.ok) {
            const status = await response.json();
            // Update UI if WebSocket is connected but camera has issues
            if (ws && ws.readyState === WebSocket.OPEN) {
                setConnectionStatus('connected', status);
            }
            return status;
        }
    } catch (error) {
        console.warn('Failed to fetch camera status:', error);
    }
    return null;
}

function startCameraStatusPolling() {
    if (cameraStatusInterval) return;
    cameraStatusInterval = setInterval(fetchCameraStatus, 3000);
    fetchCameraStatus(); // Initial fetch
}

function stopCameraStatusPolling() {
    if (cameraStatusInterval) {
        clearInterval(cameraStatusInterval);
        cameraStatusInterval = null;
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

        // Draw F face (vertices 2, 3, 5, 4)
        if (faces.F) {
            ctx.strokeStyle = 'rgba(255, 0, 0, 0.8)';
            drawPolygon(ctx, faces.F, scaleX, scaleY);
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

    // F face: vertices 2 (f top-left), 3 (center), 5 (bottom-center), 4 (f bottom-left)
    if (v.length >= 6) {
        faces.F = [v[2], v[3], v[5], v[4]];
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

// ============================================
// Save ROI Defaults
// ============================================

const saveDefaultsBtn = document.getElementById('save-defaults-btn');

async function saveCalibrationDefaults() {
    try {
        const response = await fetch('/save-calibration-defaults', { method: 'POST' });
        const result = await response.json();

        if (result.status === 'ok') {
            showToast('ROI calibration saved as default', 'success');
        } else {
            showToast('Failed: ' + (result.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}

if (saveDefaultsBtn) {
    saveDefaultsBtn.addEventListener('click', saveCalibrationDefaults);
}

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
// Capture Workflow Functions
// ============================================

async function fetchSessionState() {
    try {
        const response = await fetch('/session');
        if (response.ok) {
            const session = await response.json();
            updateProgressUI(session);
        }
    } catch (error) {
        console.warn('Failed to fetch session state:', error);
    }
}

function updateProgressUI(result) {
    // Update progress text
    const count = result.progress?.count ?? 0;
    progressText.textContent = `${count}/6 faces`;

    // Update rotation hint
    if (result.hint) {
        rotationHint.textContent = result.hint;
    }

    // Update step indicator
    const currentStep = result.current_step ?? 0;
    const totalSteps = result.total_steps ?? 2;
    const stepElements = document.querySelectorAll('.step-indicator .step');
    stepElements.forEach(stepEl => {
        const stepIdx = parseInt(stepEl.dataset.step, 10);
        stepEl.classList.remove('completed', 'active', 'pending');
        if (stepIdx < currentStep) {
            stepEl.classList.add('completed');
        } else if (stepIdx === currentStep) {
            stepEl.classList.add('active');
        } else {
            stepEl.classList.add('pending');
        }
    });

    // Update face icons
    const captured = result.captured || [];
    faceIcons.forEach(icon => {
        const face = icon.dataset.face;
        if (captured.includes(face)) {
            icon.textContent = face;
            icon.style.backgroundColor = FACE_COLORS[face];
            icon.style.color = (face === 'U' || face === 'D' || face === 'L') ? '#000' : '#fff';
            icon.classList.add('captured');
        } else {
            icon.textContent = '?';
            icon.style.backgroundColor = '#404040';
            icon.style.color = '#888';
            icon.classList.remove('captured');
        }
    });

    // Check completion
    if (result.is_complete) {
        progressText.style.color = '#4caf50';
        progressText.style.fontWeight = 'bold';
    } else {
        progressText.style.color = '';
        progressText.style.fontWeight = '';
    }
}

async function triggerCapture() {
    if (isCapturing) return;

    isCapturing = true;
    captureBtn.disabled = true;
    captureBtn.textContent = '⏳ Capturing...';

    try {
        const response = await fetch('/capture', { method: 'POST' });
        const result = await response.json();

        updateProgressUI(result);

        if (!result.success) {
            console.error('Capture failed:', result.error);
            showToast('Capture failed: ' + (result.error || 'Unknown error'), 'error');
        } else if (result.inconsistencies && result.inconsistencies.length > 0) {
            console.warn('Capture inconsistencies:', result.inconsistencies);
            showToast(`Warning: ${result.inconsistencies.length} sticker conflicts detected`, 'warning');
        } else if (result.new_faces && result.new_faces.length > 0) {
            showToast(`Captured faces: ${result.new_faces.join(', ')}`, 'success');
        } else {
            showToast('Same faces detected - rotate cube to show new faces', 'info');
        }

        if (result.is_complete) {
            showToast('🎉 All 6 faces captured!', 'success');
        }

    } catch (error) {
        console.error('Capture error:', error);
        showToast('Error: ' + error.message, 'error');
    } finally {
        isCapturing = false;
        captureBtn.disabled = false;
        captureBtn.textContent = '📷 Capture';
    }
}

async function resetSession() {
    try {
        const response = await fetch('/reset', { method: 'POST' });
        const result = await response.json();

        updateProgressUI(result);
        refreshImages();
        showToast('Session reset', 'info');

    } catch (error) {
        console.error('Reset error:', error);
        showToast('Reset failed: ' + error.message, 'error');
    }
}

function showToast(message, type = 'info') {
    // Remove existing toasts
    const existingToast = document.querySelector('.toast');
    if (existingToast) {
        existingToast.remove();
    }

    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    document.body.appendChild(toast);

    // Fade in
    requestAnimationFrame(() => {
        toast.classList.add('visible');
    });

    // Auto-remove after 3 seconds
    setTimeout(() => {
        toast.classList.remove('visible');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Capture button event listeners
if (captureBtn) {
    captureBtn.addEventListener('click', triggerCapture);
}

if (resetBtn) {
    resetBtn.addEventListener('click', resetSession);
}

// ============================================
// 3D Cube Initialization
// ============================================

// Initialize cube after a short delay to ensure container is sized
setTimeout(async () => {
    const cubeContainer = document.getElementById('cube-3d');
    if (cubeContainer) {
        console.log('Initializing 3D cube, container size:',
            cubeContainer.clientWidth, 'x', cubeContainer.clientHeight);
        const success = initCube3D(cubeContainer);
        if (success) {
            console.log('3D cube initialized successfully');

            // Load ground truth for the right cube
            try {
                const gtResponse = await fetch('/ground-truth');
                if (gtResponse.ok) {
                    const gtData = await gtResponse.json();
                    if (gtData.colors) {
                        groundTruthData = gtData.colors;
                        groundTruth = gtData.colors;  // Also update local state
                        updateGroundTruthCube(groundTruthData);
                        console.log('Ground truth loaded for 3D cube');
                    }
                }
            } catch (e) {
                console.warn('No ground truth data available:', e.message);
            }

            // Fetch initial state for estimation cube
            const state = await fetchCubeState();
            if (state) {
                updateCubeState(state);
                updateAccuracySummary(state, groundTruthData);
            }
        } else {
            console.error('Failed to initialize 3D cube');
        }
    }
}, 100);


// ============================================
// Live Stream Toggle
// ============================================

const streamBtn = document.getElementById('stream-btn');
const streamStatus = document.getElementById('stream-status');
let isStreaming = false;
const STATIC_DEBUG_SRC = '/output/debug.jpg';
const STREAM_SRC = '/stream';

function toggleStream() {
    isStreaming = !isStreaming;

    if (isStreaming) {
        // Switch to live stream
        debugImg.src = STREAM_SRC;
        streamBtn.textContent = '⏹ Stop Stream';
        streamBtn.classList.add('streaming');
        streamStatus.classList.remove('hidden');
        console.log('Started live stream');
    } else {
        // Switch back to static image
        debugImg.src = STATIC_DEBUG_SRC + `?t=${Date.now()}`;
        streamBtn.textContent = '▶ Live Stream';
        streamBtn.classList.remove('streaming');
        streamStatus.classList.add('hidden');
        console.log('Stopped live stream');
    }
}

if (streamBtn) {
    streamBtn.addEventListener('click', toggleStream);
}

// Don't auto-refresh debug image when streaming
const originalRefreshImages = refreshImages;
refreshImages = async function() {
    const timestamp = Date.now();

    // Refresh raw image
    rawImg.src = `/output/raw.jpg?t=${timestamp}`;

    // Only refresh debug image if not streaming
    if (!isStreaming) {
        debugImg.src = `/output/debug.jpg?t=${timestamp}`;
    }

    // Fetch and update 3D cube state
    const state = await fetchCubeState();
    if (state) {
        updateCubeState(state);
        // Update accuracy summary with ground truth comparison
        updateAccuracySummary(state, groundTruthData);
    }

    // Update last update time
    const now = new Date();
    lastUpdateEl.textContent = now.toLocaleTimeString();
};


// ============================================
// HSV Settings Panel
// ============================================

const settingsBtn = document.getElementById('settings-btn');
const hsvOverlay = document.getElementById('hsv-overlay');
const hueSlider = document.getElementById('hue-slider');
const satSlider = document.getElementById('sat-slider');
const valSlider = document.getElementById('val-slider');
const hueValue = document.getElementById('hue-value');
const satValue = document.getElementById('sat-value');
const valValue = document.getElementById('val-value');
const hsvReset = document.getElementById('hsv-reset');
const hsvClose = document.getElementById('hsv-close');

let hsvVisible = false;

function toggleHsvPanel() {
    hsvVisible = !hsvVisible;
    if (hsvVisible) {
        hsvOverlay.classList.remove('hidden');
        // Fetch current settings
        fetchHsvSettings();
    } else {
        hsvOverlay.classList.add('hidden');
    }
}

async function fetchHsvSettings() {
    try {
        const response = await fetch('/settings/hsv');
        if (response.ok) {
            const settings = await response.json();
            hueSlider.value = settings.h || 0;
            satSlider.value = settings.s || 0;
            valSlider.value = settings.v || 0;
            updateSliderValues();
        }
    } catch (error) {
        console.warn('Failed to fetch HSV settings:', error);
    }
}

async function updateHsvSettings() {
    const data = {
        h: parseInt(hueSlider.value, 10),
        s: parseInt(satSlider.value, 10),
        v: parseInt(valSlider.value, 10),
    };

    try {
        await fetch('/settings/hsv', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
    } catch (error) {
        console.warn('Failed to update HSV settings:', error);
    }
}

function updateSliderValues() {
    hueValue.textContent = hueSlider.value;
    satValue.textContent = satSlider.value;
    valValue.textContent = valSlider.value;
}

function resetHsvSliders() {
    hueSlider.value = 0;
    satSlider.value = 0;
    valSlider.value = 0;
    updateSliderValues();
    updateHsvSettings();
}

// HSV event listeners
if (settingsBtn) {
    settingsBtn.addEventListener('click', toggleHsvPanel);
}

if (hsvClose) {
    hsvClose.addEventListener('click', () => {
        hsvOverlay.classList.add('hidden');
        hsvVisible = false;
    });
}

if (hsvReset) {
    hsvReset.addEventListener('click', resetHsvSliders);
}

// Update values and send to server on slider change
[hueSlider, satSlider, valSlider].forEach(slider => {
    if (slider) {
        slider.addEventListener('input', () => {
            updateSliderValues();
            updateHsvSettings();
        });
    }
});

// ============================================
// Ground Truth Mode
// ============================================

const gtBtn = document.getElementById('ground-truth-btn');
const gtOverlay = document.getElementById('ground-truth-overlay');
const gtSelectedSticker = document.getElementById('gt-selected-sticker');
const gtCount = document.getElementById('gt-count');
const gtColorBtns = document.querySelectorAll('.gt-color-btn');
const gtClear = document.getElementById('gt-clear');
const gtSave = document.getElementById('gt-save');
const gtClose = document.getElementById('gt-close');

let gtMode = false;
let gtSelectedFace = null;
let gtSelectedRow = null;
let gtSelectedCol = null;

// Ground truth data for 3D cube comparison
let groundTruthData = null;

let groundTruth = {
    U: [[null, null, null], [null, null, null], [null, null, null]],
    F: [[null, null, null], [null, null, null], [null, null, null]],
    R: [[null, null, null], [null, null, null], [null, null, null]],
};

// Sticker grid positions relative to face polygons (approximate centers)
// These are u, v coordinates within each face (0-1 range)
const STICKER_UV = [
    [0.17, 0.17], [0.50, 0.17], [0.83, 0.17],
    [0.17, 0.50], [0.50, 0.50], [0.83, 0.50],
    [0.17, 0.83], [0.50, 0.83], [0.83, 0.83],
];

function toggleGtMode() {
    gtMode = !gtMode;
    if (gtMode) {
        gtOverlay.classList.remove('hidden');
        document.body.classList.add('gt-mode');
        fetchGroundTruth();
    } else {
        gtOverlay.classList.add('hidden');
        document.body.classList.remove('gt-mode');
    }
}

function updateGtCount() {
    let count = 0;
    for (const face of ['U', 'F', 'R']) {
        for (let row = 0; row < 3; row++) {
            for (let col = 0; col < 3; col++) {
                if (groundTruth[face][row][col]) count++;
            }
        }
    }
    gtCount.textContent = `${count}/27 marked`;
}

function selectGtSticker(face, row, col) {
    gtSelectedFace = face;
    gtSelectedRow = row;
    gtSelectedCol = col;
    const current = groundTruth[face][row][col] || '?';
    gtSelectedSticker.textContent = `${face}[${row},${col}] = ${current}`;

    // Highlight current color button
    gtColorBtns.forEach(btn => {
        btn.classList.toggle('selected', btn.dataset.color === current);
    });
}

function setGtColor(color) {
    if (gtSelectedFace && gtSelectedRow !== null && gtSelectedCol !== null) {
        groundTruth[gtSelectedFace][gtSelectedRow][gtSelectedCol] = color;
        gtSelectedSticker.textContent = `${gtSelectedFace}[${gtSelectedRow},${gtSelectedCol}] = ${color}`;
        updateGtCount();

        // Highlight selected button
        gtColorBtns.forEach(btn => {
            btn.classList.toggle('selected', btn.dataset.color === color);
        });
    }
}

// Order polygon corners as TL, TR, BR, BL (matching pipeline.py)
function orderPolygonCorners(polygon) {
    const pts = polygon.map(p => ({x: p[0], y: p[1]}));

    // Sort by y first to get top vs bottom
    pts.sort((a, b) => a.y - b.y);
    const topPts = pts.slice(0, 2);
    const bottomPts = pts.slice(2, 4);

    // Sort each pair by x to get left vs right
    topPts.sort((a, b) => a.x - b.x);
    bottomPts.sort((a, b) => a.x - b.x);

    // Return as [TL, TR, BR, BL]
    return [
        [topPts[0].x, topPts[0].y],
        [topPts[1].x, topPts[1].y],
        [bottomPts[1].x, bottomPts[1].y],
        [bottomPts[0].x, bottomPts[0].y]
    ];
}

// Bilinear interpolation to find UV coords within a quad
function pointInQuad(px, py, corners) {
    // corners: [TL, TR, BR, BL] as [[x,y], ...]
    const [tl, tr, br, bl] = corners;

    // Use inverse bilinear interpolation
    // Iterative solution for non-rectangular quads
    let u = 0.5, v = 0.5;

    for (let iter = 0; iter < 10; iter++) {
        // Compute point at current (u, v)
        const x = (1-u)*(1-v)*tl[0] + u*(1-v)*tr[0] + u*v*br[0] + (1-u)*v*bl[0];
        const y = (1-u)*(1-v)*tl[1] + u*(1-v)*tr[1] + u*v*br[1] + (1-u)*v*bl[1];

        // Compute Jacobian
        const dxdu = -(1-v)*tl[0] + (1-v)*tr[0] + v*br[0] - v*bl[0];
        const dxdv = -(1-u)*tl[0] - u*tr[0] + u*br[0] + (1-u)*bl[0];
        const dydu = -(1-v)*tl[1] + (1-v)*tr[1] + v*br[1] - v*bl[1];
        const dydv = -(1-u)*tl[1] - u*tr[1] + u*br[1] + (1-u)*bl[1];

        // Solve for delta
        const det = dxdu * dydv - dxdv * dydu;
        if (Math.abs(det) < 1e-10) break;

        const dx = px - x;
        const dy = py - y;

        const du = (dydv * dx - dxdv * dy) / det;
        const dv = (-dydu * dx + dxdu * dy) / det;

        u += du;
        v += dv;

        if (Math.abs(du) < 0.001 && Math.abs(dv) < 0.001) break;
    }

    const inside = u >= 0 && u <= 1 && v >= 0 && v <= 1;
    return { inside, u, v };
}

// Cache for calibration data
let cachedCalibration = null;

async function handleDebugImageClick(event) {
    if (!gtMode) return;

    // Get click position relative to image
    const rect = debugImg.getBoundingClientRect();
    const clickX = event.clientX - rect.left;
    const clickY = event.clientY - rect.top;

    // Convert to image coordinates
    const imgX = clickX * debugImg.naturalWidth / rect.width;
    const imgY = clickY * debugImg.naturalHeight / rect.height;

    // Fetch calibration data (cached)
    try {
        if (!cachedCalibration) {
            const response = await fetch('/output/calibration.json');
            if (!response.ok) {
                showToast('No calibration data. Please calibrate first.', 'warning');
                return;
            }
            cachedCalibration = await response.json();
        }

        const facePolygons = cachedCalibration.face_polygons;
        if (!facePolygons) {
            showToast('Invalid calibration data', 'error');
            return;
        }

        // Check each face
        for (const [face, polygon] of Object.entries(facePolygons)) {
            const corners = orderPolygonCorners(polygon);
            const result = pointInQuad(imgX, imgY, corners);

            if (result.inside) {
                const row = Math.min(2, Math.floor(result.v * 3));
                const col = Math.min(2, Math.floor(result.u * 3));
                selectGtSticker(face, row, col);
                console.log(`Selected: ${face}[${row},${col}] at UV(${result.u.toFixed(2)}, ${result.v.toFixed(2)})`);
                return;
            }
        }

        // Click was outside all faces
        console.log(`Click at (${imgX.toFixed(0)}, ${imgY.toFixed(0)}) - outside face polygons`);

    } catch (error) {
        console.error('Failed to process click:', error);
        showToast('Error processing click', 'error');
    }
}

async function fetchGroundTruth() {
    try {
        const response = await fetch('/ground-truth');
        if (response.ok) {
            const data = await response.json();
            if (data.colors) {
                groundTruth = data.colors;
                groundTruthData = data.colors;  // Store for 3D cube
                updateGtCount();
                // Update 3D ground truth cube
                updateGroundTruthCube(groundTruthData);
            }
        }
    } catch (error) {
        console.warn('No existing ground truth found');
    }
}

async function saveGroundTruth() {
    try {
        const response = await fetch('/ground-truth', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ colors: groundTruth })
        });

        if (response.ok) {
            showToast('Ground truth saved!', 'success');
            // Update 3D ground truth cube
            groundTruthData = { ...groundTruth };
            updateGroundTruthCube(groundTruthData);
            // Update accuracy summary with current state
            const state = await fetchCubeState();
            if (state) {
                updateAccuracySummary(state, groundTruthData);
            }
        } else {
            showToast('Failed to save ground truth', 'error');
        }
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}

function clearGroundTruth() {
    groundTruth = {
        U: [[null, null, null], [null, null, null], [null, null, null]],
        F: [[null, null, null], [null, null, null], [null, null, null]],
        R: [[null, null, null], [null, null, null], [null, null, null]],
    };
    groundTruthData = { ...groundTruth };
    gtSelectedSticker.textContent = 'None';
    updateGtCount();
    // Update 3D cube (shows as unmarked/dark)
    updateGroundTruthCube(groundTruthData);
    // Clear accuracy summary
    const summaryEl = document.getElementById('accuracy-summary');
    if (summaryEl) {
        summaryEl.textContent = 'No ground truth marked';
        summaryEl.style.color = '#aaa';
    }
}

/**
 * Update accuracy summary text (e.g., "23/27 correct (85%)")
 */
function updateAccuracySummary(detected, groundTruthColors) {
    const summaryEl = document.getElementById('accuracy-summary');
    if (!summaryEl) return;

    if (!groundTruthColors) {
        summaryEl.textContent = 'No ground truth data';
        return;
    }

    let correct = 0, total = 0;
    for (const face of ['U', 'F', 'R']) {
        const gt = groundTruthColors[face];
        const det = detected?.faces?.[face];
        if (!gt) continue;

        for (let r = 0; r < 3; r++) {
            for (let c = 0; c < 3; c++) {
                if (gt[r]?.[c]) {
                    total++;
                    if (det?.[r]?.[c] === gt[r][c]) correct++;
                }
            }
        }
    }

    if (total === 0) {
        summaryEl.textContent = 'No ground truth marked';
        return;
    }

    const pct = Math.round(100 * correct / total);
    summaryEl.textContent = `${correct}/${total} correct (${pct}%)`;

    // Color code the result
    if (pct >= 90) {
        summaryEl.style.color = '#4caf50';  // Green
    } else if (pct >= 70) {
        summaryEl.style.color = '#ff9800';  // Orange
    } else {
        summaryEl.style.color = '#f44336';  // Red
    }
}

// Ground truth event listeners - attach directly without guards
// Elements are guaranteed to exist in the HTML
gtBtn.addEventListener('click', () => {
    console.log('Ground Truth button clicked');
    toggleGtMode();
});

gtClose.addEventListener('click', () => {
    console.log('GT Close clicked');
    gtOverlay.classList.add('hidden');
    document.body.classList.remove('gt-mode');
    gtMode = false;
});

gtClear.addEventListener('click', () => {
    console.log('GT Clear clicked');
    clearGroundTruth();
});

gtSave.addEventListener('click', () => {
    console.log('GT Save clicked');
    saveGroundTruth();
});

gtColorBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        console.log('Color button clicked:', btn.dataset.color);
        setGtColor(btn.dataset.color);
    });
});

debugImg.addEventListener('click', handleDebugImageClick);

// ============================================
// 3D Calibration Mode
// ============================================

const cal3dBtn = document.getElementById('calibrate-3d-btn');
const cal3dOverlay = document.getElementById('calibrate-3d-overlay');
const cal3dTabs = document.querySelectorAll('.cal3d-tab');
const cal3dTarget = document.getElementById('cal3d-target');
const cal3dRotValue = document.getElementById('cal3d-rot-value');
const cal3dRotLeft = document.getElementById('cal3d-rot-left');
const cal3dRotRight = document.getElementById('cal3d-rot-right');
const cal3dReset = document.getElementById('cal3d-reset');
const cal3dSave = document.getElementById('cal3d-save');
const cal3dClose = document.getElementById('cal3d-close');

let cal3dMode = false;
let currentCalFace = 'U';  // Currently selected camera ROI (U, F, or R)
let faceMappings = {
    U: { target: 'U', rotation: 0 },
    F: { target: 'F', rotation: 0 },
    R: { target: 'R', rotation: 0 }
};

function openCal3DPanel() {
    cal3dMode = true;
    cal3dOverlay.classList.remove('hidden');
    loadMappings();
}

function closeCal3DPanel() {
    cal3dMode = false;
    cal3dOverlay.classList.add('hidden');
    disableFaceClickMode();
    highlightFace(null);
    showFaceLabels(null);
}

async function loadMappings() {
    // Load from cached calibration or fetch
    try {
        if (!cachedCalibration) {
            const response = await fetch('/output/calibration.json');
            if (response.ok) {
                cachedCalibration = await response.json();
            }
        }

        if (cachedCalibration?.face_mappings) {
            // Load from new face_mappings format
            faceMappings = {
                U: { ...cachedCalibration.face_mappings.U },
                F: { ...cachedCalibration.face_mappings.F },
                R: { ...cachedCalibration.face_mappings.R }
            };
        } else if (cachedCalibration?.face_orientations) {
            // Backwards compatibility: convert from old format
            faceMappings = {
                U: { target: 'U', rotation: cachedCalibration.face_orientations.U || 0 },
                F: { target: 'F', rotation: cachedCalibration.face_orientations.F || 0 },
                R: { target: 'R', rotation: cachedCalibration.face_orientations.R || 0 }
            };
        } else {
            faceMappings = {
                U: { target: 'U', rotation: 0 },
                F: { target: 'F', rotation: 0 },
                R: { target: 'R', rotation: 0 }
            };
        }
    } catch (e) {
        console.warn('Failed to load mappings:', e);
        faceMappings = {
            U: { target: 'U', rotation: 0 },
            F: { target: 'F', rotation: 0 },
            R: { target: 'R', rotation: 0 }
        };
    }

    updateCal3DUI();
    selectCalFace(currentCalFace);

    // Enable face click mode
    enableFaceClickMode((clickedFace) => {
        faceMappings[currentCalFace].target = clickedFace;
        updateCal3DUI();
        applyMappingsToOrientations();
        // Update highlight to new target face
        highlightFace(clickedFace);
        showFaceLabels(clickedFace);
    });
}

function selectCalFace(face) {
    currentCalFace = face;
    updateCal3DUI();

    const targetFace = faceMappings[face].target;
    highlightFace(targetFace);
    showFaceLabels(targetFace);
}

function rotateLeft() {
    faceMappings[currentCalFace].rotation =
        (faceMappings[currentCalFace].rotation + 270) % 360;
    updateCal3DUI();
    applyMappingsToOrientations();
}

function rotateRight() {
    faceMappings[currentCalFace].rotation =
        (faceMappings[currentCalFace].rotation + 90) % 360;
    updateCal3DUI();
    applyMappingsToOrientations();
}

function applyMappingsToOrientations() {
    // Convert mappings to orientations format for cube3d
    const orientations = {};
    for (const [roi, mapping] of Object.entries(faceMappings)) {
        orientations[mapping.target] = mapping.rotation;
    }
    setOrientations(orientations);
}

function updateCal3DUI() {
    // Update tab selection
    cal3dTabs.forEach(tab => {
        tab.classList.toggle('selected', tab.dataset.face === currentCalFace);
    });

    // Update mapping display
    const mapping = faceMappings[currentCalFace];
    if (cal3dTarget) cal3dTarget.textContent = mapping.target;
    if (cal3dRotValue) cal3dRotValue.textContent = `${mapping.rotation}°`;
}

async function saveMappings() {
    // Preserve existing calibration and add mappings
    try {
        if (!cachedCalibration) {
            const response = await fetch('/output/calibration.json');
            if (response.ok) {
                cachedCalibration = await response.json();
            } else {
                showToast('No calibration data. Please calibrate ROI first.', 'warning');
                return;
            }
        }

        // Convert to face_orientations for backwards compatibility
        const faceOrientations = {};
        for (const [roi, mapping] of Object.entries(faceMappings)) {
            faceOrientations[mapping.target] = mapping.rotation;
        }

        const data = {
            vertices: cachedCalibration.vertices || {},
            face_polygons: cachedCalibration.face_polygons || {},
            face_mappings: faceMappings,
            face_orientations: faceOrientations  // Keep for backwards compat
        };

        const response = await fetch('/calibrate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            cachedCalibration.face_mappings = faceMappings;
            cachedCalibration.face_orientations = faceOrientations;
            showToast('3D calibration saved!', 'success');
        } else {
            showToast('Failed to save calibration', 'error');
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    }
}

function resetMappings() {
    faceMappings = {
        U: { target: 'U', rotation: 0 },
        F: { target: 'F', rotation: 0 },
        R: { target: 'R', rotation: 0 }
    };
    updateCal3DUI();
    applyMappingsToOrientations();
    selectCalFace(currentCalFace);
}

// 3D Calibration event listeners
if (cal3dBtn) {
    cal3dBtn.addEventListener('click', () => {
        if (cal3dMode) {
            closeCal3DPanel();
        } else {
            openCal3DPanel();
        }
    });
}

if (cal3dClose) {
    cal3dClose.addEventListener('click', closeCal3DPanel);
}

cal3dTabs.forEach(tab => {
    tab.addEventListener('click', () => {
        selectCalFace(tab.dataset.face);
    });
});

if (cal3dRotLeft) {
    cal3dRotLeft.addEventListener('click', rotateLeft);
}

if (cal3dRotRight) {
    cal3dRotRight.addEventListener('click', rotateRight);
}

if (cal3dReset) {
    cal3dReset.addEventListener('click', resetMappings);
}

if (cal3dSave) {
    cal3dSave.addEventListener('click', saveMappings);
}

// Load mappings on page startup (after cube init)
setTimeout(async () => {
    try {
        const response = await fetch('/output/calibration.json');
        if (response.ok) {
            cachedCalibration = await response.json();
            if (cachedCalibration?.face_mappings) {
                faceMappings = {
                    U: { ...cachedCalibration.face_mappings.U },
                    F: { ...cachedCalibration.face_mappings.F },
                    R: { ...cachedCalibration.face_mappings.R }
                };
            } else if (cachedCalibration?.face_orientations) {
                // Backwards compat
                faceMappings = {
                    U: { target: 'U', rotation: cachedCalibration.face_orientations.U || 0 },
                    F: { target: 'F', rotation: cachedCalibration.face_orientations.F || 0 },
                    R: { target: 'R', rotation: cachedCalibration.face_orientations.R || 0 }
                };
            }
            applyMappingsToOrientations();
        }
    } catch (e) {
        console.warn('Failed to load initial mappings:', e);
    }
}, 200);  // After cube init (100ms)
