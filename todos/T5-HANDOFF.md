# T5 Handoff: Multi-Capture Guided Workflow

## T4 Completion Summary

**Status:** ✅ COMPLETE

**Problem Solved:** The 3D cube visualization showed L and R as opposite faces, but the camera sees them as adjacent faces meeting at a corner.

**Solution Applied:** Renamed CV label "L" → "F" (Front) throughout the codebase:
- `output/calibration.json` - face polygon key
- `pipeline.py` - comments and debug overlay colors
- `config.py` - documentation comments
- `detect.py` - face assignment logic
- `static/app.js` - vertex names and face polygon computation
- `static/index.html` - calibration labels
- `static/cube3d.js` - camera position changed from `(0, 4, -5)` to `(4, 4, 4)`
- `experiments/grid_detection.py` - expected colors
- `CLAUDE.md` - cube orientation documentation

**Verification:** 3D cube now correctly shows:
- U (white) on top
- F (red) on front-left - adjacent to R
- R (blue) on front-right - adjacent to F
- All three faces meet at corner vertex (1, 1, 1)

**Bonus:** Added `screenshot_3d.py` with Playwright for automated 3D screenshot capture (WebGL rendering in headless mode needs further work).

---

## T5 Requirements: Multi-Capture Guided Workflow

### User Story
As a user, I want to place my Rubik's cube in any orientation, capture the visible faces, then have the system guide me through rotating and capturing the remaining faces until the complete cube state is known.

### Current Limitations
1. Single capture only - detects 3 faces (U, F, R) from one angle
2. No web UI controls for triggering captures
3. No state accumulation across multiple captures
4. No guidance for which faces still need capturing

### Required Features

#### 1. Web UI Capture Controls
- Add "Capture" button to localhost:8000 bottom bar
- Trigger pipeline.py execution from browser
- Show capture status/progress
- Display results in real-time

#### 2. Multi-Capture State Accumulation
- Store partial cube state across captures
- Merge new face detections with existing state
- Handle conflicts (same face detected twice with different colors)
- Track which faces have been captured vs. missing

#### 3. Flexible Orientation Support
- Detect which 3 faces are visible in current orientation
- Map detected colors to correct face positions regardless of cube orientation
- Use center sticker color to identify which face is which

#### 4. Guided Workflow UI
- Show which faces are still needed (D, L, B initially)
- Suggest how to rotate cube to capture missing faces
- Visual indicator of capture progress (e.g., 3/6 faces captured)
- "Complete" state when all 6 faces detected

#### 5. Cube State Model Updates
- Extend `CubeState` to track partial vs. complete states
- Add methods to merge captures
- Validate consistency across captures

### Technical Considerations

1. **Face Identification:** Use center sticker color to identify face:
   - White center = U face
   - Yellow center = D face
   - Red center = F face (was "L" in camera)
   - Orange center = B face
   - Blue center = R face
   - Green center = L face

2. **Orientation Detection:** Given 3 visible face centers, determine cube orientation relative to standard position.

3. **WebSocket Integration:** Server already has WebSocket support - use it to trigger captures and push updates.

4. **State Persistence:** Save accumulated state to `output/state.json` with capture history.

### Acceptance Criteria
- [ ] User can trigger capture from web UI
- [ ] System correctly identifies faces by center color
- [ ] State accumulates across multiple captures
- [ ] UI shows which faces are missing
- [ ] UI provides rotation guidance
- [ ] Complete cube state detected after sufficient captures
- [ ] Works regardless of initial cube orientation

### Files Likely to Modify
- `server.py` - Add capture endpoint
- `pipeline.py` - Return detection results, support partial state
- `cube_model.py` - Multi-capture state management
- `static/index.html` - Capture controls UI
- `static/app.js` - Capture triggering, progress display
- `static/cube3d.js` - Show partial/complete state visually

---

## Project Location
`~/personal/rubik`

## Current Working State
- Server: `uvicorn server:app --host 0.0.0.0 --port 8000`
- Pipeline: `python pipeline.py`
- Web UI: http://localhost:8000
- 3D visualization working correctly with F/R adjacent
