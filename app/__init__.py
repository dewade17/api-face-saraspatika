# flask_api_face/app/__init__.py

from flask import Flask
from .config import load_config
from . import extensions
from .middleware.error_handlers import register_error_handlers

# Import blueprints
from .blueprints.face.routes import face_bp
from .blueprints.absensi.routes import absensi_bp
from .blueprints.location.routes import location_bp


def create_app():
    app = Flask(__name__)
    load_config(app)

    # Initialize extensions (Celery binding).
    extensions.init_app(app)

    # Register blueprints DENGAN url_prefix yang jelas
    app.register_blueprint(face_bp, url_prefix="/api/face")
    app.register_blueprint(absensi_bp, url_prefix="/api/absensi")
    app.register_blueprint(location_bp, url_prefix="/api/location")
 
    register_error_handlers(app)

    @app.get("/health")
    def health():
        """Health check endpoint.

        Returns basic information about the application including whether
        Nextcloud storage credentials are configured.
        so this endpoint focuses solely on Nextcloud.
        """
        # Determine if Nextcloud credentials are present and valid. Use a
        # lightweight check by attempting to load credentials via the
        # storage helper. If an exception is raised the credentials are
        # considered missing or invalid.
        try:
            from .services.storage.nextcloud_storage import _get_credentials  # type: ignore
            _get_credentials()
            nc_ok = True
        except Exception:
            nc_ok = False
        return {
            "ok": True,
            "engine": app.config.get("MODEL_NAME"),
            "nextcloud": nc_ok,
            # Expose the default Nextcloud folder configured for uploads.
            "folder": app.config.get("NEXTCLOUD_DEFAULT_FOLDER"),
        }

    return app
