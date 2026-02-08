"""
Simplified Absensi (attendance) endpoints.

This module defines three endpoints for checking in, checking out and
    retrieving attendance status for a user.  The implementation aligns
    with the SQLAlchemy models defined in :mod:`app.db.models`.

Endpoints:

* POST /checkin  -verify the user's face, then enqueue a Celery task to record
  a check-in.  Requires ``user_id``, ``location_id``, ``lat``, ``lng`` and ``image``.
  Optionally accepts ``correlation_id`` as an idempotency key from client.
* POST /checkout -verify the user's face, then enqueue a Celery task to record
  a check-out.  Requires ``user_id``, ``lat``, ``lng`` and ``image`` plus one of
  ``absensi_id`` or ``correlation_id``.
* GET /status    -return today's attendance record for the given ``user_id``.

"""

from __future__ import annotations

from datetime import date
from flask import Blueprint, request, current_app
from sqlalchemy import func

from ...utils.responses import ok, error
from ...utils.auth_utils import token_required, get_user_id_from_auth
from ...utils.rbac_utils import require_permission
from ...services.face_service import verify_user
from ...db import get_session
from ...db.models import (
    User,
    Absensi,
    Lokasi,
)
from ...utils.timez import now_local, today_local_date

# Import Celery tasks that persist the attendance data asynchronously
from app.tasks.absensi_tasks import (
    process_checkin_task_v2,
    process_checkout_task_v2,
)

# Prefix is attached by the application factory when registering the blueprint
absensi_bp = Blueprint("absensi", __name__)


@absensi_bp.post("/checkin")
@token_required
@require_permission("absensi", "create")
def checkin() -> tuple[dict[str, object], int] | tuple[dict[str, object], int]:
    """Verify a user's face and enqueue an asynchronous check-in task.

    Expected form-data fields:

    * ``user_id`` -the UUID of the user performing check-in.
    * ``location_id`` -the UUID of the location where the user is present.
    * ``lat``/``lng`` -latitude and longitude as floats.
    * ``image`` -the uploaded photo used for face verification.
    * ``correlation_id`` -optional client-generated idempotency key.

    The endpoint validates the inputs, verifies the face using the
    synchronous :func:`~app.services.face_service.verify_user` helper and
    then schedules a Celery task to write the attendance record.  A 202
    response is returned immediately.
    """
    user_id = (request.form.get("user_id") or "").strip()
    loc_id = (request.form.get("location_id") or "").strip()
    lat = request.form.get("lat", type=float)
    lng = request.form.get("lng", type=float)
    img_file = request.files.get("image")
    captured_at = (request.form.get("captured_at") or "").strip() #(aplikasi mode offline)
    correlation_id = (request.form.get("correlation_id") or "").strip() or None
    
    if not user_id:
        return error("user_id wajib ada", 400)
    if not loc_id:
        return error("location_id wajib ada", 400)
    if lat is None or lng is None:
        return error("lat/lng wajib ada", 400)
    if img_file is None:
        return error("Field 'image' wajib ada", 400)

    # Synchronous face verification.  Any errors here will abort the request.
    try:
        verify_user(user_id, img_file)
    except FileNotFoundError as e:
        # Embedding for user not found
        return error(str(e), 404)
    except Exception as e:
        current_app.logger.error(f"Kesalahan tidak terduga saat verifikasi wajah di checkin: {e}", exc_info=True)
        return error(str(e), 500)

    # Confirm that the user and location exist.
    with get_session() as s:
        u = s.get(User, user_id)
        if u is None:
            return error("User tidak ditemukan", 404)
        loc = s.get(Lokasi, loc_id)
        if loc is None:
            return error("Lokasi tidak ditemukan", 404)
        
    # --- LOGIKA PENENTUAN WAKTU (aplikasi mode offline) ---
    # Jika ada captured_at (dari Flutter), gunakan itu sebagai waktu resmi.
    # Jika tidak ada, gunakan waktu server (fallback).
    now_iso = captured_at if captured_at else now_local().isoformat()
    
    # Sangat penting: Ambil tanggal (YYYY-MM-DD) dari timestamp kejadian
    # agar pencarian shift kerja (JadwalShiftKerja) akurat. 
    attendance_date = now_iso.split('T')[0] 

    # Compose payload for Celery task
    payload = {
        "user_id": user_id,
        "today_local": attendance_date, # Gunakan tanggal kejadian asli
        "now_local_iso": now_iso,       # Waktu presensi asli
        "location": {"id": loc_id, "lat": lat, "lng": lng},
        "correlation_id": correlation_id,
    }
    # Enqueue asynchronous processing
    process_checkin_task_v2.delay(payload)

    return ok(message="Check-in sedang diproses", user_id=user_id, correlation_id=correlation_id)


@absensi_bp.post("/checkout")
@token_required
@require_permission("absensi", "update")
def checkout() -> tuple[dict[str, object], int] | tuple[dict[str, object], int]:
    """Verify a user's face and enqueue an asynchronous check-out task.

    Expected form-data fields:

    * ``user_id`` -the UUID of the user performing check-out.
    * ``absensi_id`` -optional UUID of the attendance record to update.
    * ``correlation_id`` -optional client-generated id (same id used on check-in).
    * ``lat``/``lng`` -latitude and longitude as floats.
    * ``image`` -the uploaded photo used for face verification.

    The endpoint validates the inputs, verifies the face synchronously and
    then schedules a Celery task to update the attendance record. At least
    one of ``absensi_id`` or ``correlation_id`` must be provided.
    """
    user_id = (request.form.get("user_id") or "").strip()
    absensi_id = (request.form.get("absensi_id") or "").strip()
    correlation_id = (request.form.get("correlation_id") or "").strip() or None
    loc_id = (request.form.get("location_id") or "").strip()
    lat = request.form.get("lat", type=float)
    lng = request.form.get("lng", type=float)
    img_file = request.files.get("image")
    captured_at = (request.form.get("captured_at") or "").strip() #(aplikasi mode offline)

    if not user_id:
        return error("user_id wajib ada", 400)
    if not absensi_id and not correlation_id:
        return error("absensi_id atau correlation_id wajib ada", 400)
    if lat is None or lng is None:
        return error("lat/lng wajib ada", 400)
    if img_file is None:
        return error("Field 'image' wajib ada", 400)

    # Face verification
    try:
        verify_user(user_id, img_file)
    except FileNotFoundError as e:
        return error(str(e), 404)
    except Exception as e:
        current_app.logger.error(f"Kesalahan tidak terduga saat verifikasi wajah di checkout: {e}", exc_info=True)
        return error(str(e), 500)
    
    
    # Tentukan waktu checkout asli (aplikasi mode offline)
    now_iso = captured_at if captured_at else now_local().isoformat()

    # Compose payload and enqueue task
    payload = {
        "user_id": user_id,
        "absensi_id": absensi_id,
        "correlation_id": correlation_id,
        "now_local_iso": now_iso,
        "location": {"id": loc_id, "lat": lat, "lng": lng},
    }
    process_checkout_task_v2.delay(payload)
    return ok(message="Check-out sedang diproses", user_id=user_id)


@absensi_bp.get("/status")
@token_required
@require_permission("absensi", "read")
def status() -> tuple[dict[str, object], int] | tuple[dict[str, object], int]:
    """Return the latest attendance record for a user for today.

    Query parameter:

    * ``user_id`` -the UUID of the user whose attendance status should be fetched.

    The response contains details about check-in and check-out times, attendance
    status and face verification flags if a record exists for today.  If no
    record is found the ``item`` field will be ``null``.
    """
    user_id = (request.args.get("user_id") or "").strip()
    if not user_id:
        return error("user_id wajib ada", 400)

    today = today_local_date()
    with get_session() as s:
        # Fetch the latest Absensi record for today (if multiple, pick the most recent)
        rec = (
            s.query(Absensi)
            .filter(
                Absensi.id_user == user_id,
                func.date(Absensi.waktu_masuk) == today,
            )
            .order_by(Absensi.waktu_masuk.desc())
            .first()
        )
        if rec is None:
            return ok(item=None)

        item = {
            "id_absensi": rec.id_absensi,
            "waktu_masuk": rec.waktu_masuk.isoformat() if rec.waktu_masuk else None,
            "waktu_pulang": rec.waktu_pulang.isoformat() if getattr(rec, "waktu_pulang", None) else None,
            "status_masuk": rec.status_masuk.value if rec.status_masuk else None,
            "status_pulang": rec.status_pulang.value if getattr(rec, "status_pulang", None) else None,
            "face_verified_masuk": rec.face_verified_masuk,
            "face_verified_pulang": rec.face_verified_pulang,
        }
        return ok(item=item)
