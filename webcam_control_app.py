#!/usr/bin/env python3
"""Webcam watcher + control API (Flask) in one process (strict config, no legacy keys).

Endpoints:
  GET  /status
  POST /start
  POST /stop
  POST /test_notify
  POST /clear_images

Notes:
- No status file is used.
- Watcher runs in a background thread.
- Config is reloaded from webcam_config.json on each start.
- ntfy messages are fully driven by config templates (title/priority/tags/message).
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
from typing import Any, Optional, Set, Iterable

import requests
from flask import Flask, jsonify


# Adjust if you move the file:
CONFIG_FILE = Path("/home/raspiroman/project/webcam_watcher/webcam_config.json")


@dataclass
class WatcherStatus:
    timestamp_utc: str
    watcher_running: bool
    webcam_online: Optional[bool]
    last_alarm_utc: Optional[str]
    last_webcam_change_utc: Optional[str]
    known_files_count: int


class ConfigError(RuntimeError):
    pass


class WebcamWatcher:
    def __init__(self, config_path: Path):
        self.config_path = config_path

        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

        # runtime state
        self.conf: dict[str, Any] = self.load_config()
        self._known_files: Set[str] = set()
        self._last_alarm: Optional[datetime] = None
        self._last_webcam_ok: Optional[bool] = None
        self._last_webcam_change: Optional[datetime] = None
        self._health_hist: list[bool] = []

    def load_config(self) -> dict[str, Any]:
        conf = json.loads(self.config_path.read_text(encoding="utf-8"))
        return conf

    # ---------- ntfy (template-driven) ----------

    def _ntfy_url(self) -> str:
        ntfy = self.conf["ntfy"]
        server = str(ntfy["server"]).rstrip("/")
        topic = str(ntfy["topic"]).strip().strip("/")
        return f"{server}/{topic}"

    def _merge_ntfy_defaults(self, tpl: dict[str, Any]) -> dict[str, Any]:
        ntfy = self.conf["ntfy"]
        defaults = ntfy.get("defaults") if isinstance(ntfy.get("defaults"), dict) else {}
        merged = dict(defaults)
        merged.update(tpl or {})
        return merged

    def _format_message(self, msg: str, vars_: dict[str, Any]) -> str:
        try:
            return str(msg).format(**vars_)
        except Exception as e:
            # still send something useful
            return f"{msg} (format error: {e})"

    def send_event(self, name: str, **fmt: Any) -> None:
        ntfy = self.conf["ntfy"]
        tpl = ntfy["templates"][name]
        cfg = self._merge_ntfy_defaults(tpl)

        vars_ = dict(self.conf)
        vars_.update(fmt)

        # convenience
        if "web_url" in self.conf:
            vars_["web_url"] = self.conf["web_url"]

        message = self._format_message(cfg.get("message", ""), vars_)
        title = cfg.get("title", None)
        priority = cfg.get("priority", None)
        tags = cfg.get("tags", None)

        headers = {}
        if title:
            headers["Title"] = str(title)
        if priority is not None:
            headers["Priority"] = str(priority)

        if tags:
            if isinstance(tags, (list, tuple, set)):
                headers["Tags"] = ",".join(str(t) for t in tags if str(t).strip())
            else:
                headers["Tags"] = str(tags)

        try:
            r = requests.post(self._ntfy_url(), data=message.encode("utf-8"), headers=headers, timeout=8)
            r.raise_for_status()
            print(f"[{datetime.now()}] ntfy({name}) sent")
        except Exception as e:
            print(f"[WARN] ntfy({name}) failed: {e}")

    # ---------- watcher helpers ----------

    @staticmethod
    def _scan_directory(dir_path: Path, valid_exts: Set[str]) -> Set[str]:
        return {
            p.name
            for p in dir_path.iterdir()
            if p.is_file() and p.suffix.lower() in valid_exts
        }

    def _check_webcam_once(self) -> bool:
        hc = self.conf["webcam_health"]
        try:
            r = requests.get(hc["url"], timeout=float(hc.get("timeout", 3)))
            return r.status_code < 500
        except Exception:
            return False

    # ---------- public control ----------

    def start(self) -> bool:
        """Start the watcher thread (no-op if already running)."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False

            self.conf = self.load_config()  # reload config on start
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

    def test_notify(self) -> None:
        self.send_event("test")

    def clear_images(self) -> dict[str, int]:
        conf = self.conf
        watch_dir = Path(conf["watch_dir"])
        valid_exts = set(ext.lower() for ext in conf["valid_extensions"])

        deleted = 0
        failed = 0

        try:
            files = self._scan_directory(watch_dir, valid_exts)

            with self._lock:
                for fname in files:
                    fpath = watch_dir / fname
                    try:
                        fpath.unlink()
                        deleted += 1
                    except Exception as e:
                        failed += 1
                        print(f"[WARN] Failed to delete {fpath}: {e}")

                # rescan for truth
                try:
                    self._known_files = self._scan_directory(watch_dir, valid_exts)
                except Exception:
                    self._known_files = set()

            self.send_event("cleared", deleted=deleted, failed=failed)
            return {"deleted": deleted, "failed": failed}

        except Exception as e:
            print(f"[WARN] clear_images failed: {e}")
            self.send_event("cleared", deleted=deleted, failed=failed, error=str(e))
            return {"deleted": deleted, "failed": failed}

    # ---------- main loop ----------

    def _run(self) -> None:
        conf = self.conf
        watch_dir = Path(conf["watch_dir"])
        check_interval = int(conf.get("check_interval_seconds", 5))
        min_alarm_interval = timedelta(minutes=int(conf.get("min_alarm_interval_minutes", 10)))
        valid_exts = set(ext.lower() for ext in conf["valid_extensions"])

        print(f"[INFO] Watching: {watch_dir}")

        if not watch_dir.exists():
            print(f"[ERROR] Directory does not exist: {watch_dir}")
            return

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
        self._health_hist = []
        n = int(self.conf["webcam_health"].get("hysteresis", 1))

        self.send_event("started")

        try:
            while not self._stop.is_set():
                time.sleep(check_interval)

                # webcam status
                raw = self._check_webcam_once()
                self._health_hist.append(raw)
                # nur die letzten n Werte behalten
                self._health_hist = self._health_hist[-n:]
                # Mehrheitsentscheid
                if len(self._health_hist) == n:
                    webcam_ok = sum(self._health_hist) >= (n // 2 + 1)
                else:
                    webcam_ok = raw   # noch nicht genug Messungen

                if self._last_webcam_ok is None:
                    self._last_webcam_ok = webcam_ok
                    self._last_webcam_change = datetime.now(timezone.utc)
                    self.send_event("online" if webcam_ok else "offline")
                elif webcam_ok != self._last_webcam_ok:
                    self._last_webcam_ok = webcam_ok
                    self._last_webcam_change = datetime.now(timezone.utc)
                    self.send_event("online" if webcam_ok else "offline")

                # new files
                current_files = self._scan_directory(watch_dir, valid_exts)
                new_files = current_files - self._known_files

                if new_files:
                    now = datetime.now(timezone.utc)
                    if now - last_alarm_time >= min_alarm_interval:
                        print(f"[INFO] New file(s): {sorted(new_files)}")
                        self.send_event("motion")
                        last_alarm_time = now
                        self._last_alarm = now

                self._known_files = current_files

        finally:
            self._last_webcam_ok = None
            self._last_webcam_change = datetime.now(timezone.utc)
            self.send_event("offline")
            self.send_event("stopped")
            print("[INFO] Watcher stopped.")


# --- Flask app ---
app = Flask(__name__)
watcher = WebcamWatcher(CONFIG_FILE)


@app.get("/status")
def api_status():
    return jsonify(asdict(watcher.status()))


@app.post("/start")
def api_start():
    ok = watcher.start()
    return jsonify({"ok": ok, "running": watcher.is_running()})


@app.post("/stop")
def api_stop():
    ok = watcher.stop(timeout_s=5.0)
    return jsonify({"ok": ok, "running": watcher.is_running()})


@app.post("/test_notify")
def api_test_notify():
    watcher.test_notify()
    return jsonify({"ok": True})


@app.post("/clear_images")
def api_clear_images():
    res = watcher.clear_images()
    return jsonify({"ok": True, **res})


def _handle_signal(signum, frame):
    print(f"[INFO] signal {signum} received, shutting down...")
    watcher.stop(timeout_s=5.0)
    raise SystemExit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # load config for API host/port
    watcher.conf = watcher.load_config()

    # optional: auto-start watcher when this service starts
    watcher.start()

    host = watcher.conf["api_listen_host"]
    port = int(watcher.conf["api_listen_port"])

    app.run(host=host, port=port)
