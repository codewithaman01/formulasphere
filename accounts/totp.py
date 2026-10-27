"""Authenticator-app codes (RFC 6238), using only the standard library."""
import base64
import hashlib
import hmac
import os
import struct
import time
from urllib.parse import quote


def new_secret():
    return base64.b32encode(os.urandom(20)).decode()       # 32 characters, no padding


def code_at(secret, moment=None, step=30, digits=6):
    key = base64.b32decode(secret)
    counter = int((time.time() if moment is None else moment) // step)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = digest[-1] & 15
    value = (struct.unpack(">I", digest[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(value).zfill(digits)


def verify(secret, code, window=1):
    """True if code matches now, or one 30-second step either side (clock drift)."""
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != 6:
        return False
    now = time.time()
    return any(hmac.compare_digest(code_at(secret, now + d * 30), code) for d in range(-window, window + 1))


def uri(secret, username, issuer="FormulaSphere"):
    return f"otpauth://totp/{quote(issuer)}:{quote(username)}?secret={secret}&issuer={quote(issuer)}"
