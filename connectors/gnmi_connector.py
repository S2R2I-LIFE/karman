#!/usr/bin/env python3
"""
gNMI Connector
gRPC Network Management Interface connection to Arista TerminAttr.

Requires pygnmi: pip install pygnmi
TerminAttr listens on port 6030 by default.

TLS handling:
  - Default (insecure=False): TLS with TOFU — fetches the device's self-signed
    certificate on first connect and trusts it. Works for both lab (self-signed)
    and production (CA-signed) certs with zero pre-configuration.
  - insecure=True: Plaintext gRPC. Only use if the device is configured with
    a flag that disables TLS on its gNMI listener.
"""

import os
import sys
import ssl
import base64
import socket
import tempfile
from typing import Dict, List, Optional

GNMI_AVAILABLE = False
try:
    from pygnmi.client import gNMIclient
    GNMI_AVAILABLE = True

    class _GNMIclient(gNMIclient):
        """
        Subclass that tolerates UNIMPLEMENTED from the Capabilities RPC.

        Some TerminAttr versions do not implement gNMI Capabilities even
        though they implement Get/Subscribe. pygnmi calls capabilities()
        inside connect() and raises an exception on failure — this subclass
        catches that so the connection can proceed.
        """
        def capabilities(self):
            try:
                return super().capabilities()
            except Exception:
                return {}

        def get(self, path=None, **kwargs):
            """
            Override to inject a per-call gRPC timeout that pygnmi omits.

            pygnmi passes timeout only to grpc.channel_ready_future() during
            __enter__(), but NOT to the actual stub.Get() RPC call.  Without a
            deadline the call blocks indefinitely when the server stalls (e.g.
            management api gnmi + eos_native path on vEOS-lab).  We monkey-patch
            the stub for the duration of this call to add the timeout.
            """
            stub = self._gNMIclient__stub
            original_Get = stub.Get
            timeout = getattr(self, 'timeout', 30)

            def _timed_Get(request, metadata=None, **kw):
                kw.setdefault('timeout', timeout)
                return original_Get(request, metadata=metadata, **kw)

            stub.Get = _timed_Get
            try:
                return super().get(path=path, **kwargs)
            finally:
                stub.Get = original_Get

except ImportError:
    pass


class GNMIConnector:
    """
    gNMI connector for Arista TerminAttr.

    Connects via gRPC on port 6030 (TerminAttr default).
    Uses TOFU (Trust On First Use) by default so it works with Arista's
    self-signed certificates in lab environments without any cert management.

    Usage:
        connector = GNMIConnector(host='192.168.1.1', username='admin', password='pass')
        if connector.connect():
            result = connector.get('openconfig-interfaces:interfaces')
            connector.disconnect()
    """

    def __init__(self, host: str, port: int = 6030, username: str = "",
                 password: str = "", insecure: bool = False, timeout: int = 30):
        """
        Args:
            host:     Device IP address or hostname
            port:     gNMI port (default 6030 for Arista TerminAttr)
            username: Device username
            password: Device password
            insecure: True = plaintext gRPC (device must disable TLS).
                      False (default) = TLS with TOFU, works with self-signed certs.
            timeout:  gRPC call timeout in seconds
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.insecure = insecure
        self.timeout = timeout
        self._client = None
        self._connected = False

    @staticmethod
    def is_available() -> bool:
        """Check whether the pygnmi library is installed."""
        return GNMI_AVAILABLE

    @staticmethod
    def _fetch_server_cert(host: str, port: int, timeout: int = 5) -> Optional[bytes]:
        """
        Fetch the TLS certificate presented by the gNMI server without verifying it.

        This enables TOFU (Trust On First Use): we accept whatever certificate
        the device presents and use it as the trusted root for the gRPC connection.
        Works with Arista's self-signed TerminAttr certificates and with
        CA-signed production certificates alike.

        Returns PEM-encoded certificate bytes, or None if the fetch fails
        (e.g. the server is using plaintext, not TLS).
        """
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            with socket.create_connection((host, port), timeout=timeout) as raw_sock:
                with ctx.wrap_socket(raw_sock, server_hostname=host) as tls_sock:
                    cert_der = tls_sock.getpeercert(binary_form=True)

            if not cert_der:
                return None

            pem = b"-----BEGIN CERTIFICATE-----\n"
            pem += base64.encodebytes(cert_der)
            pem += b"-----END CERTIFICATE-----\n"
            return pem

        except Exception as e:
            print(f"gNMI TLS cert fetch failed for {host}:{port}: {e}",
                  file=sys.stderr)
            return None

    def connect(self) -> bool:
        """
        Establish a gNMI connection to TerminAttr.

        Auto-detects whether the server uses TLS or plaintext:
          1. Attempts to fetch the server's TLS certificate (TOFU).
          2. If TLS is confirmed  → connects with that cert as the trusted root.
          3. If no TLS detected  → falls back to plaintext gRPC automatically.

        This handles both vEOS-lab (plaintext by default) and production
        TerminAttr (TLS) without any manual configuration.

        Returns True if the connection succeeded, False otherwise.
        """
        if not GNMI_AVAILABLE:
            print("pygnmi is not installed. Run: pip install pygnmi",
                  file=sys.stderr)
            return False

        try:
            if self.insecure:
                # Explicit plaintext mode requested
                self._client = _GNMIclient(
                    target=(self.host, self.port),
                    username=self.username,
                    password=self.password,
                    insecure=True,
                    timeout=self.timeout,
                )
            else:
                # Auto-detect: try TLS first, fall back to plaintext
                cert_pem = self._fetch_server_cert(self.host, self.port)

                if cert_pem:
                    # Server uses TLS — connect with TOFU cert as trusted root
                    fd, cert_path = tempfile.mkstemp(suffix='.pem')
                    try:
                        os.write(fd, cert_pem)
                        os.close(fd)
                        self._client = _GNMIclient(
                            target=(self.host, self.port),
                            username=self.username,
                            password=self.password,
                            insecure=False,
                            path_cert=cert_path,
                            timeout=self.timeout,
                        )
                    finally:
                        os.unlink(cert_path)
                else:
                    # No TLS detected (plaintext gRPC server) — connect insecure
                    print(f"gNMI {self.host}:{self.port} is plaintext, connecting without TLS",
                          file=sys.stderr)
                    self._client = _GNMIclient(
                        target=(self.host, self.port),
                        username=self.username,
                        password=self.password,
                        insecure=True,
                        timeout=self.timeout,
                    )

            self._client.__enter__()
            self._connected = True
            return True

        except Exception as e:
            print(f"gNMI connection failed to {self.host}:{self.port}: {e}",
                  file=sys.stderr)
            # Close the gRPC channel if it was opened before the error — its
            # background _poll_connectivity thread would otherwise leak forever.
            if self._client is not None:
                try:
                    self._client.__exit__(None, None, None)
                except Exception:
                    pass
                self._client = None
            self._connected = False
            return False

    def disconnect(self):
        """Close the gNMI connection gracefully."""
        if self._client is not None:
            try:
                self._client.__exit__(None, None, None)
            except Exception:
                pass
        self._connected = False
        self._client = None

    def get(self, path: str) -> Optional[Dict]:
        """
        Send a gNMI Get RPC for a single OpenConfig / Arista path.

        Returns the parsed GetResponse dict or None on error.
        """
        if not self._connected or not self._client:
            return None
        try:
            return self._client.get(path=[path])
        except Exception as e:
            print(f"gNMI get failed for '{path}': {e}", file=sys.stderr)
            return None

    def get_multi(self, paths: List[str]) -> Optional[Dict]:
        """
        Send a single gNMI Get RPC for multiple paths (reduces round-trips).

        Returns the parsed GetResponse dict or None on error.
        """
        if not self._connected or not self._client:
            return None
        try:
            return self._client.get(path=paths)
        except Exception as e:
            print(f"gNMI get_multi failed for paths {paths}: {e}", file=sys.stderr)
            return None

    def capabilities(self) -> Optional[Dict]:
        """
        Query the device's gNMI Capabilities.

        Returns the parsed CapabilityResponse dict or None on error.
        """
        if not self._connected or not self._client:
            return None
        try:
            return self._client.capabilities()
        except Exception as e:
            print(f"gNMI capabilities failed: {e}", file=sys.stderr)
            return None
