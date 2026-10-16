import pickle

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


def test_context_trusts_only_the_given_bundle():
    assert fnsi_ssl_context().get_ca_certs() == []


def test_final_https_pool_gets_ca_bundle_and_fnsi_context(tmp_path):
    ca = tmp_path / "ca.pem"
    ca.write_text("")
    adapter = FnsiTLSAdapter()
    request = requests.Request("GET", "https://nsi.rosminzdrav.ru/").prepare()

    for proxies in (None, {"https": "http://proxy.local:3128"}):
        pool = adapter.get_connection_with_tls_context(
            request, verify=str(ca), proxies=proxies
        )
        assert pool.ca_certs == str(ca)
        assert pool.cert_reqs == "CERT_REQUIRED"
        context = pool.conn_kw["ssl_context"]
        assert "AES128-GCM-SHA256" in [c["name"] for c in context.get_ciphers()]


def test_each_ca_bundle_gets_its_own_context_and_pool(tmp_path):
    adapter = FnsiTLSAdapter()
    request = requests.Request("GET", "https://nsi.rosminzdrav.ru/").prepare()
    pools = []
    for name in ("a.pem", "b.pem", "a.pem"):
        (tmp_path / name).write_text("")
        pools.append(
            adapter.get_connection_with_tls_context(
                request, verify=str(tmp_path / name)
            )
        )

    assert pools[0] is pools[2]
    assert pools[0] is not pools[1]
    assert pools[0].conn_kw["ssl_context"] is not pools[1].conn_kw["ssl_context"]


def test_verify_false_gets_non_verifying_context():
    adapter = FnsiTLSAdapter()
    request = requests.Request("GET", "https://nsi.rosminzdrav.ru/").prepare()
    pool = adapter.get_connection_with_tls_context(request, verify=False)
    context = pool.conn_kw["ssl_context"]
    assert not context.check_hostname
    assert context.verify_mode.name == "CERT_NONE"


def test_adapter_survives_pickling():
    adapter = pickle.loads(pickle.dumps(FnsiTLSAdapter()))
    request = requests.Request("GET", "https://nsi.rosminzdrav.ru/").prepare()
    pool = adapter.get_connection_with_tls_context(request, verify=True)
    assert "ssl_context" in pool.conn_kw
