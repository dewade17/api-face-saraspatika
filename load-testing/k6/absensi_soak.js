import { sleep } from 'k6';
import { users, location } from './lib/config.js';
import { postCheckin, postCheckout } from './lib/client.js';
import { uuidv4, envOr } from './lib/utils.js';

const SOAK_DURATION = envOr('SOAK_DURATION', '15m');
const PACE_SEC = Number(envOr('SOAK_PACE_SEC', '5'));

export const options = {
  scenarios: {
    soak_36_vus: {
      executor: 'constant-vus',
      vus: 36,
      duration: SOAK_DURATION,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.02'],
    http_req_duration: ['p(95)<3000'],
    checkin_success: ['rate>0.98'],
    checkout_success: ['rate>0.98'],
  },
};

export function setup() {
  const correlationIds = {};
  for (const u of users) {
    correlationIds[u.user_id] = `lt-soak-${uuidv4()}`;
  }
  return { correlationIds };
}

export default function (data) {
  const idx = (__VU - 1) % users.length;
  const user = users[idx];
  const correlationId = data.correlationIds[user.user_id];

  if ((__ITER % 2) === 0) {
    postCheckin({ user, location, correlationId });
  } else {
    postCheckout({ user, location, correlationId });
  }

  sleep(PACE_SEC);
}
