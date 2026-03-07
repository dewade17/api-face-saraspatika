from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Dict

from sqlalchemy import text

from app.db.models import Absensi, StatusAbsensi


_IDEMPOTENT_CHECKIN_MESSAGE = "Absensi kamu sudah tersimpan sebelumnya, Terimakasih!"


def _build_idempotent_checkin_response(absensi_id: str, message: str = _IDEMPOTENT_CHECKIN_MESSAGE) -> Dict[str, Any]:
    return {
        "status": "ok",
        "message": message,
        "absensi_id": absensi_id,
        "idempotent": True,
    }


def parse_checkin_payload(payload: Dict[str, Any]) -> tuple[Dict[str, Any] | None, Dict[str, Any] | None]:
    user_id = (payload.get("user_id") or "").strip()
    if not user_id:
        return None, {
            "status": "error",
            "message": "ID pengguna belum terbaca. Silakan login ulang lalu coba lagi.",
        }

    attendance_date_raw = payload.get("attendance_date") or payload.get("today_local")
    if not attendance_date_raw:
        return None, {
            "status": "error",
            "message": "Tanggal absensi belum ada. Silakan coba lagi.",
        }

    try:
        today = date.fromisoformat(attendance_date_raw)
    except (TypeError, ValueError):
        return None, {
            "status": "error",
            "message": "Format tanggal absensi tidak sesuai. Gunakan format YYYY-MM-DD.",
        }

    now_iso = payload.get("now_local_iso")
    if not now_iso:
        return None, {
            "status": "error",
            "message": "Waktu absensi belum terbaca. Silakan coba lagi.",
        }
    try:
        now_dt = datetime.fromisoformat(now_iso).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None, {
            "status": "error",
            "message": "Format waktu absensi tidak sesuai. Silakan coba lagi.",
        }

    location = payload.get("location", {})
    correlation_id = (payload.get("correlation_id") or "").strip() or None
    face_verified = payload.get("face_verified", True)

    return {
        "user_id": user_id,
        "today": today,
        "now_dt": now_dt,
        "location": location,
        "correlation_id": correlation_id,
        "face_verified": face_verified,
    }, None


def find_existing_checkin_for_day(session, user_id: str, attendance_date: date) -> Absensi | None:
    day_start = datetime.combine(attendance_date, time.min)
    day_end = day_start + timedelta(days=1)
    return (
        session.query(Absensi)
        .filter(
            Absensi.id_user == user_id,
            Absensi.waktu_masuk >= day_start,
            Absensi.waktu_masuk < day_end,
        )
        .order_by(Absensi.waktu_masuk.asc())
        .first()
    )


def acquire_checkin_advisory_lock(session, user_id: str, attendance_date: date) -> None:
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        lock_key = f"absensi-checkin:{user_id}:{attendance_date.isoformat()}"
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": lock_key},
        )


def check_checkin_idempotency_and_duplicates(
    session,
    user_id: str,
    attendance_date: date,
    correlation_id: str | None,
) -> Dict[str, Any] | None:
    if correlation_id:
        existing = session.query(Absensi).filter(Absensi.correlation_id == correlation_id).first()
        if existing:
            if existing.id_user != user_id:
                return {
                    "status": "error",
                    "message": "Maaf, data ini sudah digunakan oleh akun lain.",
                }
            return _build_idempotent_checkin_response(existing.id_absensi)

    existing_today = find_existing_checkin_for_day(session, user_id, attendance_date)
    if existing_today:
        return _build_idempotent_checkin_response(existing_today.id_absensi)

    return None


def determine_checkin_status(jadwal: Any, now_dt: datetime) -> StatusAbsensi:
    status_kehadiran = StatusAbsensi.TEPAT
    if jadwal and jadwal.pola_jam_kerja and jadwal.pola_jam_kerja.jam_mulai_kerja:
        scheduled_start = jadwal.pola_jam_kerja.jam_mulai_kerja
        actual_time = now_dt.time()
        if actual_time > scheduled_start:
            status_kehadiran = StatusAbsensi.TERLAMBAT
    return status_kehadiran


def resolve_checkin_integrity_error(
    session,
    user_id: str,
    attendance_date: date,
    correlation_id: str | None,
) -> Dict[str, Any] | None:
    if correlation_id:
        existing = session.query(Absensi).filter(Absensi.correlation_id == correlation_id).first()
        if existing and existing.id_user == user_id:
            return _build_idempotent_checkin_response(
                existing.id_absensi,
                "Data absensi sudah berhasil masuk.",
            )

    existing_today = find_existing_checkin_for_day(session, user_id, attendance_date)
    if existing_today:
        return _build_idempotent_checkin_response(existing_today.id_absensi)

    return None
