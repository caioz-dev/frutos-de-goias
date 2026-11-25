"""Inicia o servidor HTTPS da sorveteria.

Uso:  python servidor.py

O servidor escuta em 0.0.0.0 (todas as interfaces de rede), por isso pode
ser acessado tanto pelo próprio PC quanto por um celular na mesma rede Wi-Fi.
Toda a comunicação navegador <-> servidor passa por TLS (HTTPS), usando o
certificado gerado por gerar_certificado.py.
"""

import os
import ssl
import sys
from pathlib import Path

from app import PASTA_PROJETO, create_app
from gerar_certificado import ip_da_rede_local


def main() -> None:
    app = create_app()
    cert = PASTA_PROJETO / os.environ.get("CERT_ARQUIVO", "certs/cert.pem")
    chave = PASTA_PROJETO / os.environ.get("CHAVE_ARQUIVO", "certs/key.pem")
    porta = int(os.environ.get("PORTA", "5000"))

    if not (Path(cert).exists() and Path(chave).exists()):
        sys.exit("Certificado não encontrado. Rode antes:  python gerar_certificado.py --ip <IP do PC>")

    ip = ip_da_rede_local()
    print("=" * 60)
    print(" Frutos de Goiás - servidor HTTPS iniciado")
    print(f"   No PC:       https://localhost:{porta}")
    if ip:
        print(f"   No celular:  https://{ip}:{porta}  (mesma rede Wi-Fi)")
    print(f"   Área do dono: /admin/login")
    print(" Para parar: Ctrl+C")
    print("=" * 60)

    # Contexto TLS do módulo ssl (biblioteca padrão). Só aceita TLS 1.2 ou
    # superior; versões antigas (SSLv3, TLS 1.0/1.1) têm falhas conhecidas.
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexto.minimum_version = ssl.TLSVersion.TLSv1_2
    contexto.load_cert_chain(certfile=str(cert), keyfile=str(chave))

    # debug=False: o modo debug permite executar código pelo navegador e
    # nunca deve ficar ligado em uma rede compartilhada.
    app.run(host="0.0.0.0", port=porta, ssl_context=contexto, debug=False)


if __name__ == "__main__":
    main()
