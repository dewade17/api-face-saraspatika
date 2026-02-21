import crypto from 'k6/crypto';

export function uuidv4() {
  // RFC4122 v4 using random bytes
  const b = crypto.randomBytes(16);
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;

  const hex = Array.from(b, (x) => (`0${x.toString(16)}`).slice(-2)).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function envOr(name, fallback) {
  const v = __ENV[name];
  return (v === undefined || v === null || String(v).trim() === '') ? fallback : String(v);
}

export function envNumber(name, fallback) {
  const v = __ENV[name];
  if (v === undefined || v === null || String(v).trim() === '') return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}
