import { sleep } from 'k6';
import { users, location } from './lib/config.js';
import { postCheckin } from './lib/client.js';
import { uuidv4 } from './lib/utils.js';

export const options = {
  scenarios: {
    burst_checkin_36: {
      executor: 'per-vu-iterations',
      vus: 36,
      iterations: 1,
      maxDuration: '2m',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.02'],
    http_req_duration: ['p(95)<2500'],
    checkin_success: ['rate>0.98'],
  },
};

export default function () {
  const idx = (__VU - 1) % users.length;
  const user = users[idx];
  const correlationId = `lt-checkin-${uuidv4()}`;

  postCheckin({ user, location, correlationId });

  sleep(0.1);
}
