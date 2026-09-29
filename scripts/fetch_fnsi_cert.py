#!/usr/bin/env python3
"""
Получает цепочку сертификатов ФНСИ с сервера nsi.rosminzdrav.ru
и сохраняет её в env/crts/rosminzdrav.crt.

Запуск:
    poetry run python scripts/fetch_fnsi_cert.py
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CERT_DIR = PROJECT_ROOT / "env" / "crts"
CERT_PATH = CERT_DIR / "rosminzdrav.crt"
HOST = "nsi.rosminzdrav.ru"


def fetch_cert():
    """Получает полную цепочку сертификатов через openssl s_client."""
    CERT_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        "openssl",
        "s_client",
        "-connect",
        f"{HOST}:443",
        "-servername",
        HOST,
        "-showcerts",
    ]

    print(f"Получаю сертификаты с {HOST}...")
    proc = subprocess.run(
        cmd,
        input=b"",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if proc.returncode != 0:
        print(
            f"Ошибка openssl: {proc.stderr.decode('utf-8', errors='ignore')}",
            file=sys.stderr,
        )
        return False

    output = proc.stdout.decode("utf-8", errors="ignore")

    # Извлекаем все блоки -----BEGIN CERTIFICATE----- ... -----END CERTIFICATE-----
    certs = []
    current = []
    in_cert = False
    for line in output.splitlines():
        if line.strip() == "-----BEGIN CERTIFICATE-----":
            in_cert = True
            current = [line]
        elif in_cert:
            current.append(line)
            if line.strip() == "-----END CERTIFICATE-----":
                certs.append("\n".join(current) + "\n")
                in_cert = False
                current = []

    if not certs:
        print("Не удалось извлечь сертификаты из ответа openssl", file=sys.stderr)
        return False

    CERT_PATH.write_text("".join(certs), encoding="utf-8")
    print(f"Сохранено {len(certs)} сертификат(ов) в {CERT_PATH}")

    # Проверяем, что файл корректен
    verify_proc = subprocess.run(
        ["openssl", "verify", "-CAfile", str(CERT_PATH), str(CERT_PATH)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    print(f"Проверка сертификата: {verify_proc.stdout.strip()}")
    if verify_proc.returncode != 0:
        print(
            f"Предупреждение при проверке: {verify_proc.stderr.strip()}",
            file=sys.stderr,
        )

    return True


if __name__ == "__main__":
    success = fetch_cert()
    sys.exit(0 if success else 1)
