#!/usr/bin/env python3
import json
import time
import requests
from pathlib import Path
from datetime import datetime, timedelta


CONFIG_FILE = Path("/home/raspiroman/webcam_ntfy_config.json")


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def send_ntfy_notification(conf):
    url = f"https://ntfy.sh/{conf['ntfy_topic']}"

    headers = {
        "X-Priority": str(conf.get("ntfy_priority", 3)),
        "X-Title": conf.get("ntfy_title", "Webcam Alarm"),
    }

    try:
        resp = requests.post(
            url,
            data=conf["message"].encode("utf-8"),
            headers=headers,
            timeout=8,
        )
        resp.raise_for_status()
        print(f"[{datetime.now()}] ntfy-Nachricht gesendet")
    except Exception as e:
        print(f"[ERROR] ntfy fehlgeschlagen: {e}")


def scan_directory(dir_path: Path, valid_exts):
    return {
        p.name
        for p in dir_path.iterdir()
        if p.is_file() and p.suffix.lower() in valid_exts
    }


def main():
    conf = load_config()

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

    while True:
        time.sleep(check_interval)

        # Live reload der Config bei jeder Runde ist praktisch 🙂
        try:
            conf = load_config()
        except Exception as e:
            print(f"[WARN] Konnte Config nicht neu laden: {e}")

        current_files = scan_directory(watch_dir, valid_exts)
        new_files = current_files - known_files

        if new_files:
            now = datetime.now()
            if now - last_alarm_time >= min_alarm_interval:
                print(f"[INFO] Neue Datei(en): {sorted(new_files)}")
                send_ntfy_notification(conf)
                last_alarm_time = now
            else:
                remaining = min_alarm_interval - (now - last_alarm_time)
                print(
                    f"[INFO] Neue Dateien, aber Cooldown aktiv "
                    f"(noch {remaining.seconds} s)"
                )

        known_files = current_files


if __name__ == "__main__":
    main()
