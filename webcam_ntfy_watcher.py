#!/usr/bin/env python3
import os
import time
import requests  # musst du evtl. mit: pip install requests
from pathlib import Path

# === KONFIGURATION ===
WATCH_DIR = Path("/srv/webcam/upload/webcam")          # Ordner, in dem die Kamera die Bilder ablegt
NTFY_TOPIC = "raspiroman"                # dein ntfy Topic
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"
CHECK_INTERVAL = 5                       # Sekunden zwischen den Checks
VALID_EXTENSIONS = {".jpg", ".jpeg", ".png"}  # überwachte Dateitypen

# Optional: Text der Notification
MESSAGE_TEMPLATE = "Neue Aufnahme von der Webcam: {filename}"


def send_ntfy_notification(filename: str):
    """Schicke eine Nachricht an ntfy."""
    msg = MESSAGE_TEMPLATE.format(filename=filename)
    try:
        resp = requests.post(
            NTFY_URL,
            data=msg.encode("utf-8"),
            timeout=5,
        )
        resp.raise_for_status()
        print(f"[INFO] ntfy-Nachricht gesendet für {filename}")
    except Exception as e:
        print(f"[ERROR] Konnte ntfy-Nachricht nicht senden für {filename}: {e}")


def scan_directory(dir_path: Path):
    """Gibt ein Set aller Dateien mit gültiger Endung im Verzeichnis zurück."""
    return {
        p.name
        for p in dir_path.iterdir()
        if p.is_file() and p.suffix.lower() in VALID_EXTENSIONS
    }


def main():
    print(f"Starte Überwachung von {WATCH_DIR} ...")
    if not WATCH_DIR.exists():
        print(f"[ERROR] Verzeichnis existiert nicht: {WATCH_DIR}")
        return

    # Anfangszustand: alle aktuellen Dateien merken (noch keine Meldung)
    known_files = scan_directory(WATCH_DIR)
    print(f"Initial {len(known_files)} Dateien gefunden, werden als bekannt markiert.")

    while True:
        time.sleep(CHECK_INTERVAL)

        current_files = scan_directory(WATCH_DIR)

        # Neue Dateien = in current_files, aber nicht in known_files
        new_files = current_files - known_files
        if new_files:
            for fname in sorted(new_files):
                print(f"[INFO] Neue Datei erkannt: {fname}")
                send_ntfy_notification(fname)

        known_files = current_files


if __name__ == "__main__":
    main()
