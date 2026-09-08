"""Access control for non-local serving: a shared token and a self-signed TLS certificate.

Lightman handles biometric data, so binding to anything but the loopback interface requires a
token. The token travels once in the URL (`?token=`), is stored in an HttpOnly cookie and is
checked on every request and on the WebSocket. Browsers only allow camera/microphone capture
on secure origins, so a certificate is generated on first use (self-signed; the browser will
ask you to trust it once).
"""

from __future__ import annotations

import datetime as dt
import hmac
import ipaddress
import secrets
import socket
from pathlib import Path

from platformdirs import user_config_dir
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.websockets import WebSocket

COOKIE = "lightman_token"
HEADER = "x-lightman-token"


def new_token() -> str:
    return secrets.token_urlsafe(24)


def token_ok(supplied: str | None, expected: str | None) -> bool:
    if expected is None:
        return True
    if not supplied:
        return False
    return hmac.compare_digest(supplied, expected)


def ws_token(ws: WebSocket) -> str | None:
    return ws.cookies.get(COOKIE) or ws.headers.get(HEADER) or ws.query_params.get("token")


class TokenMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied = request.cookies.get(COOKIE) or request.headers.get(HEADER)
        query = request.query_params.get("token")
        if query is not None and token_ok(query, self.token):
            # Move the token from the URL into a cookie and drop it from the address bar.
            clean = request.url.remove_query_params("token")
            resp: Response = RedirectResponse(str(clean), status_code=303)
            resp.set_cookie(
                COOKIE, self.token, httponly=True, samesite="strict",
                secure=request.url.scheme == "https", max_age=12 * 3600,
            )  # fmt: skip
            return resp
        if not token_ok(supplied, self.token):
            return JSONResponse(
                {"detail": "token required: open the URL printed by `lightman serve`"},
                status_code=401,
            )
        return await call_next(request)


def lan_addresses() -> list[str]:
    out: list[str] = []
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            ip = str(info[4][0])
            if not ip.startswith("127.") and ip not in out:
                out.append(ip)
    except OSError:
        pass
    try:  # default-route interface
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("127.") and ip not in out:
            out.insert(0, ip)
    except OSError:
        pass
    return out


def tls_dir() -> Path:
    return Path(user_config_dir("lightman", appauthor=False)) / "tls"


def ensure_self_signed_cert(hosts: list[str], *, days: int = 825) -> tuple[Path, Path]:
    """Create (once) and return (cert_path, key_path) for the given hosts/IPs."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    d = tls_dir()
    d.mkdir(parents=True, exist_ok=True)
    cert_path, key_path = d / "lightman-cert.pem", d / "lightman-key.pem"
    if cert_path.is_file() and key_path.is_file():
        return cert_path, key_path
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "lightman-local")])
    sans: list[x509.GeneralName] = [x509.DNSName("localhost")]
    for h in hosts:
        try:
            sans.append(x509.IPAddress(ipaddress.ip_address(h)))
        except ValueError:
            sans.append(x509.DNSName(h))
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path
