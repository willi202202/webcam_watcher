#!/usr/bin/env python3
"""Webcam watcher + control API (Flask) in one process.

Endpoints:
  GET  /webcam/status
  POST /webcam/start
  POST /webcam/stop

Notes:
- No status file is written anymore.
- Watcher runs in a background thread.
- Config is reloaded from JSON on each start.
"""
from __future__ import annotations

import json
import signal
import subprocess
import time
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Set

import requests
from flask import Flask, jsonify


CONFIG_FILE = Path(r"/home/raspiroman/project/webcam_watcher/webcam_config.json")


@dataclass
class WatcherStatus:
    timestamp_utc: str
    watcher_running: bool
    webcam_online: Optional[bool]
    last_alarm_utc: Optional[str]
    last_webcam_change_utc: Optional[str]
    known_files_count: int


class WebcamWatcher:
    def __init__(self, config_path: Path):
        self.config_path = config_path

        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

        self.conf: dict = {}

        self._known_files: Set[str] = set()
        self._last_alarm: Optional[datetime] = None
        self._last_webcam_ok: Optional[bool] = None
        self._last_webcam_change: Optional[datetime] = None

    def load_config(self) -> dict:
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def _send_ntfy(self, message: str, priority=None, title=None) -> None:
        conf = self.conf
        url = f"{conf['ntfy_server']}/{conf['ntfy_topic']}"
        headers = {}
        headers["X-Title"] = title or conf.get("ntfy_title", "Webcam Alarm")
        if priority is not None:
            headers["X-Priority"] = str(priority)

        try:
            r = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=8)
            r.raise_for_status()
            print(f"[{datetime.now()}] ntfy sent: {message}")
        except Exception as e:
            print(f"[WARN] ntfy failed: {e}")

    def _send_motion_alarm(self) -> None:
        conf = self.conf
        prio = conf.get("ntfy_priority", 3)
        msg = conf.get("message", "Motion detected")
        self._send_ntfy(msg, priority=prio, title=conf.get("ntfy_title", "Webcam Alarm"))

    @staticmethod
    def _scan_directory(dir_path: Path, valid_exts: Set[str]) -> Set[str]:
        return {
            p.name
            for p in dir_path.iterdir()
            if p.is_file() and p.suffix.lower() in valid_exts
        }

    @staticmethod
    def _check_webcam_online(ip: str) -> bool:
        try:
            r = subprocess.run(
                ["ping", "-c", "1", "-W", "2", ip],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return r.returncode == 0
        except Exception:
            return False

    def start(self) -> bool:
        """Start the watcher thread (no-op if already running)."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False

            self.conf = self.load_config()
            self._stop.clear()

            self._thread = threading.Thread(target=self._run, name="WebcamWatcher", daemon=True)
            self._thread.start()
            return True

    def stop(self, timeout_s: float = 5.0) -> bool:
        """Request stop and wait briefly."""
        with self._lock:
            t = self._thread
            if not (t and t.is_alive()):
                return False
            self._stop.set()

        t.join(timeout=timeout_s)
        return not t.is_alive()

    def is_running(self) -> bool:
        t = self._thread
        return bool(t and t.is_alive())

    def status(self) -> WatcherStatus:
        now = datetime.now(timezone.utc)
        return WatcherStatus(
            timestamp_utc=now.isoformat(),
            watcher_running=self.is_running(),
            webcam_online=self._last_webcam_ok,
            last_alarm_utc=self._last_alarm.isoformat() if self._last_alarm else None,
            last_webcam_change_utc=self._last_webcam_change.isoformat() if self._last_webcam_change else None,
            known_files_count=len(self._known_files),
        )

    def _run(self) -> None:
        conf = self.conf

        watch_dir = Path(conf["watch_dir"])
        webcam_ip = conf["webcam_ip"]
        check_interval = int(conf.get("check_interval_seconds", 5))
        min_alarm_interval = timedelta(minutes=int(conf.get("min_alarm_interval_minutes", 10)))
        valid_exts = set(ext.lower() for ext in conf["valid_extensions"])

        print(f"[INFO] Watching: {watch_dir}")

        if not watch_dir.exists():
            print(f"[ERROR] Directory does not exist: {watch_dir}")
            return

        # existing files are known
        try:
            self._known_files = self._scan_directory(watch_dir, valid_exts)
            print(f"[INFO] {len(self._known_files)} existing files marked as known.")
        except Exception as e:
            print(f"[WARN] initial scan failed: {e}")
            self._known_files = set()

        last_alarm_time = datetime.min.replace(tzinfo=timezone.utc)
        self._last_alarm = None
        self._last_webcam_ok = None
        self._last_webcam_change = None

        self._send_ntfy("Webcam-Watcher gestartet", title="Watcher")

        try:
            while not self._stop.is_set():
                time.sleep(check_interval)

                # webcam status
                webcam_ok = self._check_webcam_online(webcam_ip)

                if self._last_webcam_ok is None:
                    self._last_webcam_ok = webcam_ok
                    self._last_webcam_change = datetime.now(timezone.utc)
                elif webcam_ok != self._last_webcam_ok:
                    self._last_webcam_ok = webcam_ok
                    self._last_webcam_change = datetime.now(timezone.utc)
                    self._send_ntfy(
                        "Webcam ist ONLINE" if webcam_ok else "Webcam ist OFFLINE",
                        title="Webcam Status",
                    )

                # new files
                current_files = self._scan_directory(watch_dir, valid_exts)
                new_files = current_files - self._known_files

                if new_files:
                    now = datetime.now(timezone.utc)
                    if now - last_alarm_time >= min_alarm_interval:
                        print(f"[INFO] New file(s): {sorted(new_files)}")
                        self._send_motion_alarm()
                        last_alarm_time = now
                        self._last_alarm = now
                    # else: cooldown -> ignore

                self._known_files = current_files

        finally:
            self._send_ntfy("Webcam-Watcher gestoppt", title="Watcher")
            print("[INFO] Watcher stopped.")


# --- Flask app ---
app = Flask(__name__)
watcher = WebcamWatcher(CONFIG_FILE)


@app.get("/webcam/status")
def api_status():
    return jsonify(asdict(watcher.status()))


@app.post("/webcam/start")
def api_start():
    ok = watcher.start()
    return jsonify({"ok": ok, "running": watcher.is_running()})


@app.post("/webcam/stop")
def api_stop():
    ok = watcher.stop(timeout_s=5.0)
    return jsonify({"ok": ok, "running": watcher.is_running()})


def _handle_signal(signum, frame):
    # stop watcher so we also get the "Watcher gestoppt" ntfy
    print(f"[INFO] signal {signum} received, shutting down...")
    watcher.stop(timeout_s=5.0)
    raise SystemExit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # optional: auto-start watcher on boot of this service
    watcher.start()
    host = watcher.conf.get("api_listen_host", "127.0.0.1")
    port = watcher.conf.get("api_listen_port", 5055)

    # bind locally; put nginx in front if needed
    app.run(host=host, port=port)
