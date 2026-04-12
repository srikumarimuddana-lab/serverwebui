import os
import ssl
import sys
import datetime
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _generate_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=4096)


def _save_key(key: rsa.RSAPrivateKey, path: str):
    with open(path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    # os.chmod is a no-op on Windows for fine-grained permission control,
    # but we call it anyway on POSIX to restrict key file access.
    if sys.platform != "win32":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def _save_cert(cert: x509.Certificate, path: str):
    with open(path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))


def generate_ca(cert_dir: str) -> tuple[str, str]:
    os.makedirs(cert_dir, exist_ok=True)
    key = _generate_key()
    key_path = os.path.join(cert_dir, "ca.key")
    cert_path = os.path.join(cert_dir, "ca.crt")

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Server WebUI CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Server WebUI"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    _save_key(key, key_path)
    _save_cert(cert, cert_path)
    return key_path, cert_path


def generate_agent_cert(cert_dir: str, ca_key_path: str, ca_cert_path: str, hostname: str) -> tuple[str, str]:
    os.makedirs(cert_dir, exist_ok=True)

    with open(ca_key_path, "rb") as f:
        ca_key = serialization.load_pem_private_key(f.read(), password=None)
    with open(ca_cert_path, "rb") as f:
        ca_cert = x509.load_pem_x509_certificate(f.read())

    key = _generate_key()
    key_path = os.path.join(cert_dir, f"{hostname}.key")
    cert_path = os.path.join(cert_dir, f"{hostname}.crt")

    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, hostname),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(hostname)]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    _save_key(key, key_path)
    _save_cert(cert, cert_path)
    return key_path, cert_path


def load_ssl_context(cert_path: str, key_path: str, ca_cert_path: str) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_cert_chain(cert_path, key_path)
    ctx.load_verify_locations(ca_cert_path)
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx
