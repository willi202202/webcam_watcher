FTP-Server auf Raspberry Pi

ein eigener Webcam-User
Upload in definiertes Verzeichnis
Benutzer ist auf Ordner eingeschränkt (chroot jail)
kein Internetzugang nötig – nur internes LAN

🟢 1. vsftpd installieren
sudo apt update
sudo apt install vsftpd

Backup der Original-Config:

sudo cp /etc/vsftpd.conf /etc/vsftpd.conf.orig

🟢 2. Webcam-Ordner anlegen
sudo mkdir -p /srv/webcam
sudo chown -R root:root /srv/webcam
sudo mkdir /srv/webcam/upload
sudo chown -R ftpuser:ftpuser /srv/webcam/upload


(ftpuser kommt gleich)

🟢 3. FTP-Benutzer erstellen (kein SSH-Login!)
sudo adduser ftpuser


Shell sperren:

sudo usermod -s /usr/sbin/nologin ftpuser


Home auf Webcam-Verzeichnis setzen:

sudo usermod -d /srv/webcam ftpuser

🟢 4. vsftpd konfigurieren

Datei öffnen:

sudo nano /etc/vsftpd.conf


Inhalt anpassen/ergänzen:

listen=YES
anonymous_enable=NO
local_enable=YES
write_enable=YES

# User in sein Verzeichnis einsperren
chroot_local_user=YES
allow_writeable_chroot=YES

# Passive Mode (wichtig für viele Webcams!)
pasv_enable=YES
pasv_min_port=30000
pasv_max_port=30010

# Optional: nur LAN
listen_ipv6=NO

🟢 5. Dienst neu starten
sudo systemctl restart vsftpd
sudo systemctl enable vsftpd

🟢 6. Webcam konfigurieren

Trage ein:

FTP Server: 👉 IP vom Raspberry Pi

Port: 👉 21

Benutzername: 👉 ftpuser

Passwort: 👉 dein gesetztes Passwort

Pfad: 👉 upload oder /upload (je nach Webcam)

🛟 Optional – interne Sicherheitstipps

keine Portfreigabe im Router

bei Bedarf LAN-Restriktion in UFW:

sudo ufw allow from 192.168.0.0/16 to any port 21 proto tcp comment 'FTP webcam'
sudo ufw allow from 192.168.0.0/16 to any port 30000:30010 proto tcp comment 'FTP passive webcam'


Systemd-Status anzeigen (beste Methode)
sudo systemctl status vsftpd
journalctl -u vsftpd -e

Prüfen, ob Port 21 lauscht
sudo ss -ltnp | grep 21