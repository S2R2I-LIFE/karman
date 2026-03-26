#!/usr/bin/env python3
"""
Pure-Python DHCP server for Kármán ZTP.

Listens on UDP port 67, responds ONLY to clients whose DHCP DISCOVER
carries a vendor-class (option 60) that starts with "Arista".
All other clients are silently ignored — UCG-Ultra or whatever router
is on the network handles them normally.

Implements the minimal DISCOVER → OFFER → REQUEST → ACK flow needed for
EOS ZTP.  Option 67 (boot-file) is always injected pointing at the
Kármán ZTP script endpoint.
"""

import fcntl
import ipaddress
import logging
import socket
import struct
import threading
import time

log = logging.getLogger('karman.dhcp')

# ---------------------------------------------------------------------------
# DHCP constants
# ---------------------------------------------------------------------------
DHCP_MAGIC        = b'\x63\x82\x53\x63'
BOOT_REQUEST      = 1
BOOT_REPLY        = 2

MSG_DISCOVER      = 1
MSG_OFFER         = 2
MSG_REQUEST       = 3
MSG_ACK           = 5
MSG_NAK           = 6

OPT_SUBNET_MASK   = 1
OPT_ROUTER        = 3
OPT_DNS           = 6
OPT_LEASE_TIME    = 51
OPT_MSG_TYPE      = 53
OPT_SERVER_ID     = 54
OPT_PARAM_REQ     = 55
OPT_VENDOR_CLASS  = 60
OPT_BOOTFILE      = 67
OPT_END           = 255
OPT_PAD           = 0

_DEFAULT_LEASE    = 86400   # 24 h in seconds


# ---------------------------------------------------------------------------
# Packet parser
# ---------------------------------------------------------------------------
class _Pkt:
    """Parse a raw DHCP/BOOTP packet."""

    __slots__ = ('op', 'htype', 'hlen', 'xid', 'flags',
                 'ciaddr', 'giaddr', 'chaddr', 'mac', 'options')

    def __init__(self, data: bytes):
        if len(data) < 240:
            raise ValueError('packet too short')
        self.op    = data[0]
        self.htype = data[1]
        self.hlen  = data[2]
        self.xid   = data[4:8]
        self.flags = struct.unpack('!H', data[10:12])[0]
        self.ciaddr = data[12:16]
        self.giaddr = data[24:28]
        self.chaddr = data[28:44]
        self.mac    = ':'.join(f'{b:02x}' for b in self.chaddr[:self.hlen])

        self.options: dict[int, bytes] = {}
        if data[236:240] == DHCP_MAGIC:
            i = 240
            while i < len(data):
                code = data[i]
                if code == OPT_END:
                    break
                if code == OPT_PAD:
                    i += 1
                    continue
                if i + 1 >= len(data):
                    break
                length = data[i + 1]
                self.options[code] = data[i + 2: i + 2 + length]
                i += 2 + length

    @property
    def msg_type(self) -> int:
        v = self.options.get(OPT_MSG_TYPE, b'\x00')
        return v[0] if v else 0

    @property
    def vendor_class(self) -> str:
        return self.options.get(OPT_VENDOR_CLASS, b'').decode('ascii', errors='replace')

    @property
    def requested_ip(self) -> bytes:
        return self.options.get(50, b'')   # option 50 = requested IP

    @property
    def client_hostname(self) -> str:
        return self.options.get(12, b'').decode('ascii', errors='replace').strip('\x00')


# ---------------------------------------------------------------------------
# Packet builder helpers
# ---------------------------------------------------------------------------
def _pack_ip(ip_str: str) -> bytes:
    try:
        return socket.inet_aton(ip_str)
    except OSError:
        return b'\x00\x00\x00\x00'


def _prefix_to_netmask(prefix_len: int) -> str:
    """Convert a CIDR prefix length (e.g. 24) to dotted-decimal netmask."""
    try:
        return str(ipaddress.IPv4Network(f'0.0.0.0/{prefix_len}').netmask)
    except ValueError:
        return '255.255.255.0'


def _build_reply(pkt: _Pkt, msg_type: int, offered_ip: str,
                 server_ip: str, settings: dict) -> bytes:
    """Build a DHCP OFFER or ACK packet."""
    boot_url  = settings.get('ztp_karman_url', '').rstrip('/') + '/ztp/script'
    dns       = settings.get('ztp_dhcp_dns', '8.8.8.8')
    # When the management pool is active the DHCP IPs are the permanent management
    # IPs, so use the pool's gateway and prefix instead of the DHCP-range values.
    if settings.get('ztp_mgmt_pool_enabled') == 'true' and settings.get('ztp_mgmt_pool_start'):
        subnet  = _prefix_to_netmask(int(settings.get('ztp_mgmt_prefix', '24')))
        gateway = settings.get('ztp_mgmt_gateway', '')
    else:
        subnet  = settings.get('ztp_dhcp_netmask', '255.255.255.0')
        gateway = settings.get('ztp_dhcp_gateway', '')

    # Fixed header (236 bytes)
    buf = bytearray(236)
    buf[0]  = BOOT_REPLY
    buf[1]  = pkt.htype
    buf[2]  = pkt.hlen
    buf[3]  = 0                                 # hops
    buf[4:8]   = pkt.xid
    buf[8:10]  = b'\x00\x00'                    # secs
    # Broadcast flag: mirror client flags so client can receive the reply
    buf[10:12] = struct.pack('!H', pkt.flags)
    buf[12:16] = pkt.ciaddr                     # ciaddr
    buf[16:20] = _pack_ip(offered_ip)           # yiaddr
    buf[20:24] = _pack_ip(server_ip)            # siaddr
    buf[24:28] = pkt.giaddr                     # giaddr
    buf[28:44] = pkt.chaddr                     # chaddr (16 bytes padded)

    # Magic cookie
    buf += DHCP_MAGIC

    # Options
    def opt(code: int, value: bytes):
        buf.extend(bytes([code, len(value)]) + value)

    opt(OPT_MSG_TYPE,  bytes([msg_type]))
    opt(OPT_SERVER_ID, _pack_ip(server_ip))
    opt(OPT_LEASE_TIME, struct.pack('!I', _DEFAULT_LEASE))
    opt(OPT_SUBNET_MASK, _pack_ip(subnet))
    if gateway:
        opt(OPT_ROUTER, _pack_ip(gateway))
    if dns:
        opt(OPT_DNS, _pack_ip(dns))
    # Option 67 — ZTP boot file URL
    opt(OPT_BOOTFILE, boot_url.encode())
    buf.extend([OPT_END])

    return bytes(buf)


# ---------------------------------------------------------------------------
# IP pool
# ---------------------------------------------------------------------------
class _Pool:
    """Simple in-memory IP pool.  Allocations survive as long as the server thread runs."""

    def __init__(self):
        self._mac_to_ip:       dict[str, str] = {}
        self._mac_to_hostname: dict[str, str] = {}
        self._used: set[str] = set()
        self._lock = threading.Lock()

    def allocate(self, mac: str, start: str, end: str, hostname: str = '',
                 exclude_ips=None) -> str | None:
        with self._lock:
            if hostname:
                self._mac_to_hostname[mac] = hostname
            if mac in self._mac_to_ip:
                return self._mac_to_ip[mac]
            try:
                s = int(ipaddress.IPv4Address(start))
                e = int(ipaddress.IPv4Address(end))
            except ValueError:
                return None
            for ip_int in range(s, e + 1):
                ip = str(ipaddress.IPv4Address(ip_int))
                if ip not in self._used and (not exclude_ips or ip not in exclude_ips):
                    self._mac_to_ip[mac] = ip
                    self._used.add(ip)
                    return ip
        return None

    def lookup(self, mac: str) -> str | None:
        return self._mac_to_ip.get(mac)

    def leases(self) -> list[dict]:
        return [
            {'mac': m, 'ip': i, 'hostname': self._mac_to_hostname.get(m, '')}
            for m, i in self._mac_to_ip.items()
        ]

    def clear(self):
        with self._lock:
            self._mac_to_ip.clear()
            self._mac_to_hostname.clear()
            self._used.clear()


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
def _get_iface_ip(iface: str) -> str | None:
    """Return the IPv4 address of a network interface (Linux ioctl)."""
    SIOCGIFADDR = 0x8915
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            result = fcntl.ioctl(
                s.fileno(), SIOCGIFADDR,
                struct.pack('256s', iface[:15].encode())
            )
        return socket.inet_ntoa(result[20:24])
    except Exception:
        return None


class PythonDHCPServer:
    """Pure-Python DHCP server thread.

    Usage::
        srv = PythonDHCPServer(get_settings_fn)
        srv.start({'ztp_dhcp_interface': 'eth0', ...})
        # later:
        srv.stop()
    """

    def __init__(self, get_settings_fn, get_used_ips_fn=None):
        self._get_settings  = get_settings_fn
        self._get_used_ips  = get_used_ips_fn   # optional: () -> set[str] of DB-resident IPs
        self._pool          = _Pool()
        self._thread: threading.Thread | None = None
        self._stop          = threading.Event()
        self._sock: socket.socket | None = None
        self._server_ip: str | None = None

    # ------------------------------------------------------------------
    def start(self, settings: dict) -> dict:
        if self._thread and self._thread.is_alive():
            self.stop()
        self._stop.clear()
        self._pool.clear()
        self._thread = threading.Thread(
            target=self._run, args=(settings,), daemon=True, name='karman-dhcp'
        )
        self._thread.start()
        time.sleep(0.2)  # give it a moment to bind
        if self._thread.is_alive():
            return {'success': True, 'message': 'Python DHCP server started'}
        return {'success': False, 'message': 'DHCP server thread failed to start (check port 67)'}

    def stop(self) -> dict:
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=3)
        self._thread = None
        self._server_ip = None
        return {'success': True, 'message': 'Python DHCP server stopped'}

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def get_status(self) -> dict:
        if self.is_running():
            return {'running': True, 'server_ip': self._server_ip, 'backend': 'python'}
        return {'running': False, 'backend': 'python'}

    def get_leases(self) -> list[dict]:
        return self._pool.leases()

    def get_pool_ip_for_mac(self, mac: str) -> str | None:
        """Return the IP this server's pool already allocated for mac, or None."""
        return self._pool.lookup(mac)

    # ------------------------------------------------------------------
    def _run(self, settings: dict):
        iface     = settings.get('ztp_dhcp_interface', 'eth0')
        self._server_ip = _get_iface_ip(iface) or '0.0.0.0'

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            # Bind to the interface IP so we don't steal packets from other servers
            # on different subnets — only the broadcast on this iface reaches us.
            sock.bind(('', 67))
            sock.settimeout(1.0)
            self._sock = sock
            log.info('DHCP server listening on %s (iface %s)', self._server_ip, iface)
        except OSError as exc:
            log.error('DHCP server failed to bind port 67: %s', exc)
            return

        # When management pool is enabled, allocate DHCP IPs from that range so
        # the lease address IS the permanent management IP (no IP change on reload).
        if (settings.get('ztp_mgmt_pool_enabled') == 'true'
                and settings.get('ztp_mgmt_pool_start')):
            pool_start = settings.get('ztp_mgmt_pool_start')
            pool_end   = settings.get('ztp_mgmt_pool_end', pool_start)
            log.info('DHCP server using management pool range %s – %s', pool_start, pool_end)
        else:
            pool_start = settings.get('ztp_dhcp_range_start', '192.168.2.100')
            pool_end   = settings.get('ztp_dhcp_range_end',   '192.168.2.200')
            log.info('DHCP server using DHCP range %s – %s', pool_start, pool_end)

        with sock:
            while not self._stop.is_set():
                try:
                    data, addr = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    self._handle(sock, data, addr, pool_start, pool_end)
                except Exception as exc:
                    log.debug('DHCP handler error: %s', exc)

    # ------------------------------------------------------------------
    def _handle(self, sock: socket.socket, data: bytes, addr,
                pool_start: str, pool_end: str):
        try:
            pkt = _Pkt(data)
        except ValueError:
            return

        if pkt.op != BOOT_REQUEST:
            return

        # Silently ignore non-Arista clients
        if 'Arista' not in pkt.vendor_class:
            return

        # Re-read settings on every packet so URL changes take effect live
        settings = self._get_settings()
        server_ip = self._server_ip or '0.0.0.0'

        if pkt.msg_type == MSG_DISCOVER:
            # Exclude IPs already used by registered devices so a pool restart
            # never re-offers an IP that has been permanently assigned.
            exclude = self._get_used_ips() if self._get_used_ips else None
            offered = self._pool.allocate(pkt.mac, pool_start, pool_end, pkt.client_hostname, exclude)
            if not offered:
                log.warning('DHCP pool exhausted — cannot serve %s', pkt.mac)
                return
            reply = _build_reply(pkt, MSG_OFFER, offered, server_ip, settings)
            log.info('DHCP OFFER → %s  IP=%s  boot=%s/ztp/script',
                     pkt.mac, offered,
                     settings.get('ztp_karman_url', '').rstrip('/'))
            self._send(sock, pkt, reply)

        elif pkt.msg_type == MSG_REQUEST:
            # Honor only if we have a lease for this client
            offered = self._pool.lookup(pkt.mac)
            if not offered:
                return
            reply = _build_reply(pkt, MSG_ACK, offered, server_ip, settings)
            log.info('DHCP ACK  → %s  IP=%s', pkt.mac, offered)
            self._send(sock, pkt, reply)

    @staticmethod
    def _send(sock: socket.socket, pkt: _Pkt, reply: bytes):
        # Use broadcast if client has no IP yet or set broadcast flag
        if pkt.ciaddr == b'\x00\x00\x00\x00' or (pkt.flags & 0x8000):
            dest = ('<broadcast>', 68)
        else:
            dest = (socket.inet_ntoa(pkt.ciaddr), 68)
        sock.sendto(reply, dest)
