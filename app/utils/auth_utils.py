"""
Utility functions related to authentication and token validation.

This module replaces the previous placeholder implementation with a real
JWT-based token verification mechanism.  Tokens issued by the Next.js
application (``saraspatika``) use the HS256 algorithm and include a
``sub`` claim for the user identifier as well as an ``exp`` expiration
timestamp.  To share authentication between the JavaScript frontend and
this Flask API, we validate incoming tokens using the same secret and
return appropriate HTTP 401 responses when the token is missing or
invalid.

The verification logic avoids external dependencies by using Python's
``hmac`` and ``hashlib`` libraries to compute the HMAC signature.
Environment variable ``JWT_SECRET`` must be set to the same value used
by the Next.js application.  If it is not set, an empty string is used
which will cause all tokens to fail verification.
"""

import base64
import hmac
import hashlib
import json
import os
import time
from functools import wraps
from flask import request, jsonify, g


def _base64url_decode(data: str) -> bytes:
    """Decode a base64url-encoded string.

    JWT segments are base64url-encoded without padding.  This helper
    adds the required padding before decoding.
    """
    # Calculate missing padding and add it
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _verify_jwt(token: str) -> dict:
    """Verify a HS256 JWT and return its payload.

    The function decodes the header, payload and signature from the
    incoming token, computes the expected HMAC-SHA256 signature using
    the ``JWT_SECRET`` environment variable and compares it with the
    provided signature.  It also checks the ``exp`` claim to ensure
    that the token has not expired.  If verification fails, a
    ``ValueError`` is raised.

    :param token: The raw JWT from the request.
    :returns: The decoded payload as a dictionary.
    :raises ValueError: If the token is malformed, has an invalid
        signature or has expired.
    """
    try:
        header_b64, payload_b64, signature_b64 = token.split('.')
    except ValueError:
        raise ValueError('Token format tidak valid')

    # Compute expected signature
    signing_input = f'{header_b64}.{payload_b64}'.encode('utf-8')
    secret = os.getenv('JWT_SECRET', '')
    if not isinstance(secret, bytes):
        secret_bytes = secret.encode('utf-8')
    else:
        secret_bytes = secret
    expected_sig = hmac.new(secret_bytes, signing_input, hashlib.sha256).digest()
    try:
        provided_sig = _base64url_decode(signature_b64)
    except Exception:
        raise ValueError('Signature tidak valid')
    # Compare signatures securely
    if not hmac.compare_digest(expected_sig, provided_sig):
        raise ValueError('Signature token tidak valid')

    # Decode and parse payload
    try:
        payload_bytes = _base64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode('utf-8'))
    except Exception:
        raise ValueError('Payload token tidak valid')

    # Expiration check
    exp = payload.get('exp')
    if exp is not None:
        # ``exp`` in JWT is usually expressed as seconds since the Unix epoch.
        try:
            exp_ts = float(exp)
        except Exception:
            raise ValueError('Claim exp tidak valid')
        now = time.time()
        if now >= exp_ts:
            raise ValueError('Token sudah kedaluwarsa')

    return payload


def token_required(f):
    """Decorator to enforce authentication via JWT on Flask endpoints.

    This decorator mirrors the authentication logic used throughout the
    ``saraspatika`` backend.  It attempts to extract a bearer token from
    the ``Authorization`` header.  If no header is present or it does
    not contain a bearer token, the ``access_token`` cookie is checked
    instead.  The token is then verified using :func:`_verify_jwt`.  On
    success the decoded payload is stored on Flask's global ``g``
    context under ``g.current_token_payload`` and the wrapped function
    is executed.  If verification fails, a JSON error response with a
    401 status code is returned.
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        # 1. Attempt to read bearer token from Authorization header
        auth_header = request.headers.get('Authorization') or request.headers.get('authorization')
        token = None
        if auth_header and auth_header.lower().startswith('bearer '):
            token = auth_header.split(' ', 1)[1].strip()

        # 2. Fall back to access_token cookie if header not provided
        if not token:
            token = request.cookies.get('access_token')

        if not token:
            # No token found – return 401 Unauthorized
            return (
                jsonify(ok=False, error='Unauthorized', detail='Token tidak ditemukan'),
                401,
            )

        try:
            payload = _verify_jwt(token)
        except ValueError as e:
            # Invalid token or signature
            return (
                jsonify(ok=False, error='Unauthorized', detail=str(e)),
                401,
            )

        # Store payload in the Flask global context for downstream use
        g.current_token_payload = payload

        return f(*args, **kwargs)

    return decorated


def get_user_id_from_auth() -> str | None:
    """Extract the current user identifier from the authenticated token.

    Use this helper within routes to retrieve the ``sub`` claim from the
    decoded JWT payload.  If no token has been validated yet (for
    instance, if :func:`token_required` has not been applied), ``None``
    is returned.
    """
    payload = getattr(g, 'current_token_payload', None)
    if not payload:
        return None
    # The ``sub`` claim represents the subject (user identifier) in JWT
    sub = payload.get('sub')
    return str(sub).strip() if sub else None