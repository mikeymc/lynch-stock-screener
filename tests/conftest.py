"""
Pytest fixtures for E2E browser automation tests.

This module provides session-scoped fixtures that start the backend and frontend
servers for testing.
"""

import pytest
import subprocess
import time
import requests
import os
from playwright.sync_api import Page


@pytest.fixture(scope="session")
def backend_server():
    """Use existing backend server or start a new one for the test session."""
    print("\n[E2E] Checking for existing backend server...")
    
    # Check if backend is already running
    try:
        response = requests.get('http://localhost:8080/api/health', timeout=2)
        if response.status_code == 200:
            print("[E2E] Using existing backend server on port 8080")
            yield None  # No process to manage
            return
    except (requests.ConnectionError, requests.Timeout):
        print("[E2E] No existing backend found, starting new one...")
    
    # Set environment variables for the backend
    env = os.environ.copy()
    env.update({
        'DB_HOST': 'localhost',
        'DB_PORT': '5432',
        'DB_NAME': 'lynch_stocks',
        'DB_USER': 'lynch',
        'DB_PASSWORD': 'lynch_dev_password',
        'FLASK_ENV': 'development'
    })
    
    # Start backend process
    backend_process = subprocess.Popen(
        ['python3', 'backend/app.py'],
        cwd='/Users/mikey/workspace/lynch-stock-screener',
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait for backend to be ready
    max_retries = 30
    for i in range(max_retries):
        try:
            response = requests.get('http://localhost:8080/api/health', timeout=2)
            if response.status_code == 200:
                print(f"[E2E] Backend ready after {i+1} attempts")
                break
        except (requests.ConnectionError, requests.Timeout):
            if i == max_retries - 1:
                # Get stderr output for debugging
                stderr_output = backend_process.stderr.read() if backend_process.stderr else "No stderr available"
                stdout_output = backend_process.stdout.read() if backend_process.stdout else "No stdout available"
                backend_process.kill()
                error_msg = f"Backend server failed to start.\nSTDOUT:\n{stdout_output}\nSTDERR:\n{stderr_output}"
                raise Exception(error_msg)
            time.sleep(1)
    
    yield backend_process
    
    # Cleanup
    print("\n[E2E] Stopping backend server...")
    backend_process.terminate()
    try:
        backend_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        backend_process.kill()


@pytest.fixture(scope="session")
def frontend_server():
    """Use existing frontend server or start a new one for the test session."""
    print("\n[E2E] Checking for existing frontend server...")
    
    # Check if frontend is already running
    try:
        response = requests.get('http://localhost:5173', timeout=2)
        if response.status_code == 200:
            print("[E2E] Using existing frontend server on port 5173")
            yield None  # No process to manage
            return
    except (requests.ConnectionError, requests.Timeout):
        print("[E2E] No existing frontend found, starting new one...")
    
    # Start frontend process
    frontend_process = subprocess.Popen(
        ['npm', 'run', 'dev'],
        cwd='/Users/mikey/workspace/lynch-stock-screener/frontend',
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for frontend to be ready
    max_retries = 30
    for i in range(max_retries):
        try:
            response = requests.get('http://localhost:5173', timeout=2)
            if response.status_code == 200:
                print(f"[E2E] Frontend ready after {i+1} attempts")
                break
        except (requests.ConnectionError, requests.Timeout):
            if i == max_retries - 1:
                frontend_process.kill()
                raise Exception("Frontend server failed to start")
            time.sleep(1)
    
    yield frontend_process
    
    # Cleanup
    print("\n[E2E] Stopping frontend server...")
    frontend_process.terminate()
    try:
        frontend_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        frontend_process.kill()


@pytest.fixture(scope="session")
def servers(backend_server, frontend_server):
    """Combined fixture to ensure both servers are running."""
    return {
        'backend': backend_server,
        'frontend': frontend_server
    }


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    Hook to capture test failures and take screenshots.
    
    This hook runs after each test phase (setup, call, teardown) and captures
    a screenshot if the test failed.
    """
    # Execute all other hooks to obtain the report object
    outcome = yield
    rep = outcome.get_result()
    
    # Only capture screenshots on test failures during the 'call' phase
    if rep.when == "call" and rep.failed:
        # Get the page fixture if it exists
        if "page" in item.funcargs:
            page = item.funcargs["page"]
            
            # Create screenshots directory if it doesn't exist
            screenshots_dir = "/Users/mikey/workspace/lynch-stock-screener/tests/screenshots"
            os.makedirs(screenshots_dir, exist_ok=True)
            
            # Generate filename with test name
            test_name = item.name.replace("[", "_").replace("]", "")
            screenshot_path = f"{screenshots_dir}/failure_{test_name}.png"
            
            try:
                page.screenshot(path=screenshot_path)
                print(f"\n[E2E] Screenshot saved on failure: {screenshot_path}")
            except Exception as e:
                print(f"\n[E2E] Failed to capture screenshot: {e}")
