from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP_PATH = PROJECT_ROOT / "app.py"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Smoke-check the P5 Streamlit dashboard.")
    parser.add_argument("--app", default=str(DEFAULT_APP_PATH), help="Streamlit app path.")
    parser.add_argument("--host", default="localhost", help="Host used for health checks.")
    parser.add_argument("--port", type=int, default=8501, help="Streamlit port.")
    parser.add_argument("--timeout", type=float, default=60.0, help="Seconds to wait for health check.")
    parser.add_argument(
        "--keep-running",
        action="store_true",
        help="Leave the Streamlit server running after the health check passes.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    health_url = f"http://{args.host}:{args.port}/_stcore/health"
    if _health_ok(health_url):
        print(f"p5_dashboard_health=ok url=http://{args.host}:{args.port}")
        return 0

    command = _streamlit_command(Path(args.app), args.port)
    process = _start_streamlit(command, keep_running=args.keep_running)
    try:
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = _read_output(process)
                print(f"p5_dashboard_health=failed exit_code={process.returncode}")
                if output:
                    print(output)
                return process.returncode or 1
            if _health_ok(health_url):
                print(f"p5_dashboard_health=ok url=http://{args.host}:{args.port} pid={process.pid}")
                return 0
            time.sleep(1.0)

        print(f"p5_dashboard_health=timeout url={health_url}")
        return 1
    finally:
        if not args.keep_running and process.poll() is None:
            _stop_process(process)


def _streamlit_command(app_path: Path, port: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.headless=true",
        f"--server.port={port}",
        "--browser.gatherUsageStats=false",
    ]


def _start_streamlit(command: list[str], *, keep_running: bool) -> subprocess.Popen:
    if keep_running:
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        return subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )

    return subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _health_ok(url: str) -> bool:
    try:
        with urlopen(url, timeout=2.0) as response:
            return response.status == 200 and response.read().decode("utf-8").strip() == "ok"
    except (OSError, URLError):
        return False


def _read_output(process: subprocess.Popen) -> str:
    if process.stdout is None:
        return ""
    return process.stdout.read().strip()


def _stop_process(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5.0)


if __name__ == "__main__":
    raise SystemExit(main())
