# celery_worker.py
# Jalankan:
#   celery -A celery_worker:app worker --loglevel=INFO --pool=solo

import logging
from app import create_app
from app.extensions import celery

# Siapkan Flask app dari factory
flask_app = create_app()
logger = logging.getLogger(__name__)

# Panaskan face engine (kalau tersedia)
try:
    from app.extensions import init_face_engine
    with flask_app.app_context():
        # >>> PERBAIKAN: kirim flask_app sebagai argumen
        init_face_engine(flask_app)
        logger.info("[celery_worker] InsightFace engine initialized.")
except Exception as e:
    logger.warning("[celery_worker] init_face_engine gagal saat startup: %s", e)

# Entry point Celery
app = celery
