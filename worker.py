import time
import uuid
from io import BytesIO

import numpy as np
from sqlalchemy import select

from logger_config import log
from app.db import get_session
from app.db.models import User, UserFace
from app.services.storage.nextcloud_storage import upload_bytes


def proses_pendaftaran_wajah_background(user_id: str, user_name: str, images_data: list[bytes]) -> None:
    log.info(f"PROSES DIMULAI untuk user_id: {user_id}")

    if not user_id:
        log.error("user_id kosong")
        return
    if not images_data:
        log.error("images_data kosong")
        return

    try:
        prefix = f"face_detection/{user_id}"
        baseline_paths: list[str] = []

        for img_bytes in images_data:
            if not img_bytes:
                continue
            baseline_path = f"{prefix}/baseline/{uuid.uuid4()}.jpg"
            upload_bytes(baseline_path, img_bytes, "image/jpeg")
            baseline_paths.append(baseline_path)

        if not baseline_paths:
            log.error("Semua image bytes kosong/invalid")
            return

        time.sleep(3)
        embedding = np.random.rand(512).astype(np.float32)

        buffer = BytesIO()
        np.save(buffer, embedding)
        embedding_bytes = buffer.getvalue()

        embedding_path = f"{prefix}/embedding.npy"
        upload_bytes(embedding_path, embedding_bytes, "application/octet-stream")

        foto_referensi_path = baseline_paths[0]

        with get_session() as s:
            user = s.execute(select(User).where(User.id_user == user_id)).scalar_one_or_none()
            if user is None:
                log.error(f"User tidak ditemukan: {user_id}")
                return

            existing = s.execute(select(UserFace).where(UserFace.id_user == user_id)).scalar_one_or_none()
            if existing is None:
                s.add(
                    UserFace(
                        id_user=user_id,
                        embedding_path=embedding_path,
                        foto_referensi=foto_referensi_path,
                    )
                )
            else:
                existing.embedding_path = embedding_path
                existing.foto_referensi = foto_referensi_path

        log.info(f"PROSES SELESAI untuk user_id: {user_id}")
    except Exception as e:
        log.error(f"GAGAL - Terjadi error pada proses untuk user_id {user_id}")
        log.exception(e)
