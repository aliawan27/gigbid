"""Start every GigBid service as child processes (local dev and the single-container deployment).
docker compose runs them as separate containers instead (infra/docker-compose.yml)."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

PY = sys.executable
PORT = os.getenv("PORT", "8000")
SERVICES = {
    "gigsim": [PY, "-m", "uvicorn", "gigsim.app:app", "--host", "0.0.0.0", "--port", "8081", "--log-level", "warning"],
    "portfolio": [PY, "-m", "mcp_servers.portfolio.server", "--http", "8091"],
    "marketplace": [PY, "-m", "mcp_servers.marketplace.server", "--http", "8092"],
    "workspace": [PY, "-m", "mcp_servers.workspace.server", "--http", "8093"],
    "worker": [PY, "-m", "worker.main"],
    "api": [PY, "-m", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", PORT, "--log-level", "warning"],
}


def main(only: list[str]):
    os.makedirs("logs", exist_ok=True)
    env = {**os.environ, "PYTHONPATH": os.getcwd(), "PYTHONUNBUFFERED": "1"}
    procs = {}
    for name, cmd in SERVICES.items():
        if only and name not in only:
            continue
        procs[name] = subprocess.Popen(cmd, env=env, stdout=open(f"logs/{name}.log", "a"), stderr=subprocess.STDOUT)
        print(f"started {name} (pid {procs[name].pid})", flush=True)
        if name == "workspace":
            time.sleep(6)  # let MCP servers bind before worker/api
    try:
        while True:
            for name, p in list(procs.items()):
                if p.poll() is not None and name != "marketplace_killed":
                    print(f"{name} exited ({p.returncode}); restarting", flush=True)
                    procs[name] = subprocess.Popen(SERVICES[name], env=env, stdout=open(f"logs/{name}.log", "a"),
                                                   stderr=subprocess.STDOUT)
            time.sleep(3)
    except KeyboardInterrupt:
        for p in procs.values():
            p.send_signal(signal.SIGTERM)


if __name__ == "__main__":
    main(sys.argv[1:])
