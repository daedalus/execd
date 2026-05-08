"""
Work Server Client - Sends work to server and fetches results.
Supports file upload via multipart, parameters, and git repos.
"""

import requests
import time
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import os
import json

# ============================================================================
# Configuration
# ============================================================================

SERVER_URL = "http://localhost:5000"


@dataclass
class Program:
    work_id: str = ""
    score: float = 0.0
    generation: int = 0
    runtime: float = 0.0
    correct: bool = False
    description: str = ""
    status: str = ""


# ============================================================================
# Server Communication
# ============================================================================

def submit_file(file_path: str, entry_point: str = 'main',
                params: Dict[str, Any] = None, description: str = "") -> Optional[str]:
    """Submit a file (Python or zip) to server via multipart upload."""
    if not os.path.exists(file_path):
        print(f"  [Client] File not found: {file_path}")
        return None

    try:
        files = {'file': open(file_path, 'rb')}
        data = {
            'entry_point': entry_point,
            'params': json.dumps(params or {}),
            'description': description
        }

        response = requests.post(
            f"{SERVER_URL}/api/submit",
            files=files,
            data=data,
            timeout=30
        )
        files['file'].close()

        if response.status_code == 200:
            result = response.json()
            work_id = result['work_id']
            print(f"  [Client] Submitted work {work_id[:8]}...")
            return work_id
        else:
            print(f"  [Client] Submit failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"  [Client] Error submitting file: {e}")
        return None


def submit_code(code: str, entry_point: str = 'main',
                params: Dict[str, Any] = None, description: str = "") -> Optional[str]:
    """Submit inline code to server."""
    try:
        payload = {
            'code': code,
            'entry_point': entry_point,
            'params': params or {},
            'description': description
        }

        response = requests.post(
            f"{SERVER_URL}/api/submit",
            json=payload,
            timeout=10
        )

        if response.status_code == 200:
            result = response.json()
            work_id = result['work_id']
            print(f"  [Client] Submitted work {work_id[:8]}...")
            return work_id
        else:
            print(f"  [Client] Submit failed: {response.status_code}")
            return None
    except Exception as e:
        print(f"  [Client] Error submitting code: {e}")
        return None


def submit_git_repo(git_repo: str, entry_point: str = 'main',
                    params: Dict[str, Any] = None, description: str = "") -> Optional[str]:
    """Submit a git repo URL to server."""
    try:
        payload = {
            'git_repo': git_repo,
            'entry_point': entry_point,
            'params': params or {},
            'description': description
        }

        response = requests.post(
            f"{SERVER_URL}/api/submit",
            json=payload,
            timeout=10
        )

        if response.status_code == 200:
            result = response.json()
            work_id = result['work_id']
            print(f"  [Client] Submitted git repo {work_id[:8]}...")
            return work_id
        else:
            print(f"  [Client] Submit failed: {response.status_code}")
            return None
    except Exception as e:
        print(f"  [Client] Error submitting git repo: {e}")
        return None


def poll_for_result(work_id: str, timeout=300, poll_interval=5) -> Optional[dict]:
    """Poll server for work result."""
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            response = requests.get(
                f"{SERVER_URL}/api/status/{work_id}",
                timeout=10
            )

            if response.status_code == 404:
                print(f"  [Client] Work {work_id[:8]} not found!")
                return None

            data = response.json()
            status = data['status']

            if status == 'completed':
                print(f"  [Client] Work {work_id[:8]} completed!")
                result_response = requests.get(
                    f"{SERVER_URL}/api/result/{work_id}",
                    timeout=10
                )
                if result_response.status_code == 200:
                    return result_response.json()
                return None

            elif status == 'failed':
                print(f"  [Client] Work {work_id[:8]} failed!")
                return data.get('result', {'score': 0.0, 'correct': False, 'error': 'Failed'})

            else:
                print(f"  [Client] Work {work_id[:8]} status: {status}...")

        except Exception as e:
            print(f"  [Client] Error polling: {e}")

        time.sleep(poll_interval)

    print(f"  [Client] Timeout waiting for {work_id[:8]}")
    return None


def check_server_health() -> bool:
    """Check if server is running."""
    try:
        response = requests.get(f"{SERVER_URL}/api/health", timeout=5)
        return response.status_code == 200
    except:
        return False


# ============================================================================
# Example Usage
# ============================================================================

def example_submit_python_file():
    """Example: Submit a Python file."""
    print("=" * 70)
    print("Example: Submit Python File")
    print("=" * 70)

    # Create a test file
    test_code = '''
def main(name="World"):
    """Entry point for the program."""
    return {
        "message": f"Hello, {name}!",
        "score": 1.0,
        "correct": True
    }
'''

    with open('/tmp/test_program.py', 'w') as f:
        f.write(test_code)

    # Submit with parameters
    work_id = submit_file(
        '/tmp/test_program.py',
        entry_point='main',
        params={'name': 'Server'},
        description='Test Python file'
    )

    if work_id:
        result = poll_for_result(work_id, timeout=60)
        if result:
            print(f"  Result: {result}")

    os.unlink('/tmp/test_program.py')


def example_submit_zip():
    """Example: Submit a zip file with pyproject.toml."""
    print("=" * 70)
    print("Example: Submit Zip File")
    print("=" * 70)

    import zipfile

    # Create a test zip with pyproject.toml
    zip_path = '/tmp/test_project.zip'

    with zipfile.ZipFile(zip_path, 'w') as zf:
        # Add pyproject.toml
        pyproject = '''
[project]
name = "test-project"
version = "0.1.0"

[project.scripts]
run = "main:main"
'''
        zf.writestr('pyproject.toml', pyproject)

        # Add main.py
        main_code = '''
def main():
    return {"score": 1.0, "correct": True, "message": "From zip file!"}
'''
        zf.writestr('main.py', main_code)

    # Submit the zip
    work_id = submit_file(
        zip_path,
        description='Test zip with pyproject.toml'
    )

    if work_id:
        result = poll_for_result(work_id, timeout=60)
        if result:
            print(f"  Result: {result}")

    os.unlink(zip_path)


def example_submit_git():
    """Example: Submit a git repository."""
    print("=" * 70)
    print("Example: Submit Git Repo")
    print("=" * 70)

    work_id = submit_git_repo(
        'https://github.com/example/repo.git',
        entry_point='main',
        description='Test git repo'
    )

    if work_id:
        result = poll_for_result(work_id, timeout=300)
        if result:
            print(f"  Result: {result}")


def main():
    print("=" * 70)
    print("Work Server Client")
    print("=" * 70)

    # Check server health
    print("\nChecking server...")
    if not check_server_health():
        print(f"ERROR: Server not running at {SERVER_URL}")
        print(f"Start the server first: python3 server_v3.py")
        return

    print("Server is healthy!\n")

    # Run examples
    example_submit_python_file()
    print()
    example_submit_zip()

    print("\n" + "=" * 70)
    print("Done!")
    print("=" * 70)


if __name__ == '__main__':
    main()
