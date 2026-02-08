# flask_api_face/app/services/face_service.py

from __future__ import annotations

import io
import time
import logging
from typing import List, Union

import numpy as np
import cv2
from werkzeug.datastructures import FileStorage

from ..extensions import get_face_engine, celery
from .storage.nextcloud_storage import upload_bytes, signed_url, download, list_objects, delete_object
from sqlalchemy import select
from datetime import datetime, timezone
from ..db import get_session
from ..db.models import UserFace


logger = logging.getLogger(__name__)


# -------------
# Util kecil
# -------------
def _now_ts() -> int:
    return int(time.time())


def _normalize(v: np.ndarray, eps: float = 1e-10) -> np.ndarray:
    n = np.linalg.norm(v) + eps
    return v / n


def _score(a: np.ndarray, b: np.ndarray, metric: str = "cosine") -> float:
    if metric == "cosine":
        return float(np.dot(a, b))
    elif metric == "l2":
        return float(-np.linalg.norm(a - b))
    else:
        raise ValueError(f"Unsupported metric: {metric}")


def _is_match(score: float, metric: str, threshold: float) -> bool:
    # cosine: lebih besar lebih mirip; l2: lebih besar (negatif kecil) berarti lebih mirip
    if metric == "cosine":
        return score >= threshold
    elif metric == "l2":
        return score >= -threshold
    else:
        return False


def decode_image(file_or_bytes: Union[FileStorage, bytes, bytearray, np.ndarray]) -> np.ndarray:
    """
    Decode a file-like object or raw bytes into an OpenCV-compatible BGR array.

    This helper accepts three input types:

    * ``FileStorage`` -typically the uploaded file object from Flask.
    * ``bytes``/``bytearray`` -raw image data already loaded into memory.
    * ``numpy.ndarray`` -if an array is passed it will be returned unmodified.

    Regardless of the source (uploaded file, raw bytes or numpy array) this
    helper returns a decoded BGR numpy array ready for use with OpenCV and
    insightface.

    Raises ``TypeError`` if an unsupported type is provided or ``ValueError``
    if OpenCV fails to decode the image.
    """
    if isinstance(file_or_bytes, np.ndarray):
        img = file_or_bytes
    elif isinstance(file_or_bytes, (bytes, bytearray)):
        img = cv2.imdecode(np.frombuffer(file_or_bytes, np.uint8), cv2.IMREAD_COLOR)
    elif isinstance(file_or_bytes, FileStorage):
        data = file_or_bytes.read()
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    else:
        raise TypeError(f"Tipe tidak didukung untuk decode_image: {type(file_or_bytes)}")

    if img is None:
        raise ValueError("Gagal decode gambar (hasil None).")
    return img


def get_embedding(img: np.ndarray) -> np.ndarray | None:
    """Ambil embedding wajah pertama yang terdeteksi. Return None jika tidak ada wajah."""
    # Pastikan engine ada; lazy init akan berjalan bila belum ada.
    engine = get_face_engine()
    faces = engine.get(img)  # insightface.FaceAnalysis
    if not faces:
        return None
    # Ambil wajah terbesar / yang pertama
    face = max(faces, key=lambda f: f.bbox[2] * f.bbox[3] if hasattr(f, "bbox") else 0)
    return face.embedding


def _user_root(user_id: str) -> str:
    user_id = (user_id or "").strip()
    if not user_id:
        raise ValueError("user_id kosong")
    return f"face_detection/{user_id}"


@celery.task(name="tasks.enroll_user_task")
def enroll_user_task(user_id: str, user_name: str, images_data: List[bytes]):
    """
    Enrol a user's face from a list of images and persist the results to
    Nextcloud.

    The enrolment process computes an embedding for each provided image,
    stores each original image as a JPEG in the user's Nextcloud folder,
    then calculates and stores the mean embedding as a NumPy array. If
    no faces are detected in any of the images the task returns an
    appropriate error message.

    :param user_id: identifier of the user to enrol
    :param user_name: not used in this implementation but kept for API compatibility
    :param images_data: list of raw image bytes to process
    :returns: a dict with the status and paths of uploaded files
    """
    logger.info(f"Memulai proses enroll wajah untuk user_id: {user_id}")

    try:
        embeddings = []
        uploaded = []

        for idx, img_bytes in enumerate(images_data, 1):
            logger.info(f"Memproses gambar #{idx} untuk user {user_id}")
            img = decode_image(img_bytes)

            emb = get_embedding(img)  # <-- akan lazy init engine bila perlu
            if emb is None:
                logger.warning(f"Wajah tidak terdeteksi pada gambar #{idx} untuk user {user_id}")
                continue

            emb = _normalize(emb.astype(np.float32))

            # Simpan baseline image
            ok, buf = cv2.imencode(".jpg", img)
            if not ok:
                logger.warning(f"Gagal encode JPEG untuk gambar #{idx}")
                continue
            ts = _now_ts()
            key = f"{_user_root(user_id)}/baseline_{ts}_{idx}.jpg"
            upload_bytes(key, buf.tobytes(), "image/jpeg")
            uploaded.append({"path": key})
            embeddings.append(emb)
            logger.info(f"Gambar #{idx} berhasil diunggah ke {key}")

        if not embeddings:
            logger.error(f"Pendaftaran wajah gagal untuk user {user_id}: Tidak ada wajah terdeteksi.")
            return {"status": "error", "message": "Tidak ada wajah yang terdeteksi di semua gambar."}

        mean_emb = _normalize(np.stack(embeddings, axis=0).mean(axis=0))
        emb_io = io.BytesIO()
        np.save(emb_io, mean_emb)
        emb_key = f"{_user_root(user_id)}/embedding.npy"
        upload_bytes(emb_key, emb_io.getvalue(), "application/octet-stream")
        logger.info(f"Embedding berhasil disimpan di {emb_key}")

        try:
            # Ambil path gambar pertama sebagai foto referensi utama
            ref_photo_path = uploaded[0]["path"] if uploaded else ""
            
            with get_session() as s:
                # 1. Cari apakah record sudah ada (Update) atau belum (Insert)
                stmt = select(UserFace).where(UserFace.id_user == user_id)
                face_record = s.execute(stmt).scalar_one_or_none()

                if face_record:
                    # Jika sudah ada, perbarui jalurnya
                    face_record.embedding_path = emb_key
                    face_record.foto_referensi = ref_photo_path
                    face_record.updated_at = datetime.now(timezone.utc)
                    logger.info(f"Database: Memperbarui data wajah untuk {user_id}")
                else:
                    # Jika belum ada, buat record baru
                    new_face = UserFace(
                        id_user=user_id,
                        embedding_path=emb_key,
                        foto_referensi=ref_photo_path,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc)
                    )
                    s.add(new_face)
                    logger.info(f"Database: Membuat record wajah baru untuk {user_id}")
                
                # Simpan perubahan
                s.commit()
        except Exception as db_err:
            # Kita bungkus dengan try-except agar jika database gagal, 
            # task tetap memberikan info bahwa file di storage sudah aman.
            logger.error(f"Gagal menyimpan metadata ke database: {db_err}")
            
        return {
            "status": "success",
            "user_id": user_id,
            "images_count": len(uploaded),
            "embedding_path": emb_key,
        }

    except Exception as e:
        # Penting: tulis stacktrace agar akar masalah jelas (mis. init engine gagal)
        logger.error(f"Error dalam enroll_user_task untuk user {user_id}: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

def verify_user(
    user_id: str,
    probe_file: Union[FileStorage, bytes, bytearray, np.ndarray],
    metric: str = "cosine",
    threshold: float = 0.45,
):
    """Verifikasi wajah terhadap embedding/baseline yang disimpan."""
    probe_img = decode_image(probe_file)
    probe_emb = get_embedding(probe_img)
    if probe_emb is None:
        raise RuntimeError("Tidak ada wajah terdeteksi di probe image.")
    probe_n = _normalize(probe_emb.astype(np.float32))

    emb_key = f"{_user_root(user_id)}/embedding.npy"

    ref = None
    try:
        emb_bytes = download(emb_key)
        ref = np.load(io.BytesIO(emb_bytes))
    except Exception:
        ref = None

    if ref is None:
        # fallback: rata-rata 3 baseline pertama
        items = list_objects(f"{_user_root(user_id)}")
        baselines = [it for it in items if it.get("name", "").startswith("baseline_")]
        if not baselines:
            raise FileNotFoundError("Embedding & baseline user belum ada di storage")
        embs = []
        for it in baselines[:3]:
            data = download(it["path"])
            img = decode_image(data)
            emb = get_embedding(img)
            if emb is not None:
                embs.append(_normalize(emb.astype(np.float32)))
        if not embs:
            raise RuntimeError("Gagal hitung embedding baseline")
        ref = np.stack(embs, axis=0).mean(axis=0)

    ref_n = _normalize(ref.astype(np.float32))
    score = _score(ref_n, probe_n, metric)
    match = _is_match(score, metric, threshold)

    return {
        "user_id": user_id,
        "metric": metric,
        "threshold": threshold,
        "score": float(score),
        "match": bool(match),
    }
    
def delete_user_face_data(user_id: str):
    """
    Menghapus record wajah di DB dan seluruh folder wajah di Nextcloud.
    """
    try:
        # 1. Hapus Folder di Nextcloud (Menghapus seluruh folder face_detection/{user_id})
        folder_path = _user_root(user_id)
        delete_object(folder_path)
        logger.info(f"Folder storage untuk user {user_id} berhasil dihapus.")

        # 2. Hapus Record di Database
        with get_session() as s:
            stmt = select(UserFace).where(UserFace.id_user == user_id)
            face_record = s.execute(stmt).scalar_one_or_none()
            
            if face_record:
                s.delete(face_record)
                s.commit()
                logger.info(f"Record database wajah untuk user {user_id} berhasil dihapus.")
            else:
                logger.warning(f"Record database untuk user {user_id} tidak ditemukan.")
                
        return True
    except Exception as e:
        logger.error(f"Gagal menghapus data wajah user {user_id}: {e}")
        raise e
