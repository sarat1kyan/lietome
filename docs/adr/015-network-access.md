# ADR-015 Network access: token and self-signed TLS

**Context.** Testing from another device on the LAN needs the server bound to a non-loopback
interface. Browsers only allow camera and microphone capture on secure origins, so plain HTTP
on a LAN address cannot run the live tab. The data is biometric, so an open LAN port is not
acceptable.

**Decision.** `lightman serve --host 0.0.0.0` (or any non-loopback host) turns on two things
by default: a random URL token (required on every request; moved from `?token=` into an
HttpOnly, SameSite=Strict cookie by a redirect; also checked on the WebSocket) and TLS with a
self-signed certificate generated once under the user config directory with the LAN IPs and
hostname as subject alternative names (P-256 key, 825 days). The printed URL includes the
token. Localhost serving stays token-free and plain HTTP.

**Rejected.** Serving HTTP on the LAN (no capture possible, no protection), a password form
(more state, no benefit for a single operator), Let's Encrypt (needs a public name), mkcert
(extra install; may be documented later for a trusted local CA).

**Consequences.** The browser shows a certificate warning once per device; accept it. Anyone
with the URL can read sessions until the server stops; the cookie lasts 12 hours. Not a
substitute for real authentication if the tool is ever hosted for more than one operator.
