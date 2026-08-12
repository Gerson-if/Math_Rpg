from flask import Blueprint, render_template
from flask_login import login_required, current_user

users_bp = Blueprint("users", __name__, url_prefix="/")


@users_bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("users/dashboard.html", user=current_user)


@users_bp.route("/profile")
@login_required
def profile():
    return render_template("users/profile.html", user=current_user)
