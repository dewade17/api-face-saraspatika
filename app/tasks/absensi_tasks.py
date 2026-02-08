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

    with get_session() as s:
        try:
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
                id_lokasi_datang=location.get("id"),
                waktu_masuk=now_dt,
                status_masuk=status_kehadiran,
                in_latitude=location.get("lat"),
                in_longitude=location.get("lng"),
                face_verified_masuk=True,
                face_verified_pulang=False,
            )
            s.add(rec)
            s.commit()

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
    * ``absensi_id`` -string identifier of the existing attendance record.
    * ``now_local_iso`` -ISO datetime string representing the current local time.
    * ``location`` -a dict with keys ``id``, ``lat``, ``lng``.

    The task will update the corresponding :class:`Absensi` record with
    the check-out timestamp and location.  If the record is not found
    an error is returned.
    """
    logger.info("[process_checkout_task_v2] start payload=%s", payload)
    user_id = payload.get("user_id")
    absensi_id = payload.get("absensi_id")
    now_dt = datetime.fromisoformat(payload["now_local_iso"]).replace(tzinfo=None)
    location = payload.get("location", {})

    with get_session() as s:
        try:
            # Retrieve existing attendance record
            rec = s.get(Absensi, absensi_id)
            if not rec:
                logger.error(f"Absensi record with id {absensi_id} not found for checkout.")
                return {
                    "status": "error",
                    "message": f"Absensi record {absensi_id} not found.",
                }

            # Update checkout data
            rec.waktu_pulang = now_dt
            rec.id_lokasi_pulang = location.get("id")
            rec.out_latitude = location.get("lat")
            rec.out_longitude = location.get("lng")
            rec.face_verified_pulang = True
            # Default status for checkout is on time
            rec.status_pulang = StatusAbsensi.TEPAT

            s.commit()
            logger.info(f"[process_checkout_task_v2] SUCCESS for user_id={user_id}, absensi_id={absensi_id}")
            return {
                "status": "ok",
                "message": "Check-out berhasil disimpan",
                "absensi_id": absensi_id,
            }
        except Exception as e:
            s.rollback()
            logger.exception("[process_checkout_task_v2] error: %s", e)
            return {"status": "error", "message": str(e)}