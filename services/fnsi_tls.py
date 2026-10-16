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
from urllib3.util.ssl_ import create_urllib3_context

# ECDHE suites stay preferred; RSA key exchange is only a fallback for FNSI
FNSI_TLS12_CIPHERS = "ECDHE+AESGCM:ECDHE+CHACHA20:AES128-GCM-SHA256"


def fnsi_ssl_context(verify: bool = True) -> ssl.SSLContext:
    """Return an SSL context that also allows AES128-GCM-SHA256.

    The urllib3 context loads no CA certificates itself, so ``verify=<path>``
    keeps requests' semantics: only that bundle is trusted.
    """
    cert_reqs = ssl.CERT_REQUIRED if verify else ssl.CERT_NONE
    return create_urllib3_context(ciphers=FNSI_TLS12_CIPHERS, cert_reqs=cert_reqs)


class FnsiTLSAdapter(HTTPAdapter):
    """HTTPAdapter that uses :func:`fnsi_ssl_context` for direct and proxied HTTPS.

    urllib3 loads the ``verify`` bundle into the context it is given, so one
    shared context would accumulate trusted CAs across requests. A separate
    context is kept per ``verify``/``cert`` value and passed through the pool
    key, which also isolates the pools themselves.
    """

    def __init__(self, *args, **kwargs):
        self._ssl_contexts: dict = {}
        super().__init__(*args, **kwargs)

    def __setstate__(self, state):
        # HTTPAdapter.__setstate__ skips __init__; SSL contexts are not picklable
        self._ssl_contexts = {}
        super().__setstate__(state)

    def build_connection_pool_key_attributes(self, request, verify, cert=None):
        host_params, pool_kwargs = super().build_connection_pool_key_attributes(
            request, verify, cert
        )
        if host_params["scheme"] == "https":
            key = (verify, cert if not isinstance(cert, list) else tuple(cert))
            if key not in self._ssl_contexts:
                self._ssl_contexts[key] = fnsi_ssl_context(verify is not False)
            pool_kwargs["ssl_context"] = self._ssl_contexts[key]
        return host_params, pool_kwargs


def fnsi_session() -> requests.Session:
    """Create a ``requests.Session`` able to connect to the FNSI server."""
    session = requests.Session()
    session.mount("https://", FnsiTLSAdapter())
    return session
