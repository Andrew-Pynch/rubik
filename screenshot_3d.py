#!/usr/bin/env python3
"""Capture screenshot of 3D cube visualization using Playwright."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"


def is_server_running(port: int = 8000) -> bool:
    """Check if the server is already running on the given port."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def capture_3d_screenshot(
    url: str = "http://localhost:8000",
    output_path: str | Path = "output/cube3d.png",
    timeout: int = 10000,
) -> Path:
    """Capture screenshot of 3D cube visualization.

    Args:
        url: URL of the web debugger.
        output_path: Path to save the screenshot.
        timeout: Timeout in milliseconds for page load.

    Returns:
        Path to the saved screenshot.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        # Enable WebGL in headless mode
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--enable-webgl',
                '--use-gl=swiftshader',
                '--enable-features=Vulkan',
            ]
        )
        page = browser.new_page(viewport={"width": 1200, "height": 800})

        page.goto(url, timeout=timeout)

        # Wait for Three.js canvas to render
        page.wait_for_selector("canvas", state="visible", timeout=5000)

        # Extra time for WebGL to complete rendering
        page.wait_for_timeout(1000)

        # Capture full page screenshot
        page.screenshot(path=str(output_path))

        browser.close()

    return output_path


def capture_with_server(output_path: str | Path = "output/cube3d.png") -> Path:
    """Start server if needed, capture screenshot, then stop server.

    Args:
        output_path: Path to save the screenshot.

    Returns:
        Path to the saved screenshot.
    """
    server_was_running = is_server_running()
    server_process = None

    try:
        if not server_was_running:
            # Start server in background
            server_process = subprocess.Popen(
                [".venv/bin/uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(BASE_DIR),
            )
            # Wait for server to start
            for _ in range(30):
                if is_server_running():
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("Server failed to start")

        return capture_3d_screenshot(output_path=output_path)

    finally:
        if server_process is not None:
            server_process.terminate()
            server_process.wait(timeout=5)


if __name__ == "__main__":
    output = capture_with_server()
    print(f"Screenshot saved to: {output}")
