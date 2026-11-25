"""Gera um certificado TLS autoassinado para rodar o servidor em HTTPS.

Uso:
    python gerar_certificado.py                    # vale para localhost e 127.0.0.1
    python gerar_certificado.py --ip 192.168.0.15  # inclui o IP do PC na rede Wi-Fi

O certificado traz o campo SAN (Subject Alternative Name), que é onde os
navegadores modernos conferem para qual endereço ele vale. Por ser
autoassinado (não emitido por uma autoridade certificadora), o navegador
mostra um aviso na primeira vez; a comunicação é criptografada mesmo assim.

Arquivos gerados (pasta certs/, ignorada pelo git):
    certs/cert.pem  -> certificado público
    certs/key.pem   -> chave privada (NUNCA compartilhe)
"""

import argparse
import ipaddress
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

PASTA = Path(__file__).resolve().parent / "certs"


def ip_da_rede_local() -> str | None:
    """Descobre o IP do PC na rede local (nenhum pacote é enviado)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return None


def gerar(ips_extras: list[str], dias: int = 365) -> None:
    # 1) Par de chaves RSA de 2048 bits.
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    nome = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Frutos de Goiás (desenvolvimento)"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])

    # 2) Endereços para os quais o certificado vale (SAN).
    alt_names: list[x509.GeneralName] = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ]
    for ip in ips_extras:
        alt_names.append(x509.IPAddress(ipaddress.ip_address(ip)))

    agora = datetime.now(timezone.utc)
    # 3) Monta e assina o certificado com a própria chave (autoassinado), SHA-256.
    cert = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - timedelta(minutes=5))
        .not_valid_after(agora + timedelta(days=dias))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(chave, hashes.SHA256())
    )

    PASTA.mkdir(exist_ok=True)
    (PASTA / "key.pem").write_bytes(
        chave.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    (PASTA / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    print(f"Certificado gerado em {PASTA}")
    print("Válido para: localhost, 127.0.0.1" + "".join(f", {ip}" for ip in ips_extras))
    print(f"Validade: {dias} dias")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera certificado TLS autoassinado.")
    parser.add_argument("--ip", action="append", default=[],
                        help="IP da rede local a incluir (pode repetir). Ex.: --ip 192.168.0.15")
    parser.add_argument("--dias", type=int, default=365, help="Validade em dias (padrão 365).")
    args = parser.parse_args()

    for ip in args.ip:
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            parser.error(f"IP inválido: {ip}")

    gerar(args.ip, args.dias)

    detectado = ip_da_rede_local()
    if not args.ip and detectado:
        print(f"\nDica: para acessar pelo celular, gere de novo com:  python gerar_certificado.py --ip {detectado}")


if __name__ == "__main__":
    main()
