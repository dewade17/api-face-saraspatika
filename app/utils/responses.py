from flask import jsonify

def ok(**data):
    payload = {"ok": True}
    payload.update(data)
    return jsonify(payload)

def error(message: str, status: int = 400, **data):
    payload = {"ok": False, "error": message}
    if data:
        payload.update(data)
    return jsonify(payload), status
