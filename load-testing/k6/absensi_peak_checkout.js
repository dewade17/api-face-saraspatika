import { sleep } from 'k6';
import { users, location } from './lib/config.js';
import { postCheckin, postCheckout, getStatus } from './lib/client.js';
import { uuidv4, envNumber } from './lib/utils.js';

export const options = {
  scenarios: {
    burst_checkout_36: {
      executor: 'per-vu-iterations',
      vus: 36,
      iterations: 1,
      maxDuration: '3m',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.02'],
    http_req_duration: ['p(95)<2500'],
    checkout_success: ['rate>0.98'],
  },
};

function statusHasCheckinItem(statusRes) {
  try {
    const body = statusRes.json();
    return body && body.ok === true && body.item !== null;
  } catch (_) {
    return false;
  }
}

export function setup() {
  const correlationIds = {};
  for (const u of users) {
    const correlationId = `lt-flow-${uuidv4()}`;
    correlationIds[u.user_id] = correlationId;
    postCheckin({ user: u, location, correlationId });
    sleep(0.05);
  }

  const timeoutSec = envNumber('CHECKIN_POLL_TIMEOUT_SEC', 60);
  const start = Date.now();
  let allReady = false;

  while (!allReady && (Date.now() - start) / 1000 < timeoutSec) {
    allReady = true;
    for (const u of users) {
      const st = getStatus({ user: u });
      if (!statusHasCheckinItem(st)) {
        allReady = false;
        break;
      }
    }
    if (!allReady) sleep(1);
  }

  return { correlationIds };
}

export default function (data) {
  const idx = (__VU - 1) % users.length;
  const user = users[idx];
  const correlationId = data.correlationIds[user.user_id];

  postCheckout({ user, location, correlationId });
  sleep(0.1);
}
