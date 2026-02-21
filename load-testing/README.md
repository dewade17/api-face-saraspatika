# Load Testing - Absensi (Kedatangan & Kepulangan)

Folder ini berisi skrip **k6** untuk menguji **kinerja** dan **daya tahan (soak/endurance)** sistem saat fitur absensi diakses serentak oleh **36 pengguna**.

## Prasyarat
1. **k6** terpasang (lokal) atau gunakan Docker image `grafana/k6`.
2. API sudah berjalan dan bisa diakses dari mesin yang menjalankan k6.
3. Pastikan environment API memiliki `JWT_SECRET` yang sama dengan yang dipakai skrip k6 (agar token valid).
4. Pastikan 36 user pada `config/users_ids_36.json` sudah ada di database dan punya permission:
   - `absensi:create` (check-in)
   - `absensi:update` (check-out)
   - `absensi:read` (status, dipakai untuk polling pada skenario checkout)

## Konfigurasi
- `config/users_ids_36.json` : daftar 36 user (UUID + email + role)
- `config/location.json` : lokasi (id_lokasi + koordinat)
- `assets/shared/all-users-use.jpeg` : foto yang dipakai untuk request multipart `image`
- `BASE_URL` : opsional. Jika tidak diisi, skrip akan mencoba otomatis:
  `NEXT_PUBLIC_API_BASE_URL` -> `NEXT_PUBLIC_API_FACE_URL` -> `APP_URL` -> `http://localhost:8000`

> Catatan: Jika verifikasi wajah gagal untuk user tertentu, pastikan foto ini sesuai dengan data embedding user tsb.

## Menjalankan (pilih salah satu cara)

### Opsi A — Docker (direkomendasikan)
Jalankan dari folder `load-testing`:

#### Linux (API jalan di host yang sama)
```bash
cd load-testing
BASE_URL="http://127.0.0.1:8000" JWT_SECRET="CHANGE_ME" \
  docker run --rm -i --network host -v "$PWD:/scripts" -w /scripts grafana/k6:latest \
  run k6/absensi_peak_checkin.js
```

#### Mac/Windows (API jalan di host yang sama)
```bash
cd load-testing
BASE_URL="http://host.docker.internal:8000" JWT_SECRET="CHANGE_ME" \
  docker run --rm -i -v "$PWD:/scripts" -w /scripts grafana/k6:latest \
  run k6/absensi_peak_checkin.js
```

### Opsi B — k6 lokal
```bash
cd load-testing
BASE_URL="http://localhost:8000" JWT_SECRET="CHANGE_ME" k6 run k6/absensi_peak_checkin.js
```

## Skenario yang tersedia

### 1) Peak / Burst - Check-in serentak 36 user
```bash
cd load-testing
BASE_URL="http://localhost:8000" JWT_SECRET="CHANGE_ME" k6 run k6/absensi_peak_checkin.js
```

### 2) Peak / Burst - Check-out serentak 36 user
Skenario ini melakukan **setup check-in** dulu (bukan bagian load), lalu melakukan **checkout burst** 36 user.
```bash
cd load-testing
BASE_URL="http://localhost:8000" JWT_SECRET="CHANGE_ME" CHECKIN_POLL_TIMEOUT_SEC=60 k6 run k6/absensi_peak_checkout.js
```

### 3) Soak / Endurance - 36 VUs stabil untuk durasi tertentu
```bash
cd load-testing
BASE_URL="http://localhost:8000" JWT_SECRET="CHANGE_ME" SOAK_DURATION="15m" SOAK_PACE_SEC=5 k6 run k6/absensi_soak.js
```

## Output & Evaluasi
Skrip memakai `thresholds` k6 untuk:
- error rate rendah (`http_req_failed`),
- latensi p95 dalam batas tertentu (bisa disesuaikan di file skrip).

Jika ingin export summary:
```bash
cd load-testing
k6 run --summary-export result/summary/summary.json k6/absensi_peak_checkin.js
```

Atau gunakan runner script:
```bash
cd load-testing
./run_peak_checkin.sh
```

Runner script (`run_peak_checkin.sh`, `run_peak_checkout.sh`, `run_soak.sh`, dan `k6/run_setup_enroll.sh`) akan otomatis membaca file `.env` project jika ada.
Jika lokasi file `.env` berbeda, set `ENV_FILE` saat menjalankan:

```bash
cd load-testing
ENV_FILE="/path/to/.env" ./run_peak_checkin.sh
```

## Catatan penting (realistis untuk absensi)
- **Peak burst** mencerminkan kondisi jam datang/pulang di mana semua pengguna menekan tombol presensi dalam rentang waktu yang sama.
- **Soak test** menjaga 36 pengguna aktif dalam waktu lama untuk melihat kebocoran resource, penumpukan antrean Celery, dan stabilitas DB/Redis.
