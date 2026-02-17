"""
Celery tasks for processing attendance (absensi) records.

These tasks implement asynchronous persistence of check-in and check-out
operations using the SQLAlchemy models defined in :mod:`app.db.models`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict
from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.extensions import celery
from app.db import get_session
from app.db.models import (
    Absensi,
    JadwalShiftKerja,
    PolaJamKerja,
    StatusAbsensi,
)

logger = logging.getLogger(__name__)
logger.info("[absensi.tasks] loaded from %s", __file__)


@celery.task(name="absensi.healthcheck", bind=True)
def healthcheck(self) -> Dict[str, Any]:
    """Simple health check task that reports the worker host name."""
    host = getattr(getattr(self, "request", None), "hostname", "unknown")
    logger.info("[absensi.healthcheck] OK from %s", host)
    return {"status": "ok", "host": host}


@celery.task(name="absensi.process_checkin_task_v2", bind=True)
def process_checkin_task_v2(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist a check-in event for a user.

    The ``payload`` dictionary must contain at least the following keys:

    * ``user_id`` -string identifier of the user.
    * ``today_local`` -ISO date string representing the current local date.
    * ``now_local_iso`` -ISO datetime string representing the current local time.
    * ``location`` -a dict with keys ``id``, ``lat``, ``lng``.
    * ``correlation_id`` -optional client idempotency key (recommended).

    The task will look up the user's shift for the current date (if any),
    compare the scheduled start time with the provided timestamp to
    determine whether the user is late or on time, and then create a
    corresponding :class:`Absensi` record.
    """
    logger.info("[process_checkin_task_v2] start payload=%s", payload)
    user_id = payload.get("user_id")
    today = date.fromisoformat(payload["today_local"])
    now_dt = datetime.fromisoformat(payload["now_local_iso"]).replace(tzinfo=None)
    location = payload.get("location", {})
    correlation_id = (payload.get("correlation_id") or "").strip() or None

    # Ambil status verifikasi wajah; default True untuk menjaga kompatibilitas lama.
    face_verified = payload.get("face_verified", True)

    with get_session() as s:
        try:
            # Idempotency: same correlation_id means same logical check-in.
            if correlation_id:
                existing = (
                    s.query(Absensi)
                    .filter(Absensi.correlation_id == correlation_id)
                    .first()
                )
                if existing:
                    if existing.id_user != user_id:
                        logger.warning(
                            "[process_checkin_task_v2] correlation_id conflict correlation_id=%s existing_user=%s request_user=%s",
                            correlation_id,
                            existing.id_user,
                            user_id,
                        )
                        return {
                            "status": "error",
                            "message": f"correlation_id {correlation_id} sudah dipakai user lain.",
                        }

                    logger.info(
                        "[process_checkin_task_v2] idempotent replay for user_id=%s correlation_id=%s absensi_id=%s",
                        user_id,
                        correlation_id,
                        existing.id_absensi,
                    )
                    return {
                        "status": "ok",
                        "message": "Check-in sudah pernah disimpan",
                        "absensi_id": existing.id_absensi,
                        "idempotent": True,
                    }

            # Look up the user's shift schedule for today (if any)
            jadwal = (
                s.query(JadwalShiftKerja)
                .join(PolaJamKerja)
                .filter(
                    JadwalShiftKerja.id_user == user_id,
                    func.date(JadwalShiftKerja.tanggal) == today,
                )
                .first()
            )

            # Determine attendance status (on time vs late)
            status_kehadiran = StatusAbsensi.TEPAT
            if jadwal and jadwal.pola_jam_kerja and jadwal.pola_jam_kerja.jam_mulai_kerja:
                scheduled_start = jadwal.pola_jam_kerja.jam_mulai_kerja
                actual_time = now_dt.time()
                if actual_time > scheduled_start:
                    status_kehadiran = StatusAbsensi.TERLAMBAT

            # Create Absensi record
            rec = Absensi(
                id_user=user_id,
                id_jadwal_shift=jadwal.id_jadwal_shift if jadwal else None,
                correlation_id=correlation_id,
                id_lokasi_datang=location.get("id"),
                waktu_masuk=now_dt,
                status_masuk=status_kehadiran,
                in_latitude=location.get("lat"),
                in_longitude=location.get("lng"),
                face_verified_masuk=face_verified,
                face_verified_pulang=False,
            )
            s.add(rec)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                # Race-safe idempotency for concurrent retries with same correlation_id.
                if correlation_id:
                    existing = (
                        s.query(Absensi)
                        .filter(Absensi.correlation_id == correlation_id)
                        .first()
                    )
                    if existing and existing.id_user == user_id:
                        logger.info(
                            "[process_checkin_task_v2] idempotent race replay for user_id=%s correlation_id=%s absensi_id=%s",
                            user_id,
                            correlation_id,
                            existing.id_absensi,
                        )
                        return {
                            "status": "ok",
                            "message": "Check-in sudah pernah disimpan",
                            "absensi_id": existing.id_absensi,
                            "idempotent": True,
                        }
                raise

            absensi_id = rec.id_absensi
            logger.info(f"[process_checkin_task_v2] SUCCESS for user_id={user_id}, absensi_id={absensi_id}")
            return {
                "status": "ok",
                "message": "Check-in berhasil disimpan",
                "absensi_id": absensi_id,
            }
        except Exception as e:
            s.rollback()
            logger.exception("[process_checkin_task_v2] error: %s", e)
            return {"status": "error", "message": str(e)}


@celery.task(name="absensi.process_checkout_task_v2", bind=True)
def process_checkout_task_v2(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist a check-out event for a user.

    The ``payload`` dictionary must contain:

    * ``user_id`` -string identifier of the user.
    * ``absensi_id`` -optional identifier of the existing attendance record.
    * ``correlation_id`` -optional client id used to locate the check-in record.
    * ``now_local_iso`` -ISO datetime string representing the current local time.
    * ``location`` -a dict with keys ``id``, ``lat``, ``lng``.

    The task will update the corresponding :class:`Absensi` record with
    the check-out timestamp and location. It first tries ``absensi_id`` and
    then falls back to ``correlation_id``. If check-out has already been set,
    the operation is treated as idempotent and no update is applied.
    """
    logger.info("[process_checkout_task_v2] start payload=%s", payload)
    # Ambil status verifikasi wajah; default True untuk kompatibilitas lama.
    face_verified = payload.get("face_verified", True)
    user_id = payload.get("user_id")
    absensi_id = (payload.get("absensi_id") or "").strip() or None
    correlation_id = (payload.get("correlation_id") or "").strip() or None
    now_dt = datetime.fromisoformat(payload["now_local_iso"]).replace(tzinfo=None)
    location = payload.get("location", {})

    with get_session() as s:
        try:
            # Retrieve existing attendance record
            rec = s.get(Absensi, absensi_id) if absensi_id else None
            if not rec and correlation_id:
                rec = (
                    s.query(Absensi)
                    .filter(
                        Absensi.correlation_id == correlation_id,
                        Absensi.id_user == user_id,
                    )
                    .first()
                )

            if not rec:
                logger.error(
                    "[process_checkout_task_v2] Absensi not found for checkout absensi_id=%s correlation_id=%s user_id=%s",
                    absensi_id,
                    correlation_id,
                    user_id,
                )
                return {
                    "status": "error",
                    "message": f"Absensi tidak ditemukan untuk absensi_id={absensi_id} atau correlation_id={correlation_id}.",
                }
            if rec.id_user != user_id:
                logger.warning(
                    "[process_checkout_task_v2] user mismatch for absensi_id=%s expected_user=%s got_user=%s",
                    rec.id_absensi,
                    rec.id_user,
                    user_id,
                )
                return {
                    "status": "error",
                    "message": "Absensi tidak ditemukan untuk user tersebut.",
                }

            # Idempotency: repeated checkout should be a no-op.
            if rec.waktu_pulang is not None:
                logger.info(
                    "[process_checkout_task_v2] idempotent replay for user_id=%s absensi_id=%s",
                    user_id,
                    rec.id_absensi,
                )
                return {
                    "status": "ok",
                    "message": "Check-out sudah pernah disimpan",
                    "absensi_id": rec.id_absensi,
                    "idempotent": True,
                }

            # Update checkout data
            rec.waktu_pulang = now_dt
            rec.id_lokasi_pulang = location.get("id")
            rec.out_latitude = location.get("lat")
            rec.out_longitude = location.get("lng")
            # Gunakan status verifikasi wajah yang dikirim dari endpoint.
            rec.face_verified_pulang = face_verified
            # Default status for checkout is on time
            rec.status_pulang = StatusAbsensi.TEPAT

            s.commit()
            logger.info(f"[process_checkout_task_v2] SUCCESS for user_id={user_id}, absensi_id={rec.id_absensi}")
            return {
                "status": "ok",
                "message": "Check-out berhasil disimpan",
                "absensi_id": rec.id_absensi,
            }
        except Exception as e:
            s.rollback()
            logger.exception("[process_checkout_task_v2] error: %s", e)
            return {"status": "error", "message": str(e)}
