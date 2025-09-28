"""Launcher to start uvicorn in background with API_KEY set and logs redirected.

Usage: run with the venv python from repository root or any location; it will start uvicorn
with cwd set to the echo-bridge directory so imports work correctly.
"""
import os
import subprocess
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
echo_dir = repo_root
# ensure we point to the echo-bridge directory
cwd = echo_dir
venv_python = cwd / ".venv" / "Scripts" / "python.exe"
if not venv_python.exists():
    # fallback to system python
    venv_python = Path("python")

env = os.environ.copy()
# For testing we want to allow unauthenticated calls. Ensure API_KEY is not set
# in the child process so bridge_echo_generate won't require the X-API-Key header.
env.pop("API_KEY", None)

# Place logs inside the echo-bridge directory to avoid permission issues
out_log = cwd / "uvicorn.out.log"
err_log = cwd / "uvicorn.err.log"
# open files in append mode
out_f = open(out_log, "a", encoding="utf-8")
err_f = open(err_log, "a", encoding="utf-8")

cmd = [str(venv_python), "-m", "uvicorn", "echo_bridge.main:app", "--host", "0.0.0.0", "--port", "3333"]
print(f"Starting: {cmd} cwd={cwd}")
proc = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdout=out_f, stderr=err_f)
print(f"Started pid={proc.pid}")
# close file handles in parent; child keeps them
out_f.close()
err_f.close()
