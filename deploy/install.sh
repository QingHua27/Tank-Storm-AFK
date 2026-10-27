#!/bin/bash
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo 'Run with sudo'; exit 1; }
DOMAIN=${1:?Pass your HTTPS domain as the first argument}
[[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]] || { echo 'Invalid domain'; exit 1; }
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RELEASE=/opt/tankstorm/releases/v2.0.0/unpacked/tankstorm-linux-x64
[ -x "$RELEASE/tankstorm" ] && [ -f "$RELEASE/config.json" ] || { echo 'Install and verify upstream v2.0.0 release first'; exit 1; }
id tankstorm >/dev/null 2>&1 || useradd --system --home-dir /opt/tankstorm --shell /usr/sbin/nologin tankstorm
id tankstorm-web >/dev/null 2>&1 || useradd --system --home-dir /opt/tankstorm/web --shell /usr/sbin/nologin tankstorm-web
install -d -o root -g tankstorm -m 750 /opt/tankstorm/accounts
install -d -o root -g root -m 700 /opt/tankstorm/accounts/.backups /opt/tankstorm/panel-account-names /run/tankstorm-panel
install -d -m 755 /opt/tankstorm/web /opt/tankstorm/web/static
cp -a "$ROOT/web/." /opt/tankstorm/web/
find /opt/tankstorm/web -type d -exec chmod 755 {} +
find /opt/tankstorm/web -type f -exec chmod 644 {} +
chown -R root:root /opt/tankstorm/web
python3 -m venv /opt/tankstorm/web-venv
/opt/tankstorm/web-venv/bin/pip install -r "$ROOT/web/requirements.txt"
install -m 755 "$ROOT/tankstormctl" /usr/local/sbin/tankstormctl
install -m 755 "$ROOT/web/control.py" /usr/local/sbin/tankstorm-webctl
printf 'tankstorm-web ALL=(root) NOPASSWD: /usr/local/sbin/tankstorm-webctl\n' >/etc/sudoers.d/tankstorm-web
chmod 440 /etc/sudoers.d/tankstorm-web
visudo -cf /etc/sudoers.d/tankstorm-web
printf 'd /run/tankstorm-panel 0700 root root -\n' >/etc/tmpfiles.d/tankstorm-panel.conf
systemd-tmpfiles --create /etc/tmpfiles.d/tankstorm-panel.conf
export TANKSTORM_PANEL_HOST="$DOMAIN"
/opt/tankstorm/web-venv/bin/python - <<'PY'
import os,pathlib,secrets
from werkzeug.security import generate_password_hash
p=pathlib.Path('/etc/tankstorm-panel.env')
if not p.exists():
 password=secrets.token_urlsafe(18)
 p.write_text('PANEL_SECRET='+secrets.token_hex(32)+'\nPANEL_PASSWORD_HASH='+generate_password_hash(password)+'\nPANEL_HOSTS='+os.environ['TANKSTORM_PANEL_HOST']+'\n')
 os.chmod(p,0o600)
 access=pathlib.Path('/root/tankstorm-panel-access.txt')
 access.write_text('URL: https://'+os.environ['TANKSTORM_PANEL_HOST']+'/\nUsername: admin\nPassword: '+password+'\n');os.chmod(access,0o600)
PY
for unit in tankstorm@.service tankstorm-login@.service tankstorm-daily@.service tankstorm-daily@.timer tankstorm-web.service; do install -m 644 "$ROOT/systemd/$unit" /etc/systemd/system/; done
install -d /etc/systemd/system/tankstorm-web.service.d
printf '[Service]\nReadWritePaths=/opt/tankstorm/panel-account-names\n' >/etc/systemd/system/tankstorm-web.service.d/account-data.conf
systemctl daemon-reload
systemctl enable --now tankstorm-web.service
printf 'Web service installed. Configure HTTPS nginx as described in deploy/README.md. Credentials are stored in /root/tankstorm-panel-access.txt\n'
