"""
HTTP session for FNSI (nsi.rosminzdrav.ru) with a compatible TLS cipher list.

Since 2026-10-14 the FNSI server accepts only TLS 1.2 with the
AES128-GCM-SHA256 cipher (RSA key exchange). Python >= 3.10 excludes
non-forward-secret ciphers from ``ssl.create_default_context()``, so the
handshake fails with ``UNEXPECTED_EOF_WHILE_READING``. This module keeps the
default ECDHE ciphers first and appends AES128-GCM-SHA256 as a fallback.
"""

import ssl

import requests
from requests.adapters import HTTPAdapter

# ECDHE suites stay preferred; RSA key exchange is only a fallback for FNSI
FNSI_TLS12_CIPHERS = "ECDHE+AESGCM:ECDHE+CHACHA20:AES128-GCM-SHA256"


def fnsi_ssl_context() -> ssl.SSLContext:
    """Return a verifying SSL context that also allows AES128-GCM-SHA256."""
    context = ssl.create_default_context()
    context.set_ciphers(FNSI_TLS12_CIPHERS)
    return context


class FnsiTLSAdapter(HTTPAdapter):
    """HTTPAdapter that uses :func:`fnsi_ssl_context` for direct and proxied HTTPS."""

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = fnsi_ssl_context()
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        proxy_kwargs["ssl_context"] = fnsi_ssl_context()
        return super().proxy_manager_for(proxy, **proxy_kwargs)


def fnsi_session() -> requests.Session:
    """Create a ``requests.Session`` able to connect to the FNSI server."""
    session = requests.Session()
    session.mount("https://", FnsiTLSAdapter())
    return session
