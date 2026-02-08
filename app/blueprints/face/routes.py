from __future__ import annotations

from flask import Blueprint, request, current_app
from sqlalchemy import select

from ...utils.responses import ok, error
from ...services.face_service import verify_user, enroll_user_task, delete_user_face_data
from ...services.storage.nextcloud_storage import list_objects, signed_url
from ...db import get_session
from ...db.models import User, UserFace
from ...utils.auth_utils import token_required, get_user_id_from_auth
from ...utils.rbac_utils import require_permission

face_bp = Blueprint("face", __name__)


@face_bp.post("/enroll")
@token_required
@require_permission("wajah", "create")
def enroll():
    current_app.logger.info("Menerima permintaan baru di POST /api/face/enroll")

    token_user_id = (get_user_id_from_auth() or "").strip()
    user_id = (request.form.get("user_id") or token_user_id or "").strip()

    files = request.files.getlist("images") or []

    if not user_id:
        return error("user_id wajib ada", 400)

    if token_user_id and user_id != token_user_id:
        return error("Tidak diizinkan mendaftarkan wajah untuk user lain", 403)

    if not files:
        return error("Minimal unggah 1 file 'images'", 400)

    images_data: list[bytes] = []
    for f in files:
        data = f.read()
        if data:
            images_data.append(data)

    if not images_data:
        return error("Semua file 'images' kosong/invalid", 400)

    try:
        with get_session() as s:
            user = s.execute(select(User).where(User.id_user == user_id)).scalar_one_or_none()
            if user is None:
                return error(f"User dengan id_user '{user_id}' tidak ditemukan.", 404)

            user_name = user.name or "User"
            enroll_user_task.delay(user_id, user_name, images_data)

        return ok(message="Registrasi wajah berhasil di proses sistem", user_id=user_id, images=len(images_data))
    except Exception as e:
        current_app.logger.error(f"Kesalahan tidak terduga pada endpoint enroll: {e}", exc_info=True)
        return error(str(e), 500)


@face_bp.post("/verify")
@token_required
@require_permission("wajah", "read")
def verify():
    token_user_id = (get_user_id_from_auth() or "").strip()

    user_id = (request.form.get("user_id") or token_user_id or "").strip()
    metric = (request.form.get("metric") or "cosine").strip()

    try:
        threshold = float(request.form.get("threshold") or 0.45)
    except (TypeError, ValueError):
        return error("threshold harus berupa angka", 400)

    f = request.files.get("image")

    if not user_id:
        return error("user_id wajib ada", 400)
    if f is None:
        return error("Field 'image' wajib ada", 400)

    if token_user_id and user_id != token_user_id:
        return error("Tidak diizinkan memverifikasi wajah untuk user lain", 403)

    try:
        data = verify_user(user_id, f, metric=metric, threshold=threshold)
        return ok(**data)
    except FileNotFoundError as e:
        return error(str(e), 404)
    except Exception as e:
        current_app.logger.error(f"Kesalahan di verify: {e}", exc_info=True)
        return error(str(e), 500)


@face_bp.get("/<user_id>")
@token_required
@require_permission("wajah", "read")
def get_face_data(user_id: str):
    token_user_id = (get_user_id_from_auth() or "").strip()

    if not user_id:
        return error("user_id wajib ada", 400)

    if token_user_id and user_id != token_user_id:
        return error("Tidak diizinkan mengakses data wajah user lain", 403)

        
    prefix = f"face_detection/{user_id}"
    try:
        with get_session() as s:
            face_record = s.execute(
                select(UserFace).where(UserFace.id_user == user_id)
            ).scalar_one_or_none()
            
            # Jika di database tidak ada, maka user dianggap belum registrasi
            if face_record is None:
                return ok(
                    user_id=user_id, 
                    count=0, 
                    items=[], 
                    message="User belum melakukan registrasi wajah"
                )
                
        items = list_objects(prefix)
        files = []
        for it in items:
            name = (it.get("name") or it.get("path") or "").strip()
            if not name:
                continue
            path = f"{prefix}/{name}" if not name.startswith(prefix) else name
            url = signed_url(path)
            files.append({"name": name.split("/")[-1], "path": path, "signed_url": url})

        return ok(user_id=user_id, prefix=prefix, count=len(files), items=files)
    except Exception as e:
        if "status 404" in str(e):
            return ok(user_id=user_id, count=0, items=[], message="Folder storage tidak ditemukan")
            
        current_app.logger.error(f"Kesalahan pada get_face_data: {e}", exc_info=True)
        return error(str(e), 500)
    

@face_bp.delete("/<user_id>")
@token_required
@require_permission("wajah", "delete")
def delete_face(user_id: str):
    """
    Endpoint untuk menghapus data pendaftaran wajah user.
    Otorisasi sepenuhnya ditangani oleh sistem RBAC via database.
    """
    try:
        # Jalankan fungsi penghapusan yang mencakup DB dan Nextcloud
        delete_user_face_data(user_id)
        
        return ok(message=f"Data wajah user berhasil dihapus")
        
    except Exception as e:
        current_app.logger.error(f"Kesalahan pada delete_face: {e}", exc_info=True)
        return error(str(e), 500)
