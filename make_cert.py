import datetime, ipaddress, socket
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
lan_ip = socket.gethostbyname(socket.gethostname())
names = [x509.DNSName("localhost"),
         x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
try:
    names.append(x509.IPAddress(ipaddress.ip_address(lan_ip)))
except ValueError:
    pass

subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
now = datetime.datetime.now(datetime.timezone.utc)
cert = (x509.CertificateBuilder()
        .subject_name(subject).issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(names), critical=False)
        .sign(key, hashes.SHA256()))

open("key.pem", "wb").write(key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption()))
open("cert.pem", "wb").write(cert.public_bytes(serialization.Encoding.PEM))

print("Created cert.pem and key.pem")
print(f"On the phone open:  https://{lan_ip}:8501")
