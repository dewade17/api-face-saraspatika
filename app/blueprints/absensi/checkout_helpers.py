from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import Request

from ...services.face_service import verify_user
from app.tasks.absensi_tasks import process_checkout_task_v2


@dataclass(frozen=True)
class CheckoutRequestData:
    user_id: str
    absensi_id: str
    correlation_id: str | None
    loc_id: str
    lat: float
    lng: float
    img_file: object
    captured_at: str


def parse_checkout_request(req: Request) -> CheckoutRequestData:
    user_id = (req.form.get("user_id") or "").strip()
    absensi_id = (req.form.get("absensi_id") or "").strip()
    correlation_id = (req.form.get("correlation_id") or "").strip() or None
    loc_id = (req.form.get("location_id") or "").strip()
    lat = req.form.get("lat", type=float)
    lng = req.form.get("lng", type=float)
    img_file = req.files.get("image")
    captured_at = (req.form.get("captured_at") or "").strip()

    if not user_id:
        raise ValueError("user_id wajib ada")
    if not absensi_id and not correlation_id:
        raise ValueError("absensi_id atau correlation_id wajib ada")
    if lat is None or lng is None:
        raise ValueError("lat/lng wajib ada")
    if img_file is None:
        raise ValueError("Field 'image' wajib ada")

    return CheckoutRequestData(
        user_id=user_id,
        absensi_id=absensi_id,
        correlation_id=correlation_id,
        loc_id=loc_id,
        lat=lat,
        lng=lng,
        img_file=img_file,
        captured_at=captured_at,
    )


def verify_checkout_face(user_id: str, img_file: object) -> bool:
    verification = verify_user(user_id, img_file)
    return bool(verification.get("match", False))


def build_checkout_payload(
    user_id: str,
    absensi_id: str,
    correlation_id: str | None,
    now_iso: str,
    loc_id: str,
    lat: float,
    lng: float,
    face_verified: bool,
) -> dict[str, object]:
    return {
        "user_id": user_id,
        "absensi_id": absensi_id,
        "correlation_id": correlation_id,
        "now_local_iso": now_iso,
        "location": {"id": loc_id, "lat": lat, "lng": lng},
        "face_verified": face_verified,
    }


def enqueue_checkout(payload: dict[str, Any]) -> None:
    process_checkout_task_v2.delay(payload)
