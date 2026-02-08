from flask import jsonify

def register_error_handlers(app):
    @app.errorhandler(400)
    def bad_request(e):
        return jsonify(ok=False, error="Bad Request", detail=str(e)), 400

    @app.errorhandler(401)
    def unauthorized(e):
        """Handle missing/invalid authentication credentials."""
        # Mirror the structure used by other handlers with a specific error message.
        return jsonify(ok=False, error="Unauthorized", detail=str(e)), 401

    @app.errorhandler(403)
    def forbidden(e):
        """Handle permission denials."""
        return jsonify(ok=False, error="Forbidden", detail=str(e)), 403

    @app.errorhandler(404)
    def not_found(e):
        return jsonify(ok=False, error="Not Found"), 404

    @app.errorhandler(413)
    def too_large(e):
        return jsonify(ok=False, error="Payload Too Large"), 413

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify(ok=False, error="Internal Server Error"), 500
