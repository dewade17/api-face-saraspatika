import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';
import { users } from './lib/config.js';
import { authHeaderForUser, apiBase } from './lib/client.js';

const IMG_BYTES = open('../assets/shared/all-users-use.jpeg', 'b');

// Membuat metrik kustom agar mudah dipantau di akhir
export const enrollSuccess = new Counter('enroll_success_count');
export const enrollErrors = new Counter('enroll_error_count');

export const options = {
  vus: 1, // Tetap 1 VU agar tidak membunuh Celery secara instan
  iterations: users.length,
  thresholds: {
    // Skrip akan ditandai 'FAILED' oleh k6 jika ada 1 saja error yang gagal di-retry
    enroll_error_count: ['count==0'],
  },
};

export default function () {
  const user = users[__ITER];
  const url = `${apiBase()}/api/face/enroll`;

  const payload = {
    user_id: user.user_id,
    images: http.file(IMG_BYTES, 'baseline.jpeg', 'image/jpeg'),
  };

  const params = {
    headers: {
      ...authHeaderForUser(user.user_id),
    },
    timeout: '120s', // Alokasi waktu cukup panjang untuk komputasi AI
  };

  let isSuccess = false;
  let attempts = 0;
  const maxRetries = 3;

  // Loop mekanisme retry
  while (attempts < maxRetries && !isSuccess) {
    attempts++;
    const res = http.post(url, payload, params);

    let isBodyOk = false;
    let errorMessage = '';

    // Mencoba melakukan parsing JSON untuk memastikan sistem benar-benar merespons dengan benar
    try {
      const body = res.json();
      isBodyOk = body && body.ok === true;
      if (!isBodyOk && body && body.error) {
        errorMessage = body.error;
      }
    } catch (e) {
      errorMessage = 'Format respons bukan JSON valid';
    }

    // Validasi ketat
    const passed = check(res, {
      'status is 200': (r) => r.status === 200,
      'response ok is true': () => isBodyOk,
    });

    if (passed) {
      isSuccess = true;
      enrollSuccess.add(1);
      console.log(`[SUCCESS] ${user.email} terdaftar pada percobaan ke-${attempts}.`);

      // Berikan nafas untuk Celery worker (3 detik) sebelum lanjut ke user berikutnya
      sleep(3);
    } else {
      console.warn(`[FAILED] ${user.email} (Percobaan ${attempts}) - Status: ${res.status} - Info: ${errorMessage}`);

      if (attempts < maxRetries) {
        const backoffTime = attempts * 5; // Exponential backoff sederhana: 5s, lalu 10s
        console.log(`[RETRY] Menunggu ${backoffTime} detik sebelum mencoba lagi untuk ${user.email}...`);
        sleep(backoffTime);
      } else {
        console.error(`[GIVE UP] Gagal mendaftarkan wajah untuk ${user.email} setelah ${maxRetries} percobaan maksimal.`);
        enrollErrors.add(1);
      }
    }
  }
}
