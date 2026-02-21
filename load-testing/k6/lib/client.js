import http from 'k6/http';
import { check } from 'k6';
import { Rate } from 'k6/metrics';
import { makeUserToken } from './jwt.js';
import { envOr } from './utils.js';

export const checkin_success = new Rate('checkin_success');
export const checkout_success = new Rate('checkout_success');
export const status_success = new Rate('status_success');

const IMG_BYTES = open('./assets/shared/all-users-use.jpeg', 'b');

export function apiBase() {
  const fromBaseUrl = envOr('BASE_URL', '');
  if (fromBaseUrl) return fromBaseUrl;

  const fromPublicApiBase = envOr('NEXT_PUBLIC_API_BASE_URL', '');
  if (fromPublicApiBase) return fromPublicApiBase;

  const fromPublicApiFace = envOr('NEXT_PUBLIC_API_FACE_URL', '');
  if (fromPublicApiFace) return fromPublicApiFace;

  return envOr('APP_URL', 'http://localhost:8000');
}

export function jwtSecret() {
  return envOr('JWT_SECRET', '');
}

export function authHeaderForUser(userId) {
  const token = makeUserToken(userId, jwtSecret());
  return { Authorization: `Bearer ${token}` };
}

export function postCheckin({ user, location, correlationId }) {
  const url = `${apiBase()}/api/absensi/checkin`;
  const payload = {
    user_id: user.user_id,
    location_id: location.id_lokasi,
    lat: location.latitude,
    lng: location.longitude,
    correlation_id: correlationId,
    captured_at: new Date().toISOString(),
    image: http.file(IMG_BYTES, 'face.jpeg', 'image/jpeg'),
  };

  const res = http.post(url, payload, {
    headers: {
      ...authHeaderForUser(user.user_id),
    },
    timeout: '60s',
  });

  const ok200 = res.status === 200;
  checkin_success.add(ok200);

  check(res, {
    'checkin status 200': () => ok200,
  });

  return res;
}

export function postCheckout({ user, location, correlationId }) {
  const url = `${apiBase()}/api/absensi/checkout`;
  const payload = {
    user_id: user.user_id,
    location_id: location.id_lokasi,
    lat: location.latitude,
    lng: location.longitude,
    correlation_id: correlationId,
    captured_at: new Date().toISOString(),
    image: http.file(IMG_BYTES, 'face.jpeg', 'image/jpeg'),
  };

  const res = http.post(url, payload, {
    headers: {
      ...authHeaderForUser(user.user_id),
    },
    timeout: '60s',
  });

  const ok200 = res.status === 200;
  checkout_success.add(ok200);

  check(res, {
    'checkout status 200': () => ok200,
  });

  return res;
}

export function getStatus({ user }) {
  const url = `${apiBase()}/api/absensi/status?user_id=${encodeURIComponent(user.user_id)}`;
  const res = http.get(url, {
    headers: {
      ...authHeaderForUser(user.user_id),
    },
    timeout: '60s',
  });

  const ok200 = res.status === 200;
  status_success.add(ok200);

  check(res, {
    'status status 200': () => ok200,
  });

  return res;
}
