from __future__ import annotations

from flask import Blueprint, request, current_app
from kombu.exceptions import OperationalError as KombuOperationalError
from sqlalchemy import func

from ...utils.responses import ok, error
from ...utils.auth_utils import token_required, get_user_id_from_auth
from ...utils.rbac_utils import require_permission
from ...db import get_session
from ...db.models import (
    Absensi,
)
from ...utils.timez import today_local_date
from .checkin_helpers import (
    build_payload,
    enqueue_checkin,
    get_user_and_location,
    parse_checkin_request,
    parse_captured_at_datetime,
    verify_face as verify_checkin_face,
)
from .checkout_helpers import (
    build_checkout_payload,
    enqueue_checkout,
    parse_checkout_request,
    verify_checkout_face,
)

# Import Celery tasks that persist the attendance data asynchronously
# Prefix is attached by the application factory when registering the blueprint
absensi_bp = Blueprint("absensi", __name__)


@absensi_bp.post("/checkin")
@token_required
@require_permission("absensi", "create")
def checkin() -> tuple[dict[str, object], int]:
    try:
        checkin_data = parse_checkin_request(request)
    except ValueError:
        return error("Wah, datanya belum lengkap nih. Pastikan foto dan lokasimu sudah terisi semua ya!", 400)

    with get_session() as s:
        u, loc = get_user_and_location(s, checkin_data.user_id, checkin_data.loc_id)
        if not u:
            return error("Maaf, akun kamu tidak ditemukan di sistem kami.", 404)
    location_exists = loc is not None

    try:
        captured_dt = parse_captured_at_datetime(checkin_data.captured_at)
    except ValueError:
        return error("Format 'captured_at' tidak valid. Gunakan ISO 8601, misalnya 2026-03-02T08:30:00+08:00.", 400)
    attendance_date = captured_dt.date()

    # 1) Verifikasi wajah: pisahkan dari proses lain agar error lebih terarah.
    try:
        face_match = verify_checkin_face(checkin_data.user_id, checkin_data.img_file)
    except FileNotFoundError:
        return error("Data foto referensi kamu belum ada. Silakan hubungi admin untuk pendaftaran wajah.", 404)
    except (RuntimeError, ValueError, TypeError) as e:
        current_app.logger.warning(
            "Verifikasi wajah check-in gagal untuk user_id=%s: %s",
            checkin_data.user_id,
            e,
        )
        return error("Foto wajah tidak valid atau wajah tidak terdeteksi. Coba ambil foto lagi dengan lebih jelas, ya!", 400)
    except Exception as e:
        current_app.logger.error("Kesalahan tak terduga saat verifikasi check-in: %s", e, exc_info=True)
        return error("Ups, sistem kami sedang mengalami sedikit kendala. Silakan coba lagi sebentar lagi ya!", 500)

    if not face_match:
        return error("Wajahmu tidak sesuai dengan data kami. Coba ambil foto lagi dengan pencahayaan yang lebih terang, ya!", 400)

    if not location_exists:
        return error("Aduh, lokasi absensi ini tidak terdaftar. Silakan pilih lokasi yang sesuai.", 404)

    payload = build_payload(
        user_id=checkin_data.user_id,
        loc_id=checkin_data.loc_id,
        lat=checkin_data.lat,
        lng=checkin_data.lng,
        captured_dt=captured_dt,
        attendance_date=attendance_date,
        correlation_id=checkin_data.correlation_id,
    )

    # 2) Enqueue Celery: tangani kegagalan broker secara eksplisit.
    try:
        enqueue_checkin(payload)
    except KombuOperationalError as e:
        current_app.logger.error("Gagal enqueue check-in ke broker Celery: %s", e, exc_info=True)
        return error("Layanan antrean absensi sedang bermasalah. Silakan coba lagi beberapa saat lagi.", 500)
    except Exception as e:
        current_app.logger.error("Kesalahan tak terduga saat enqueue check-in: %s", e, exc_info=True)
        return error("Ups, sistem kami sedang mengalami sedikit kendala. Silakan coba lagi sebentar lagi ya!", 500)

    return ok(
        message="Terima kasih! Absensi kamu sedang kami proses.",
        user_id=checkin_data.user_id,
        correlation_id=checkin_data.correlation_id,
    )


@absensi_bp.post("/checkout")
@token_required
@require_permission("absensi", "update")
def checkout() -> tuple[dict[str, object], int]:
    # 1) Parse input
    try:
        checkout_data = parse_checkout_request(request)
    except ValueError:
        return error(
            "Data absensi pulang kamu belum lengkap. Pastikan foto, lokasi, dan data absensi masuk sudah terisi ya.",
            400,
        )

    with get_session() as s:
        u, _ = get_user_and_location(s, checkout_data.user_id, checkout_data.loc_id)
        if not u:
            return error("Maaf, akun kamu tidak ditemukan di sistem kami.", 404)

    try:
        captured_dt = parse_captured_at_datetime(checkout_data.captured_at)
    except ValueError:
        return error(
            "Waktu pengambilan foto tidak terbaca. Pastikan jam di perangkat kamu benar lalu coba lagi.",
            400,
        )
    now_iso = captured_dt.isoformat()

    # Face verification
    try:
        face_match = verify_checkout_face(checkout_data.user_id, checkout_data.img_file)
    except FileNotFoundError:
        return error("Data foto referensi kamu belum ada. Silakan hubungi admin untuk pendaftaran wajah.", 404)
    except (RuntimeError, ValueError, TypeError) as e:
        current_app.logger.warning(
            "Verifikasi wajah check-out gagal untuk user_id=%s: %s",
            checkout_data.user_id,
            e,
        )
        return error("Foto wajah tidak valid atau wajah tidak terdeteksi. Coba ambil foto lagi dengan lebih jelas, ya!", 400)
    except Exception as e:
        current_app.logger.error("Kesalahan tak terduga saat verifikasi check-out: %s", e, exc_info=True)
        return error("Ups, sistem kami sedang mengalami sedikit kendala. Silakan coba lagi sebentar lagi ya!", 500)

    # Sama dengan check-in: jangan lanjutkan jika wajah tidak cocok.
    if not face_match:
        return error("Wajahmu tidak sesuai dengan data kami. Coba ambil foto lagi dengan pencahayaan yang lebih terang, ya!", 400)

    # Compose payload and enqueue task
    # Sertakan hasil verifikasi wajah untuk disimpan pada record checkout.
    payload = build_checkout_payload(
        user_id=checkout_data.user_id,
        absensi_id=checkout_data.absensi_id,
        correlation_id=checkout_data.correlation_id,
        now_iso=now_iso,
        loc_id=checkout_data.loc_id,
        lat=checkout_data.lat,
        lng=checkout_data.lng,
        face_verified=face_match,
    )

    # 2) Enqueue Celery
    try:
        enqueue_checkout(payload)
    except KombuOperationalError as e:
        current_app.logger.error("Gagal enqueue check-out ke broker Celery: %s", e, exc_info=True)
        return error("Layanan antrean absensi sedang bermasalah. Silakan coba lagi beberapa saat lagi.", 500)
    except Exception as e:
        current_app.logger.error("Kesalahan tak terduga saat enqueue check-out: %s", e, exc_info=True)
        return error("Ups, sistem kami sedang mengalami sedikit kendala. Silakan coba lagi sebentar lagi ya!", 500)

    return ok(message="Terima kasih! Absensi Pulang kamu sedang kami proses.", user_id=checkout_data.user_id)


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
