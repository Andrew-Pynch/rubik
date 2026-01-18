#!/usr/bin/env bash
# setup.sh - Setup script for Rubik's Cube CV project
# Supports macOS and Linux

set -euo pipefail

# Configuration
REQUIRED_PYTHON_MAJOR=3
REQUIRED_PYTHON_MINOR=11
VENV_DIR=".venv"
CLEAN_INSTALL=false

# Color definitions (with fallback for non-color terminals)
if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BLUE='\033[0;34m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' BLUE='' BOLD='' NC=''
fi

# Output helpers
info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

show_help() {
    echo "Usage: ./setup.sh [OPTIONS]"
    echo ""
    echo "Setup script for Rubik's Cube CV project"
    echo ""
    echo "Options:"
    echo "  --clean    Remove existing venv and reinstall from scratch"
    echo "  --help     Show this help message"
    echo ""
    echo "Requirements:"
    echo "  - Python 3.11 or newer"
    echo "  - Internet connection (for pip install)"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --clean) CLEAN_INSTALL=true; shift ;;
        --help|-h) show_help; exit 0 ;;
        *) warn "Unknown option: $1"; shift ;;
    esac
done

# Change to script directory
cd "$(dirname "$0")"

echo -e "${BOLD}Rubik's Cube CV Project Setup${NC}"
echo "=============================="
echo ""

# Detect OS
OS="unknown"
case "$(uname -s)" in
    Darwin*) OS="macos" ;;
    Linux*)  OS="linux" ;;
esac
info "Detected OS: $OS"

# Find Python
PYTHON_CMD=""
PYTHON_VERSION=""

find_python() {
    local candidates=("python3.13" "python3.12" "python3.11" "python3" "python")

    for cmd in "${candidates[@]}"; do
        if command -v "$cmd" &>/dev/null; then
            local version_output
            version_output=$("$cmd" --version 2>&1)
            local version
            version=$(echo "$version_output" | grep -oE '[0-9]+\.[0-9]+' | head -1)
            local major minor
            major=$(echo "$version" | cut -d. -f1)
            minor=$(echo "$version" | cut -d. -f2)

            if [[ "$major" -eq "$REQUIRED_PYTHON_MAJOR" && "$minor" -ge "$REQUIRED_PYTHON_MINOR" ]]; then
                PYTHON_CMD="$cmd"
                PYTHON_VERSION="$version"
                return 0
            fi
        fi
    done
    return 1
}

if ! find_python; then
    error "Python 3.11 or newer is required but not found."
    echo ""
    echo "Please install Python 3.11+ using one of these methods:"
    echo ""
    if [[ "$OS" == "macos" ]]; then
        echo "  brew install python@3.12"
    else
        echo "  sudo apt install python3.11 python3.11-venv  # Debian/Ubuntu"
        echo "  sudo dnf install python3.11                   # Fedora"
        echo "  sudo pacman -S python                         # Arch"
    fi
    exit 1
fi
success "Found Python $PYTHON_VERSION ($PYTHON_CMD)"

# Check venv module
if ! "$PYTHON_CMD" -m venv --help &>/dev/null; then
    error "Python venv module not available"
    echo ""
    if [[ "$OS" == "linux" ]]; then
        echo "Install it with:"
        echo "  sudo apt install python3-venv  # Debian/Ubuntu"
        echo "  sudo dnf install python3-venv  # Fedora"
    fi
    exit 1
fi

# Handle --clean flag
if [[ "$CLEAN_INSTALL" == true && -d "$VENV_DIR" ]]; then
    warn "Clean install requested, removing existing venv..."
    rm -rf "$VENV_DIR"
fi

# Create or validate virtual environment
if [[ -d "$VENV_DIR" ]]; then
    if [[ -x "$VENV_DIR/bin/python" ]]; then
        local_version=$("$VENV_DIR/bin/python" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        local_major=$(echo "$local_version" | cut -d. -f1)
        local_minor=$(echo "$local_version" | cut -d. -f2)

        if [[ "$local_major" -eq "$REQUIRED_PYTHON_MAJOR" && "$local_minor" -ge "$REQUIRED_PYTHON_MINOR" ]]; then
            info "Existing venv found with Python $local_version (use --clean to recreate)"
        else
            warn "Existing venv has Python $local_version, need >= $REQUIRED_PYTHON_MAJOR.$REQUIRED_PYTHON_MINOR"
            warn "Removing old venv..."
            rm -rf "$VENV_DIR"
            info "Creating virtual environment..."
            "$PYTHON_CMD" -m venv "$VENV_DIR"
            success "Virtual environment created at $VENV_DIR/"
        fi
    else
        warn "Existing venv appears corrupted, removing..."
        rm -rf "$VENV_DIR"
        info "Creating virtual environment..."
        "$PYTHON_CMD" -m venv "$VENV_DIR"
        success "Virtual environment created at $VENV_DIR/"
    fi
else
    info "Creating virtual environment..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    success "Virtual environment created at $VENV_DIR/"
fi

# Install dependencies
info "Upgrading pip..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip --quiet

info "Installing from requirements.txt..."
if ! "$VENV_DIR/bin/pip" install -r requirements.txt --quiet; then
    error "Failed to install dependencies"
    echo ""
    echo "Common fixes:"
    echo "  - Check your internet connection"
    echo "  - Try running: $VENV_DIR/bin/pip install -r requirements.txt"
    exit 1
fi
success "Dependencies installed"

# Create output directory
if [[ ! -d "output" ]]; then
    mkdir -p output
    success "Created output/ directory"
else
    info "output/ directory already exists"
fi

# Fix run.sh for macOS compatibility
if [[ -f "run.sh" ]] && grep -q 'xargs -r' run.sh; then
    info "Patching run.sh for macOS compatibility..."

    # Create the replacement block
    NEW_BLOCK='# Kill any existing server on port 8000 (cross-platform)
pids=$(lsof -ti:8000 2>/dev/null) || true
if [ -n "$pids" ]; then
    echo "$pids" | xargs kill -9 2>/dev/null || true
fi'

    # Use sed to replace the problematic line
    if [[ "$OS" == "macos" ]]; then
        sed -i '' 's|# Kill any existing server on port 8000|# Kill any existing server on port 8000 (cross-platform)|' run.sh
        sed -i '' 's|lsof -ti:8000 | xargs -r kill -9 2>/dev/null|pids=$(lsof -ti:8000 2>/dev/null) || true\nif [ -n "$pids" ]; then\n    echo "$pids" | xargs kill -9 2>/dev/null || true\nfi|' run.sh
    else
        sed -i 's|# Kill any existing server on port 8000|# Kill any existing server on port 8000 (cross-platform)|' run.sh
        sed -i 's|lsof -ti:8000 | xargs -r kill -9 2>/dev/null|pids=$(lsof -ti:8000 2>/dev/null) || true\nif [ -n "$pids" ]; then\n    echo "$pids" | xargs kill -9 2>/dev/null || true\nfi|' run.sh
    fi
    success "run.sh patched for cross-platform compatibility"
fi

# Verify installation
info "Verifying installation..."
TEST_IMPORTS='
import sys
try:
    import cv2
    import numpy
    import fastapi
    import uvicorn
    import watchdog
    import kociemba
    sys.exit(0)
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)
'

if ! "$VENV_DIR/bin/python" -c "$TEST_IMPORTS"; then
    error "Verification failed - some packages may not be installed correctly"
    echo ""
    echo "Try running: $VENV_DIR/bin/pip install -r requirements.txt"
    exit 1
fi
success "All imports verified"

# Show installed versions
echo ""
"$VENV_DIR/bin/python" -c "
import cv2, numpy, fastapi, uvicorn
print('Installed versions:')
print(f'  opencv-python: {cv2.__version__}')
print(f'  numpy: {numpy.__version__}')
print(f'  fastapi: {fastapi.__version__}')
print(f'  uvicorn: {uvicorn.__version__}')
"

echo ""
echo -e "${GREEN}${BOLD}Setup complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Start the server:  ./run.sh"
echo "  2. Open browser:      http://localhost:8000"
echo ""
echo "Useful commands:"
echo "  Run pipeline once:    .venv/bin/python pipeline.py"
echo "  Capture single frame: .venv/bin/python capture.py"
