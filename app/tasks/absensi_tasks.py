"""
Celery tasks for processing attendance (absensi) records.

These tasks implement asynchronous persistence of check-in and check-out
operations using the SQLAlchemy models defined in :mod:`app.db.models`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

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
from app.tasks.absensi_tasks_helper_checkin import (
    acquire_checkin_advisory_lock,
    check_checkin_idempotency_and_duplicates,
    determine_checkin_status,
    parse_checkin_payload,
    resolve_checkin_integrity_error,
)
from app.tasks.absensi_tasks_helper_checkout import (
    apply_checkout_update,
    find_checkout_record,
    parse_checkout_payload,
    validate_checkout_record,
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
    logger.info("[process_checkin_task_v2] start payload=%s", payload)

    parsed_payload, validation_error = parse_checkin_payload(payload)
    if validation_error:
        return validation_error

    user_id = parsed_payload["user_id"]
    today = parsed_payload["today"]
    now_dt = parsed_payload["now_dt"]
    location = parsed_payload["location"]
    correlation_id = parsed_payload["correlation_id"]
    face_verified = parsed_payload["face_verified"]

    with get_session() as s:
        try:
            acquire_checkin_advisory_lock(s, user_id, today)

            idempotency_response = check_checkin_idempotency_and_duplicates(
                s,
                user_id=user_id,
                attendance_date=today,
                correlation_id=correlation_id,
            )
            if idempotency_response:
                return idempotency_response

            jadwal = (
                s.query(JadwalShiftKerja)
                .join(PolaJamKerja)
                .filter(
                    JadwalShiftKerja.id_user == user_id,
                    func.date(JadwalShiftKerja.tanggal) == today,
                )
                .first()
            )

            status_kehadiran = determine_checkin_status(jadwal, now_dt)

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
                integrity_error_response = resolve_checkin_integrity_error(
                    s,
                    user_id=user_id,
                    attendance_date=today,
                    correlation_id=correlation_id,
                )
                if integrity_error_response:
                    return integrity_error_response
                raise

            return {
                "status": "ok",
                "message": "Absensi berhasil dicatat! Selamat bekerja dan semangat ya!",
                "absensi_id": rec.id_absensi,
            }

        except Exception as e:
            s.rollback()
            logger.exception("[process_checkin_task_v2] error: %s", e)
            return {
                "status": "error", 
                "message": "Aduh, sepertinya ada sedikit kendala teknis saat menyimpan absensimu. Silakan coba lagi ya!"
            }


@celery.task(name="absensi.process_checkout_task_v2", bind=True)
def process_checkout_task_v2(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("[process_checkout_task_v2] start payload=%s", payload)
    parsed_payload, validation_error = parse_checkout_payload(payload)
    if validation_error:
        return validation_error

    user_id = parsed_payload["user_id"]
    absensi_id = parsed_payload["absensi_id"]
    correlation_id = parsed_payload["correlation_id"]
    now_dt = parsed_payload["now_dt"]
    location = parsed_payload["location"]
    face_verified = parsed_payload["face_verified"]

    with get_session() as s:
        try:
            rec = find_checkout_record(
                s,
                user_id=user_id,
                absensi_id=absensi_id,
                correlation_id=correlation_id,
            )

            validation_reason, validation_response = validate_checkout_record(rec, user_id)
            if validation_reason == "idempotent":
                logger.info(
                    "[process_checkout_task_v2] idempotent replay for user_id=%s absensi_id=%s",
                    user_id,
                    rec.id_absensi,
                )
                return validation_response

            if validation_reason == "not_found":
                logger.error(
                    "[process_checkout_task_v2] Absensi not found for checkout absensi_id=%s correlation_id=%s user_id=%s",
                    absensi_id,
                    correlation_id,
                    user_id,
                )
                return validation_response

            if validation_reason == "user_mismatch":
                logger.warning(
                    "[process_checkout_task_v2] user mismatch for absensi_id=%s expected_user=%s got_user=%s",
                    rec.id_absensi,
                    rec.id_user,
                    user_id,
                )
                return validation_response

            apply_checkout_update(rec, now_dt, location, face_verified)

            s.commit()
            logger.info(f"[process_checkout_task_v2] SUCCESS for user_id={user_id}, absensi_id={rec.id_absensi}")
            return {
                "status": "ok",
                "message": "Absensi pulang berhasil dicatat. Hati-hati di jalan!",
                "absensi_id": rec.id_absensi,
            }
        except Exception as e:
            s.rollback()
            logger.exception("[process_checkout_task_v2] error: %s", e)
            return {
                "status": "error",
                "message": "Aduh, sepertinya ada sedikit kendala teknis saat menyimpan absensimu. Silakan coba lagi ya!",
            }
