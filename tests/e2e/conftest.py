"""
Pytest fixtures for E2E browser automation tests.

This module provides session-scoped fixtures that start the backend and frontend
servers for testing.

Note: test_database fixture is defined in tests/conftest.py (shared)
"""

import pytest
import subprocess
import time
import requests
import os
import psycopg2
from playwright.sync_api import Page


@pytest.fixture(scope="session")
def backend_server(test_database):
    """Start isolated backend server for tests on port 8081 with test database."""
    print("\n[E2E] Starting isolated backend server for tests...")

    # Use port 8081 for test backend to avoid conflicts with dev server
    test_port = 8081

    # Set environment variables for the backend
    env = os.environ.copy()
    env.update({
        'DB_HOST': 'localhost',
        'DB_PORT': '5432',
        'DB_NAME': test_database,
        'DB_USER': 'lynch',
        'DB_PASSWORD': 'lynch_dev_password',
        'FLASK_ENV': 'development',
        'PORT': str(test_port),
        'ENABLE_TEST_AUTH': 'true',
        'DB_POOL_SIZE': '10'  # Smaller pool for tests
    })
    print(f"[E2E] Starting backend on port {test_port} with test database: {test_database}")
    print(f"[E2E] Environment: DB_NAME={env['DB_NAME']}, DB_HOST={env['DB_HOST']}, PORT={env['PORT']}")

    # Start backend process using the venv python
    # Note: stdout=None, stderr=None allows backend output to print to console for debugging
    # Get project root (two directories up from this conftest.py file)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    venv_python = os.path.join(project_root, 'backend', '.venv', 'bin', 'python3')

    backend_process = subprocess.Popen(
        [venv_python, 'backend/app.py'],
        cwd=project_root,
        env=env,
        stdout=None,  # Let backend print to console
        stderr=None,  # Let backend errors print to console
        text=True
    )

    # Wait for backend to be ready
    max_retries = 30
    for i in range(max_retries):
        try:
            response = requests.get(f'http://localhost:{test_port}/api/health', timeout=2)
            if response.status_code == 200:
                print(f"[E2E] Backend ready after {i+1} attempts on port {test_port}")
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
    """Start isolated frontend server for tests on port 5174."""
    print("\n[E2E] Starting isolated frontend server for tests...")

    # Use port 5174 for test frontend to avoid conflicts with dev server
    test_port = 5174

    # Set environment variables for the frontend
    env = os.environ.copy()
    env.update({
        'PORT': str(test_port),
        'VITE_API_URL': 'http://localhost:8081'  # Point to test backend on 8081
    })

    print(f"[E2E] Starting frontend on port {test_port}, pointing to backend on port 8081")

    # Start frontend process
    # Get project root (two directories up from this conftest.py file)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    frontend_dir = os.path.join(project_root, 'frontend')

    frontend_process = subprocess.Popen(
        ['npm', 'run', 'dev', '--', '--port', str(test_port)],
        cwd=frontend_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Wait for frontend to be ready
    max_retries = 30
    for i in range(max_retries):
        try:
            response = requests.get(f'http://localhost:{test_port}', timeout=2)
            if response.status_code == 200:
                print(f"[E2E] Frontend ready after {i+1} attempts on port {test_port}")
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


@pytest.fixture(scope="function", autouse=True)
def clear_test_session_data(test_database, page, servers):
    """Clear session data before each test to ensure clean state."""
    # This fixture runs before each test function
    # It clears data that might persist across tests within the session

    # Connect to test database
    conn = psycopg2.connect(
        database=test_database,
        user='lynch',
        password='lynch_dev_password',
        host='localhost',
        port=5432
    )
    cursor = conn.cursor()

    # Clear only session-specific data that tests might modify
    # DO NOT clear screening_results/screening_sessions - those are stable test data
    cursor.execute('DELETE FROM app_settings')
    cursor.execute('DELETE FROM watchlist')
    cursor.execute('DELETE FROM conversations')
    cursor.execute('DELETE FROM messages')
    cursor.execute('DELETE FROM message_sources')

    conn.commit()
    cursor.close()
    conn.close()

    # Clear browser storage (localStorage and sessionStorage)
    # This ensures filters don't persist in the browser between tests
    try:
        page.goto("http://localhost:5174")
        page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
    except Exception as e:
        # Ignore errors if page hasn't loaded yet
        pass

    # Perform test login to authenticate the session
    print("[E2E] Performing test login...")
    try:
        response = requests.post('http://localhost:8081/api/auth/test-login')
        if response.status_code == 200:
            print("[E2E] Test login successful")
            # Get session cookie from response and set it in the browser
            if 'set-cookie' in response.headers:
                cookies = response.cookies
                # Navigate to the app domain first so we can set cookies
                page.goto("http://localhost:5174")
                # Set each cookie in the browser context
                for cookie_name, cookie_value in cookies.items():
                    page.context.add_cookies([{
                        'name': cookie_name,
                        'value': cookie_value,
                        'domain': 'localhost',
                        'path': '/'
                    }])
                print(f"[E2E] Set {len(cookies)} authentication cookies in browser")
        else:
            print(f"[E2E] Test login failed with status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[E2E] Test login error: {e}")

    # Test runs here (yield allows test to execute)
    yield

    # Cleanup after test (if needed) - currently none


def pytest_collection_modifyitems(items):
    """Automatically add 'e2e' marker to all tests in this directory."""
    for item in items:
        if "tests/e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)


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
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            screenshots_dir = os.path.join(project_root, 'tests', 'screenshots')
            os.makedirs(screenshots_dir, exist_ok=True)

            # Generate filename with test name
            test_name = item.name.replace("[", "_").replace("]", "")
            screenshot_path = f"{screenshots_dir}/failure_{test_name}.png"

            try:
                page.screenshot(path=screenshot_path)
                print(f"\n[E2E] Screenshot saved on failure: {screenshot_path}")
            except Exception as e:
                print(f"\n[E2E] Failed to capture screenshot: {e}")
