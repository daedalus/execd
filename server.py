"""
Server v3 - Parallel Async Task Execution
Supports any Python code, zip files, or git repos with custom entry points and parameters.
Files stored on disk in hash-named directories.
"""

from flask import Flask, request, jsonify
import time
import tempfile
import os
import subprocess
import hashlib
import sqlite3
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty
import base64
import zipfile
import shutil
import sys

# Python 3.11+ has tomllib built-in
try:
    import tomllib
except ImportError:
    try:
        import toml as tomllib
    except ImportError:
        tomllib = None

app = Flask(__name__)

# ============================================================================
# Configuration
# ============================================================================

DB_FILE = "/home/dclavijo/my_code/work_server/work.db"
WORK_FILES_DIR = "/home/dclavijo/my_code/work_server/work_files"
MAX_WORKERS = 4
work_queue = Queue()
executor = None
shutdown_event = threading.Event()

# Ensure work files directory exists
os.makedirs(WORK_FILES_DIR, exist_ok=True)


# ============================================================================
# pyproject.toml Parser
# ============================================================================

def parse_pyproject_toml(work_dir):
    """
    Parse pyproject.toml to extract entry point information.
    Returns dict with 'entry_point' and 'module' if found.
    """
    pyproject_path = os.path.join(work_dir, 'pyproject.toml')
    if not os.path.exists(pyproject_path):
        return None

    if tomllib is None:
        print("[Executor] Warning: tomllib not available, skipping pyproject.toml parsing")
        return None

    try:
        with open(pyproject_path, 'rb') as f:
            config = tomllib.load(f)

        entry_info = {}

        # Check [project.scripts] (PEP 621 style)
        project = config.get('project', {})
        scripts = project.get('scripts', {})
        if scripts:
            for name, entry in scripts.items():
                entry_info['entry_point'] = entry
                entry_info['script_name'] = name
                break

        # Check [tool.poetry.scripts] (Poetry style)
        if not entry_info:
            tool = config.get('tool', {})
            poetry = tool.get('poetry', {})
            scripts = poetry.get('scripts', {})
            if scripts:
                for name, entry in scripts.items():
                    entry_info['entry_point'] = entry
                    entry_info['script_name'] = name
                    break

        return entry_info if entry_info else None

    except Exception as e:
        print(f"[Executor] Error parsing pyproject.toml: {e}")
        return None


# ============================================================================
# Database Setup
# ============================================================================

def init_db():
    """Initialize SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS work_items (
            work_id TEXT PRIMARY KEY,
            code_type TEXT NOT NULL,
            status TEXT NOT NULL,
            result TEXT,
            created_at REAL NOT NULL,
            completed_at REAL,
            description TEXT DEFAULT '',
            run_time REAL,
            stdout TEXT,
            stderr TEXT,
            exit_code INTEGER,
            entry_point TEXT,
            params TEXT,
            file_hash TEXT,
            git_repo TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_work_item(work_id, code_type, status, file_hash=None, git_repo=None,
                   entry_point='main', params=None, description=""):
    """Save work item to database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    params_json = json.dumps(params) if params else None

    cursor.execute("""
        INSERT OR REPLACE INTO work_items
        (work_id, code_type, status, result, created_at, completed_at, description,
         run_time, stdout, stderr, exit_code, entry_point, params, file_hash, git_repo)
        VALUES (?, ?, ?, NULL, ?, NULL, ?, ?, NULL, NULL, NULL, ?, ?, ?, ?)
    """, (work_id, code_type, status, time.time(), description,
          entry_point, params_json, file_hash, git_repo))

    conn.commit()
    conn.close()


def update_work_status(work_id, status, result=None,
                      run_time=None, stdout=None, stderr=None, exit_code=None):
    """Update work status and optionally result."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    if result is not None:
        result_json = json.dumps(result)
        completed_at = time.time()
        cursor.execute("""
            UPDATE work_items
            SET status = ?, result = ?, completed_at = ?,
                run_time = ?, stdout = ?, stderr = ?, exit_code = ?
            WHERE work_id = ?
        """, (status, result_json, completed_at,
              run_time, stdout, stderr, exit_code, work_id))
    else:
        cursor.execute("""
            UPDATE work_items
            SET status = ?, run_time = ?, stdout = ?, stderr = ?, exit_code = ?
            WHERE work_id = ?
        """, (status, run_time, stdout, stderr, exit_code, work_id))

    conn.commit()
    conn.close()


def get_work_item(work_id):
    """Get work item from database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT work_id, code_type, status, result, created_at, completed_at, description, "
        "run_time, stdout, stderr, exit_code, entry_point, params, file_hash, git_repo FROM work_items WHERE work_id = ?",
        (work_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        (work_id, code_type, status, result_json, created_at, completed_at,
         description, run_time, stdout, stderr, exit_code, entry_point, params_json,
         file_hash, git_repo) = row
        result = json.loads(result_json) if result_json else None
        params = json.loads(params_json) if params_json else {}
        return {
            'work_id': work_id,
            'code_type': code_type,
            'status': status,
            'result': result,
            'created_at': created_at,
            'completed_at': completed_at,
            'description': description or '',
            'run_time': run_time,
            'stdout': stdout or '',
            'stderr': stderr or '',
            'exit_code': exit_code,
            'entry_point': entry_point or 'main',
            'params': params or {},
            'file_hash': file_hash,
            'git_repo': git_repo
        }
    return None


def load_pending_work():
    """Load pending work from database and re-queue."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT work_id, code_type, status, description FROM work_items WHERE status IN ('queued', 'running')"
    )
    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        work_id, code_type, status, description = row
        print(f"[Server] Requeuing {work_id[:8]} (was {status})...")
        work_queue.put(work_id)


# ============================================================================
# Code Execution Engine
# ============================================================================

def setup_work_directory(item):
    """Set up temporary directory with code, zip, or git repo."""
    temp_dir = tempfile.mkdtemp(prefix='work_')

    try:
        if item.get('git_repo'):
            # Clone git repo
            print(f"[Executor] Cloning git repo: {item['git_repo']}")
            result = subprocess.run(
                ['git', 'clone', item['git_repo'], temp_dir],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode != 0:
                return None, f"Git clone failed: {result.stderr}"

        elif item.get('file_hash'):
            # Copy files from hash-named directory
            file_hash = item['file_hash']
            source_dir = os.path.join(WORK_FILES_DIR, file_hash)

            if not os.path.exists(source_dir):
                return None, f"File directory not found: {source_dir}"

            print(f"[Executor] Loading files from {source_dir}")
            shutil.copytree(source_dir, temp_dir, dirs_exist_ok=True)

        return temp_dir, None

    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None, str(e)


def find_entry_point(temp_dir, entry_point):
    """Find and prepare the entry point for execution."""
    # First, try to parse pyproject.toml for entry point
    pyproject_info = parse_pyproject_toml(temp_dir)
    if pyproject_info and 'entry_point' in pyproject_info:
        entry = pyproject_info['entry_point']
        print(f"[Executor] Found entry point from pyproject.toml: {entry}")

        # Parse "module:function" format
        if ':' in entry:
            module_path, func_name = entry.split(':', 1)
            module_file = module_path.replace('.', '/') + '.py'
            entry_file = os.path.join(temp_dir, module_file)
            if os.path.isfile(entry_file):
                return entry_file, None

    # If entry_point is a file path, return it
    if entry_point:
        entry_file = os.path.join(temp_dir, entry_point)
        if os.path.isfile(entry_file):
            return entry_file, None

    # Look for Python files
    py_files = []
    for root, dirs, files in os.walk(temp_dir):
        for f in files:
            if f.endswith('.py'):
                py_files.append(os.path.join(root, f))

    if not py_files:
        return None, "No Python files found"

    return py_files[0], None


def execute_code(item):
    """Execute the submitted code with parameters."""
    temp_dir = None
    start_time = time.time()

    try:
        temp_dir, error = setup_work_directory(item)
        if not temp_dir:
            return {
                'score': 0.0,
                'correct': False,
                'error': error,
                'stdout': '',
                'stderr': error,
                'exit_code': -1,
                'run_time': time.time() - start_time
            }

        entry_file, error = find_entry_point(temp_dir, item.get('entry_point', 'main'))
        if not entry_file:
            return {
                'score': 0.0,
                'correct': False,
                'error': error,
                'stdout': '',
                'stderr': error,
                'exit_code': -1,
                'run_time': time.time() - start_time
            }

        params = item.get('params', {})
        params_json = json.dumps(params)

        exec_script = f'''#!/usr/bin/env python3
import sys
import json
import importlib.util

sys.path.insert(0, '{temp_dir}')

params = json.loads('{params_json}')

try:
    spec = importlib.util.spec_from_file_location("entry_module", "{entry_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    entry_point = "{item.get('entry_point', 'main')}"

    if hasattr(module, entry_point):
        func = getattr(module, entry_point)
        result = func(**params) if params else func()
    elif hasattr(module, 'main'):
        result = module.main(**params) if params else module.main()
    else:
        result = {{"error": "No entry point found"}}

    print(json.dumps(result if isinstance(result, dict) else {{"result": result}}))

except Exception as e:
    print(json.dumps({{"error": str(e), "correct": False, "score": 0.0}}))
'''

        script_path = os.path.join(temp_dir, '_executor.py')
        with open(script_path, 'w') as f:
            f.write(exec_script)

        result = subprocess.run(
            ['python3', script_path],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=temp_dir
        )

        end_time = time.time()
        run_time = end_time - start_time

        try:
            output = json.loads(result.stdout.strip())
        except:
            output = {
                'stdout': result.stdout[:1000],
                'stderr': result.stderr[:1000],
                'exit_code': result.returncode,
                'run_time': run_time
            }

        return {
            'score': output.get('score', 0.0),
            'correct': output.get('correct', True),
            'error': output.get('error'),
            'stdout': result.stdout[:1000],
            'stderr': result.stderr[:1000],
            'exit_code': result.returncode,
            'run_time': run_time,
            'result': output
        }

    except subprocess.TimeoutExpired:
        return {
            'score': 0.0,
            'correct': False,
            'error': 'Timeout',
            'stdout': '',
            'stderr': '',
            'exit_code': -1,
            'run_time': time.time() - start_time
        }
    except Exception as e:
        return {
            'score': 0.0,
            'correct': False,
            'error': str(e),
            'stdout': '',
            'stderr': str(e),
            'exit_code': -1,
            'run_time': time.time() - start_time
        }
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================================
# Worker Threads (Parallel Execution)
# ============================================================================

def worker(worker_id):
    """Worker thread that processes queued work in parallel."""
    print(f"[Worker {worker_id}] Started")

    while not shutdown_event.is_set():
        try:
            work_id = work_queue.get(timeout=1)
        except Empty:
            continue

        item = get_work_item(work_id)
        if not item:
            print(f"[Worker {worker_id}] Work {work_id[:8]} not found in DB!")
            continue

        print(f"[Worker {worker_id}] Processing {work_id[:8]}...")

        update_work_status(work_id, 'running')

        result = execute_code(item)

        status = 'completed' if result.get('correct', True) else 'failed'
        update_work_status(work_id, status, result)

        print(f"[Worker {worker_id}] Completed {work_id[:8]}: {status}")

    print(f"[Worker {worker_id}] Stopped")


# ============================================================================
# API Endpoints
# ============================================================================

@app.route('/api/submit', methods=['POST'])
def submit_work():
    """Submit a new work item for execution.
    Supports both JSON and multipart/form-data.
    For multipart: use 'file' field for code files or zip files.
    Files are stored in hash-named directories on disk.
    """
    # Handle multipart form data
    if request.content_type and 'multipart/form-data' in request.content_type:
        entry_point = request.form.get('entry_point', 'main')
        params_str = request.form.get('params', '{}')
        description = request.form.get('description', '')

        try:
            params = json.loads(params_str)
        except:
            params = {}

        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        filename = file.filename
        file_data = file.read()

        file_hash = hashlib.sha256(file_data).hexdigest()[:16]

        file_dir = os.path.join(WORK_FILES_DIR, file_hash)
        if not os.path.exists(file_dir):
            os.makedirs(file_dir, exist_ok=True)
            file_path = os.path.join(file_dir, filename)
            with open(file_path, 'wb') as f:
                f.write(file_data)

            if filename.endswith('.zip'):
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(file_dir)
                os.unlink(file_path)

        code_type = 'zip' if filename.endswith('.zip') else 'code'
        work_id = file_hash
        git_repo = None

    else:
        data = request.json
        if not data:
            return jsonify({'error': 'Missing data'}), 400

        code = data.get('code')
        git_repo = data.get('git_repo')
        entry_point = data.get('entry_point', 'main')
        params = data.get('params', {})
        description = data.get('description', '')

        if not code and not git_repo:
            return jsonify({'error': 'Must provide code or git_repo'}), 400

        if git_repo:
            code_type = 'git'
            work_id = hashlib.sha256(git_repo.encode('utf-8')).hexdigest()[:16]
            file_hash = None
        else:
            code_type = 'code'
            work_id = hashlib.sha256(code.encode('utf-8')).hexdigest()[:16]
            file_hash = work_id

            code_dir = os.path.join(WORK_FILES_DIR, file_hash)
            if not os.path.exists(code_dir):
                os.makedirs(code_dir, exist_ok=True)
                with open(os.path.join(code_dir, 'main.py'), 'w') as f:
                    f.write(code)

    existing = get_work_item(work_id)
    if existing:
        print(f"[API] Duplicate work {work_id[:8]} - returning existing")
        return jsonify({
            'work_id': work_id,
            'status': existing['status'],
            'description': existing.get('description', ''),
            'message': 'Work already exists',
            'is_duplicate': True
        })

    save_work_item(work_id, code_type, 'queued', file_hash=file_hash,
                   git_repo=git_repo, entry_point=entry_point, params=params,
                   description=description)

    work_queue.put(work_id)

    print(f"[API] Submitted work {work_id[:8]} - {description}...")
    return jsonify({
        'work_id': work_id,
        'status': 'queued',
        'description': description,
        'message': 'Work submitted successfully',
        'is_duplicate': False
    })


@app.route('/api/status/<work_id>', methods=['GET'])
def get_status(work_id):
    """Get the status of a work item."""
    item = get_work_item(work_id)

    if not item:
        return jsonify({'error': 'Work not found'}), 404

    response = {
        'work_id': item['work_id'],
        'status': item['status'],
        'created_at': item['created_at'],
        'description': item.get('description', ''),
        'run_time': item.get('run_time'),
        'exit_code': item.get('exit_code'),
        'entry_point': item.get('entry_point'),
        'code_type': item.get('code_type'),
        'stdout_preview': item.get('stdout', '')[:200] if item.get('stdout') else '',
        'stderr_preview': item.get('stderr', '')[:200] if item.get('stderr') else ''
    }

    if item['completed_at']:
        response['completed_at'] = item['completed_at']
        response['runtime_seconds'] = item['completed_at'] - item['created_at']

    if item['result']:
        response['result'] = item['result']

    return jsonify(response)


@app.route('/api/result/<work_id>', methods=['GET'])
def get_result(work_id):
    """Get the result of a completed work item with full execution details."""
    item = get_work_item(work_id)

    if not item:
        return jsonify({'error': 'Work not found'}), 404

    if item['status'] not in ['completed', 'failed']:
        return jsonify({
            'work_id': item['work_id'],
            'status': item['status'],
            'description': item.get('description', ''),
            'message': 'Work not yet completed',
            'run_time': item.get('run_time'),
            'exit_code': item.get('exit_code')
        }), 202

    return jsonify({
        'work_id': item['work_id'],
        'status': item['status'],
        'description': item.get('description', ''),
        'result': item.get('result'),
        'stdout': item.get('stdout', ''),
        'stderr': item.get('stderr', ''),
        'exit_code': item.get('exit_code'),
        'run_time': item.get('run_time'),
        'created_at': item.get('created_at'),
        'completed_at': item.get('completed_at')
    })


@app.route('/api/list', methods=['GET'])
def list_work():
    """List all work items with description."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT work_id, status, created_at, completed_at, description, code_type, entry_point
        FROM work_items ORDER BY created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    items = []
    for row in rows:
        work_id, status, created_at, completed_at, description, code_type, entry_point = row
        item = {
            'work_id': work_id,
            'status': status,
            'created_at': created_at,
            'description': description or '',
            'code_type': code_type,
            'entry_point': entry_point
        }
        if completed_at:
            item['completed_at'] = completed_at
            item['has_result'] = True
        else:
            item['has_result'] = False
        items.append(item)

    return jsonify({'count': len(items), 'items': items})


@app.route('/api/health', methods=['GET'])
def health():
    """Health check."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM work_items")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM work_items WHERE status = 'queued'")
    queued = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM work_items WHERE status = 'running'")
    running = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM work_items WHERE status = 'completed'")
    completed = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM work_items WHERE status = 'failed'")
    failed = cursor.fetchone()[0]
    conn.close()

    return jsonify({
        'status': 'healthy',
        'database': DB_FILE,
        'queue_size': queued,
        'running': running,
        'completed': completed,
        'failed': failed,
        'total': total,
        'max_workers': MAX_WORKERS
    })


# ============================================================================
# Main
# ============================================================================

if __name__ == '__main__':
    init_db()
    load_pending_work()

    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    for i in range(MAX_WORKERS):
        executor.submit(worker, i+1)

    print("=" * 70)
    print("Server v3 - Parallel Async Task Execution")
    print("=" * 70)
    print(f"\nDatabase: {DB_FILE}")
    print(f"Work files: {WORK_FILES_DIR}")
    print(f"\nAPI Endpoints:")
    print("  POST /api/submit - Submit work (multipart: file + params)")
    print("  GET  /api/status/<work_id> - Get work status")
    print("  GET  /api/result/<work_id> - Get work result")
    print("  GET  /api/list - List all work items")
    print("  GET  /api/health - Health check")
    print(f"\nServer starting on http://0.0.0.0:5000")
    print(f"Parallel workers: {MAX_WORKERS}")
    print("Press Ctrl+C to stop and save state to disk")
    print("=" * 70)

    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        print("\n[Server] Received Ctrl+C, shutting down...")
        shutdown_event.set()
        executor.shutdown(wait=True)
        print("[Server] State saved. Exiting gracefully.")
        os._exit(0)
