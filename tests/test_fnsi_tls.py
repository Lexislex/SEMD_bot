import requests

from services.fnsi_tls import FnsiTLSAdapter, fnsi_session, fnsi_ssl_context


def test_context_allows_fnsi_rsa_cipher_and_keeps_ecdhe_first():
    names = [c["name"] for c in fnsi_ssl_context().get_ciphers()]
    tls12 = [n for n in names if not n.startswith("TLS_")]

    assert "AES128-GCM-SHA256" in tls12
    assert tls12[0].startswith("ECDHE-")
    assert tls12[-1] == "AES128-GCM-SHA256"


def test_context_still_verifies_certificates():
    context = fnsi_ssl_context()
    assert context.check_hostname
    assert context.verify_mode.name == "CERT_REQUIRED"


def test_session_uses_fnsi_adapter_for_https():
    session = fnsi_session()
    assert isinstance(session, requests.Session)
    assert isinstance(
        session.get_adapter("https://nsi.rosminzdrav.ru/"), FnsiTLSAdapter
    )


def test_adapter_passes_context_to_direct_and_proxy_pools():
    adapter = FnsiTLSAdapter()
    direct = adapter.poolmanager.connection_pool_kw["ssl_context"]
    proxied = adapter.proxy_manager_for("http://proxy.local:3128")
    assert "AES128-GCM-SHA256" in [c["name"] for c in direct.get_ciphers()]
    assert "ssl_context" in proxied.connection_pool_kw
