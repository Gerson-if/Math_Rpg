"""Chat blueprint. Room is always "global" for now — the service and
model already support arbitrary room strings, so rooms/DMs can be
layered on later without a schema change."""
from flask import Blueprint, render_template, request
from flask_login import login_required, current_user

from app.services import chat_service

chat_bp = Blueprint("chat", __name__, url_prefix="/chat")


@chat_bp.route("/")
@login_required
def index():
    messages = chat_service.get_recent_messages()
    return render_template("chat/index.html", messages=messages)


@chat_bp.route("/mensagens")
@login_required
def messages():
    messages = chat_service.get_recent_messages()
    return render_template("chat/_messages.html", messages=messages)


@chat_bp.route("/enviar", methods=["POST"])
@login_required
def send():
    content = request.form.get("content", "")
    error = None
    try:
        chat_service.send_message(current_user.id, content)
    except chat_service.ChatError as exc:
        error = str(exc)

    messages = chat_service.get_recent_messages()
    return render_template("chat/_messages.html", messages=messages, error=error)


@chat_bp.route("/denunciar/<int:message_id>", methods=["POST"])
@login_required
def report(message_id):
    error = None
    try:
        chat_service.report_message(message_id, current_user.id)
    except chat_service.ChatError as exc:
        error = str(exc)

    messages = chat_service.get_recent_messages()
    return render_template("chat/_messages.html", messages=messages, error=error)
