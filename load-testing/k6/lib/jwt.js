import crypto from 'k6/crypto';
import encoding from 'k6/encoding';

function b64urlJSON(obj) {
  return encoding.b64encode(JSON.stringify(obj), 'rawurl');
}

function b64urlFromBase64(b64) {
  return b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

export function signJWT(payload, secret) {
  if (!secret) {
    throw new Error('JWT_SECRET kosong. Set env JWT_SECRET untuk load test.');
  }
  const header = { alg: 'HS256', typ: 'JWT' };
  const h = b64urlJSON(header);
  const p = b64urlJSON(payload);
  const signingInput = `${h}.${p}`;
  const sigB64 = crypto.hmac('sha256', secret, signingInput, 'base64');
  const sig = b64urlFromBase64(sigB64);
  return `${signingInput}.${sig}`;
}

export function makeUserToken(userId, secret, ttlSeconds = 3600) {
  const now = Math.floor(Date.now() / 1000);
  const payload = {
    sub: String(userId),
    iat: now,
    exp: now + ttlSeconds,
  };
  return signJWT(payload, secret);
}
