"""Internal JSON API surface used by HTMX/Alpine.js on the frontend."""
from flask import Blueprint, jsonify

api_bp = Blueprint("api", __name__)


@api_bp.route("/ping")
def ping():
    return jsonify({"pong": True})
