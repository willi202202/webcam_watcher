#!/usr/bin/env python3
import json
import subprocess
import time
import requests
import signal
from pathlib import Path
from datetime import datetime, timedelta

CONFIG_FILE = Path("/home/raspiroman/project/webcam_watcher/webcam_ntfy_config.json")

# globale Variable für sauberes Beenden
stop_requested = False


def handle_signal(signum, frame):
    global stop_requested
    print(f"[INFO] Signal {signum} empfangen, Beenden angefordert...")
    stop_requested = True


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def send_ntfy(conf, message: str, priority=None, title=None):
    """Generische ntfy-Funktion.
       priority=None  -> default (kein X-Priority-Header)
    """
    url = f"https://ntfy.sh/{conf['ntfy_topic']}"

    headers = {}
    if priority is not None:
        headers["X-Priority"] = str(priority)
    if title is None:
        title = conf.get("ntfy_title", "Webcam Alarm")
    headers["X-Title"] = title

    try:
        resp = requests.post(
            url,
            data=message.encode("utf-8"),
            headers=headers,
            timeout=8,
        )
        resp.raise_for_status()
        print(f"[{datetime.now()}] ntfy-Nachricht gesendet: {message}")
    except Exception as e:
        print(f"[ERROR] ntfy fehlgeschlagen: {e}")


def send_motion_alarm(conf):
    """Bewegungs-/Bild-Alarm mit konfigurierter Priority."""
    prio = conf.get("ntfy_priority", 3)
    msg = conf["message"]
    send_ntfy(conf, msg, priority=prio, title=conf.get("ntfy_title", "Webcam Alarm"))


def scan_directory(dir_path: Path, valid_exts):
    return {
        p.name
        for p in dir_path.iterdir()
        if p.is_file() and p.suffix.lower() in valid_exts
    }


def check_webcam_online(ip: str) -> bool:
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0
    except Exception:
        return False


def write_status_file(status_path: Path, webcam_ok: bool):
    status = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "webcam_online": webcam_ok,
        "watcher_running": True,
    }
    try:
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(json.dumps(status), encoding="utf-8")
    except Exception as e:
        print(f"[WARN] failed to write status.json: {e}")


def main():
    global stop_requested

    # Signal-Handler für sauberes Beenden
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    conf = load_config()

    STATUS_FILE = Path(conf["status_file"])
    WEBCAM_IP = conf["webcam_ip"]
    watch_dir = Path(conf["watch_dir"])
    check_interval = conf.get("check_interval_seconds", 5)
    min_alarm_interval = timedelta(
        minutes=conf.get("min_alarm_interval_minutes", 10)
    )
    valid_exts = set(ext.lower() for ext in conf["valid_extensions"])

    print(f"Überwache: {watch_dir}")

    if not watch_dir.exists():
        print(f"[ERROR] Verzeichnis existiert nicht: {watch_dir}")
        return

    known_files = scan_directory(watch_dir, valid_exts)
    print(f"{len(known_files)} bestehende Dateien als bekannt markiert.")

    last_alarm_time = datetime.min
    last_webcam_ok = None  # noch kein Status bekannt

    # ➜ Start-Notification (default Priority)
    send_ntfy(conf, "Webcam-Watcher gestartet", title="Watcher")

    try:
        while not stop_requested:
            time.sleep(check_interval)

            # Webcam-Status prüfen & Statusfile schreiben
            webcam_ok = check_webcam_online(WEBCAM_IP)
            write_status_file(STATUS_FILE, webcam_ok)

            # Statuswechsel erkennen (online/offline)
            if last_webcam_ok is None:
                # erster Durchlauf -> nur merken
                last_webcam_ok = webcam_ok
            else:
                if webcam_ok and not last_webcam_ok:
                    # OFFLINE -> ONLINE
                    send_ntfy(
                        conf,
                        "Webcam ist wieder ONLINE",
                        title="Webcam Status"
                    )
                elif not webcam_ok and last_webcam_ok:
                    # ONLINE -> OFFLINE
                    send_ntfy(
                        conf,
                        "Webcam ist OFFLINE",
                        title="Webcam Status"
                    )
                last_webcam_ok = webcam_ok

            # Neue Dateien prüfen
            current_files = scan_directory(watch_dir, valid_exts)
            new_files = current_files - known_files

            if new_files:
                now = datetime.now()
                if now - last_alarm_time >= min_alarm_interval:
                    print(f"[INFO] Neue Datei(en): {sorted(new_files)}")
                    send_motion_alarm(conf)
                    last_alarm_time = now
                else:
                    remaining = min_alarm_interval - (now - last_alarm_time)
                    print(
                        f"[INFO] Neue Dateien, aber Cooldown aktiv "
                        f"(noch {remaining.seconds} s)"
                    )

            known_files = current_files

    finally:
        # ➜ Stop-Notification (default Priority)
        send_ntfy(conf, "Webcam-Watcher gestoppt", title="Watcher")
        print("[INFO] Watcher beendet.")


if __name__ == "__main__":
    main()
