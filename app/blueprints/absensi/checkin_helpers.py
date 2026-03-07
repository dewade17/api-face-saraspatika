from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from flask import Request

from ...db.models import Lokasi, User
from ...services.face_service import verify_user
from ...utils.timez import now_local
from app.tasks.absensi_tasks import process_checkin_task_v2


@dataclass(frozen=True)
class CheckinRequestData:
    user_id: str
    loc_id: str
    lat: float
    lng: float
    img_file: object
    captured_at: str
    correlation_id: str | None


def parse_checkin_request(req: Request) -> CheckinRequestData:
    user_id = (req.form.get("user_id") or "").strip()
    loc_id = (req.form.get("location_id") or "").strip()
    lat = req.form.get("lat", type=float)
    lng = req.form.get("lng", type=float)
    img_file = req.files.get("image")
    captured_at = (req.form.get("captured_at") or "").strip()
    correlation_id = (req.form.get("correlation_id") or "").strip() or None

    if not all([user_id, loc_id, img_file]) or lat is None or lng is None:
        raise ValueError("checkin input tidak lengkap")

    return CheckinRequestData(
        user_id=user_id,
        loc_id=loc_id,
        lat=lat,
        lng=lng,
        img_file=img_file,
        captured_at=captured_at,
        correlation_id=correlation_id,
    )


def verify_face(user_id: str, img_file: object) -> bool:
    verification = verify_user(user_id, img_file)
    return bool(verification.get("match", False))


def get_user_and_location(session: Any, user_id: str, loc_id: str) -> tuple[User | None, Lokasi | None]:
    return session.get(User, user_id), session.get(Lokasi, loc_id)


def parse_captured_at_datetime(captured_at: str) -> datetime:
    if not captured_at:
        return now_local()

    # Support UTC "Z" suffix while keeping ISO output parseable by datetime.fromisoformat.
    normalized = f"{captured_at[:-1]}+00:00" if captured_at.endswith("Z") else captured_at
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as e:
        raise ValueError("captured_at tidak valid") from e


def build_payload(
    user_id: str,
    loc_id: str,
    lat: float,
    lng: float,
    captured_dt: datetime,
    attendance_date: date,
    correlation_id: str | None,
) -> dict[str, object]:
    return {
        "user_id": user_id,
        "attendance_date": attendance_date.isoformat(),
        "now_local_iso": captured_dt.isoformat(),
        "location": {"id": loc_id, "lat": lat, "lng": lng},
        "correlation_id": correlation_id,
        "face_verified": True,
    }


def enqueue_checkin(payload: dict[str, object]) -> None:
    process_checkin_task_v2.delay(payload)
