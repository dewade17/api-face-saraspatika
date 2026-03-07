from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from app.db.models import Absensi, StatusAbsensi


_IDEMPOTENT_CHECKOUT_MESSAGE = "Absensi pulang kamu sudah tercatat sebelumnya."


def _build_idempotent_checkout_response(
    absensi_id: str,
    message: str = _IDEMPOTENT_CHECKOUT_MESSAGE,
) -> Dict[str, Any]:
    return {
        "status": "ok",
        "message": message,
        "absensi_id": absensi_id,
        "idempotent": True,
    }


def parse_checkout_payload(payload: Dict[str, Any]) -> tuple[Dict[str, Any] | None, Dict[str, Any] | None]:
    user_id = (payload.get("user_id") or "").strip()
    if not user_id:
        return None, {
            "status": "error",
            "message": "ID pengguna belum terbaca. Silakan login ulang lalu coba lagi.",
        }

    absensi_id = (payload.get("absensi_id") or "").strip() or None
    correlation_id = (payload.get("correlation_id") or "").strip() or None
    now_iso = payload.get("now_local_iso")
    if not now_iso:
        return None, {
            "status": "error",
            "message": "Waktu absensi pulang belum terbaca. Silakan coba lagi.",
        }

    try:
        now_dt = datetime.fromisoformat(now_iso).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None, {
            "status": "error",
            "message": "Waktu absensi pulang tidak dikenali. Silakan ulangi proses absensi pulang.",
        }

    location = payload.get("location", {})
    face_verified = payload.get("face_verified", True)

    return {
        "user_id": user_id,
        "absensi_id": absensi_id,
        "correlation_id": correlation_id,
        "now_dt": now_dt,
        "location": location,
        "face_verified": face_verified,
    }, None


def find_checkout_record(
    session,
    user_id: str,
    absensi_id: str | None,
    correlation_id: str | None,
) -> Absensi | None:
    rec = session.get(Absensi, absensi_id) if absensi_id else None
    if not rec and correlation_id:
        rec = (
            session.query(Absensi)
            .filter(
                Absensi.correlation_id == correlation_id,
                Absensi.id_user == user_id,
            )
            .first()
        )
    return rec


def validate_checkout_record(rec: Absensi | None, user_id: str) -> tuple[str | None, Dict[str, Any] | None]:
    if not rec:
        return "not_found", {
            "status": "error",
            "message": "Data absensi masuk tidak ditemukan. Pastikan kamu sudah check-in sebelum melakukan absensi pulang.",
        }

    if rec.id_user != user_id:
        return "user_mismatch", {
            "status": "error",
            "message": "Data absensi pulang ini tidak cocok dengan akun kamu.",
        }

    if rec.waktu_pulang is not None:
        return "idempotent", _build_idempotent_checkout_response(rec.id_absensi)

    return None, None


def apply_checkout_update(
    rec: Absensi,
    now_dt: datetime,
    location: Dict[str, Any],
    face_verified: bool,
) -> None:
    rec.waktu_pulang = now_dt
    rec.id_lokasi_pulang = location.get("id")
    rec.out_latitude = location.get("lat")
    rec.out_longitude = location.get("lng")
    rec.face_verified_pulang = face_verified
    rec.status_pulang = StatusAbsensi.TEPAT
