#!/usr/bin/env python3
"""
ZTP Manager — Zero Touch Provisioning for Kármán
Manages DHCP server (dnsmasq), ZTP script generation, and device auto-registration.
"""

import os
import signal
import shutil
import sqlite3
import subprocess
import time
from typing import Optional


# ---------------------------------------------------------------------------
# ZTP Python script template — placeholders use __UPPER__ style to avoid
# conflicts with Python f-string syntax or EOS config braces.
# ---------------------------------------------------------------------------
_ZTP_SCRIPT_TEMPLATE = r'''#!/usr/bin/env python3
# =============================================================================
# Kármán ZTP Script — auto-generated, do not edit manually
# Generated: __GENERATED_AT__
# =============================================================================
import os, json, socket, subprocess, time, urllib.request, urllib.error

KARMAN_URL  = "__KARMAN_URL__"
USERNAME    = "__USERNAME__"
PASSWORD    = "__PASSWORD__"
API_KEY     = "__API_KEY__"

BASE_CONFIG = """__BASE_CONFIG__"""


def log(msg):
    print(f"[Karman-ZTP] {msg}", flush=True)


def run_cli(cmd):
    try:
        r = subprocess.run(
            ["FastCli", "-p", "15", "-c", cmd],
            capture_output=True, text=True, timeout=30
        )
        return r.stdout.strip()
    except Exception as e:
        log(f"CLI error: {e}")
        return ""


def get_hostname():
    out = run_cli("show hostname")
    if out:
        return out.split()[-1]
    return socket.gethostname()


def get_mgmt_ip():
    # EOS sets DHCP_IP during ZTP
    ip = os.environ.get("DHCP_IP", "")
    if ip:
        return ip
    out = run_cli("show management interface")
    for line in out.splitlines():
        if "Internet address" in line:
            return line.split()[-1].split("/")[0]
    return ""


def apply_base_config(hostname, ip):
    try:
        config = BASE_CONFIG.format(
            hostname=hostname,
            ip=ip,
            username=USERNAME,
            password=PASSWORD,
            karman_url=KARMAN_URL,
        )
        with open("/mnt/flash/startup-config", "w") as f:
            f.write(config)
        log("Base config written to /mnt/flash/startup-config")
        return True
    except Exception as e:
        log(f"Failed to write startup-config: {e}")
        return False


def register(hostname, ip):
    if not KARMAN_URL:
        log("No Karman URL configured — skipping registration")
        return False
    payload = json.dumps({
        "hostname": hostname,
        "ip": ip,
        "source": "ztp",
        "api_key": API_KEY,
    }).encode()
    req = urllib.request.Request(
        f"{KARMAN_URL}/api/devices/register",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
                if result.get("success"):
                    log(f"Registered: {hostname} @ {ip}")
                    return True
                log(f"Registration rejected: {result.get('message', 'unknown')}")
                return False
        except Exception as e:
            log(f"Attempt {attempt + 1}/3 failed: {e}")
            if attempt < 2:
                time.sleep(5)
    return False


def install_agent():
    """Download the Kármán agent script and add it to the startup-config daemon stanza."""
    if not KARMAN_URL:
        log("No Karman URL — skipping agent install")
        return False
    agent_url = f"{KARMAN_URL}/karman-agent.py"
    agent_path = "/mnt/flash/karman_agent.py"
    log(f"Downloading agent from {agent_url}")
    try:
        with urllib.request.urlopen(agent_url, timeout=30) as resp:
            content = resp.read()
        with open(agent_path, "wb") as f:
            f.write(content)
        os.chmod(agent_path, 0o755)
        log(f"Agent written to {agent_path}")
    except Exception as e:
        log(f"Agent download failed: {e}")
        return False

    # Append daemon stanza to the startup-config we just wrote
    daemon_stanza = (
        "\n"
        "daemon karman-agent\n"
        f"   exec /usr/bin/python3 {agent_path}\n"
        "   no shutdown\n"
    )
    try:
        with open("/mnt/flash/startup-config", "a") as f:
            f.write(daemon_stanza)
        log("Daemon stanza appended to startup-config")
        return True
    except Exception as e:
        log(f"Failed to append daemon stanza: {e}")
        return False


def main():
    log("Zero Touch Provisioning starting")
    hostname = get_hostname()
    ip = get_mgmt_ip()
    log(f"Device: {hostname} / {ip or 'IP unknown'}")

    if apply_base_config(hostname, ip):
        log("Base config applied")
    else:
        log("WARNING: Base config apply failed — continuing anyway")

    if ip:
        register(hostname, ip)
    else:
        log("WARNING: Could not determine management IP — skipping registration")

    install_agent()

    log("ZTP complete — reloading to apply startup config")
    subprocess.run(["FastCli", "-p", "15", "-c", "reload now"], capture_output=True)


if __name__ == "__main__":
    main()
'''


# ---------------------------------------------------------------------------
# Default base config template — users edit this in the UI
# ---------------------------------------------------------------------------
DEFAULT_BASE_CONFIG = """\
no aaa root
!
username {username} privilege 15 role network-admin secret {password}
!
management api http-commands
   protocol http
   protocol https
   no shutdown
   !
   vrf default
      no shutdown
!
management ssh
   no shutdown
!
daemon TerminAttr
   exec /usr/bin/TerminAttr -grpcaddr=default/0.0.0.0:6030 -allowed-ips=0.0.0.0/0 -disableaaa
   no shutdown
!
"""


class ZTPManager:
    DNSMASQ_CONF   = '/tmp/karman-dnsmasq.conf'
    DNSMASQ_LEASES = '/tmp/karman-dnsmasq.leases'
    DNSMASQ_PID    = '/tmp/karman-dnsmasq.pid'

    _DEFAULTS = {
        'ztp_enabled':           'false',
        'ztp_dhcp_enabled':      'false',
        'ztp_dhcp_interface':    'eth0',
        'ztp_dhcp_range_start':  '192.168.2.100',
        'ztp_dhcp_range_end':    '192.168.2.200',
        'ztp_dhcp_netmask':      '255.255.255.0',
        'ztp_dhcp_gateway':      '192.168.2.1',
        'ztp_dhcp_dns':          '8.8.8.8',
        'ztp_dhcp_lease_time':   '24h',
        'ztp_default_username':  'admin',
        'ztp_default_password':  'admin',
        'ztp_karman_url':        '',
        'ztp_api_key':           '',
        'ztp_auto_add':          'true',
        'ztp_default_role':      'leaf',
        'ztp_default_site':      '',
        'ztp_default_mgmt_type': 'auto',
        'ztp_base_config':       DEFAULT_BASE_CONFIG,
    }

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as db:
            db.execute('''
                CREATE TABLE IF NOT EXISTS ztp_leases (
                    mac_address    TEXT PRIMARY KEY,
                    ip_address     TEXT,
                    hostname       TEXT,
                    first_seen     REAL,
                    last_seen      REAL,
                    registered     INTEGER DEFAULT 0,
                    device_hostname TEXT
                )
            ''')
            # Seed default base config only if not already set
            db.execute(
                "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
                ('ztp_base_config', DEFAULT_BASE_CONFIG)
            )

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def get_settings(self) -> dict:
        with self._conn() as db:
            rows = db.execute(
                "SELECT key, value FROM app_settings WHERE key LIKE 'ztp_%'"
            ).fetchall()
        settings = {r['key']: r['value'] for r in rows}
        for k, v in self._DEFAULTS.items():
            settings.setdefault(k, v)
        return settings

    def save_settings(self, settings: dict):
        with self._conn() as db:
            for key, value in settings.items():
                if key.startswith('ztp_'):
                    db.execute(
                        "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                        (key, str(value))
                    )

    # ------------------------------------------------------------------
    # DHCP leases
    # ------------------------------------------------------------------
    def get_leases(self) -> list:
        self._sync_dnsmasq_leases()
        with self._conn() as db:
            rows = db.execute(
                "SELECT * FROM ztp_leases ORDER BY last_seen DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def _sync_dnsmasq_leases(self):
        if not os.path.exists(self.DNSMASQ_LEASES):
            return
        try:
            with open(self.DNSMASQ_LEASES) as f:
                lines = f.readlines()
            now = time.time()
            with self._conn() as db:
                for line in lines:
                    parts = line.strip().split()
                    if len(parts) < 4:
                        continue
                    mac  = parts[1]
                    ip   = parts[2]
                    name = parts[3] if parts[3] != '*' else ''
                    db.execute('''
                        INSERT INTO ztp_leases (mac_address, ip_address, hostname, first_seen, last_seen)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(mac_address) DO UPDATE SET
                            ip_address = excluded.ip_address,
                            hostname   = excluded.hostname,
                            last_seen  = excluded.last_seen
                    ''', (mac, ip, name, now, now))
        except Exception as e:
            print(f"[ZTP] Error syncing dnsmasq leases: {e}")

    def record_registration(self, mac: str, device_hostname: str):
        if not mac:
            return
        with self._conn() as db:
            db.execute(
                "UPDATE ztp_leases SET registered=1, device_hostname=? WHERE mac_address=?",
                (device_hostname, mac)
            )

    # ------------------------------------------------------------------
    # Network interfaces
    # ------------------------------------------------------------------
    def get_network_interfaces(self) -> list:
        try:
            ifaces = os.listdir('/sys/class/net/')
            return sorted(i for i in ifaces if i != 'lo')
        except Exception:
            return ['eth0']

    # ------------------------------------------------------------------
    # dnsmasq — built-in DHCP server
    # ------------------------------------------------------------------
    def _dnsmasq_config(self, s: dict) -> str:
        karman_url = s.get('ztp_karman_url', '').rstrip('/')
        return (
            f"# Kármán auto-generated dnsmasq config\n"
            f"interface={s.get('ztp_dhcp_interface', 'eth0')}\n"
            f"bind-interfaces\n"
            f"port=0\n"
            f"no-hosts\n"
            f"no-resolv\n"
            f"dhcp-range={s['ztp_dhcp_range_start']},{s['ztp_dhcp_range_end']},"
            f"{s['ztp_dhcp_netmask']},{s['ztp_dhcp_lease_time']}\n"
            f"dhcp-option=option:router,{s['ztp_dhcp_gateway']}\n"
            f"dhcp-option=option:dns-server,{s['ztp_dhcp_dns']}\n"
            f"dhcp-boot={karman_url}/ztp/script\n"
            f"dhcp-leasefile={self.DNSMASQ_LEASES}\n"
            f"log-dhcp\n"
        )

    def start_dhcp(self, settings: dict) -> dict:
        if not shutil.which('dnsmasq'):
            return {'success': False,
                    'message': 'dnsmasq not found — install with: apt-get install dnsmasq'}
        self.stop_dhcp()
        with open(self.DNSMASQ_CONF, 'w') as f:
            f.write(self._dnsmasq_config(settings))
        try:
            r = subprocess.run(
                ['dnsmasq',
                 f'--conf-file={self.DNSMASQ_CONF}',
                 f'--pid-file={self.DNSMASQ_PID}'],
                capture_output=True, text=True
            )
            if r.returncode != 0:
                return {'success': False, 'message': r.stderr.strip() or 'dnsmasq failed to start'}
            return {'success': True, 'message': 'DHCP server started'}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def stop_dhcp(self) -> dict:
        stopped = False
        try:
            if os.path.exists(self.DNSMASQ_PID):
                with open(self.DNSMASQ_PID) as f:
                    pid = int(f.read().strip())
                os.kill(pid, signal.SIGTERM)
                try:
                    os.remove(self.DNSMASQ_PID)
                except FileNotFoundError:
                    pass
                stopped = True
        except (ProcessLookupError, ValueError, FileNotFoundError):
            pass
        subprocess.run(['pkill', '-f', self.DNSMASQ_CONF], capture_output=True)
        return {'success': True, 'message': 'DHCP server stopped' if stopped else 'DHCP server was not running'}

    def get_dhcp_status(self) -> dict:
        if not os.path.exists(self.DNSMASQ_PID):
            return {'running': False}
        try:
            with open(self.DNSMASQ_PID) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)   # raises if process gone
            return {'running': True, 'pid': pid}
        except (ProcessLookupError, ValueError, FileNotFoundError):
            return {'running': False}

    def is_dnsmasq_available(self) -> bool:
        return shutil.which('dnsmasq') is not None

    # ------------------------------------------------------------------
    # ZTP script generation
    # ------------------------------------------------------------------
    def generate_ztp_script(self, settings: dict) -> str:
        base_config = settings.get('ztp_base_config', DEFAULT_BASE_CONFIG)
        # Indent base config 4 spaces so it sits cleanly inside the triple-quoted string
        indented = '\n'.join('    ' + line if line.strip() else line
                             for line in base_config.splitlines())
        script = _ZTP_SCRIPT_TEMPLATE
        script = script.replace('__GENERATED_AT__',
                                time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()))
        script = script.replace('__KARMAN_URL__',
                                settings.get('ztp_karman_url', '').rstrip('/'))
        script = script.replace('__USERNAME__',
                                settings.get('ztp_default_username', 'admin'))
        script = script.replace('__PASSWORD__',
                                settings.get('ztp_default_password', 'admin'))
        script = script.replace('__API_KEY__',
                                settings.get('ztp_api_key', ''))
        script = script.replace('__BASE_CONFIG__', indented)
        return script
