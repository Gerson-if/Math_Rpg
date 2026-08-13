from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.users.forms import ProfileForm

users_bp = Blueprint("users", __name__, url_prefix="/")


@users_bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("users/dashboard.html", user=current_user)


@users_bp.route("/profile")
@login_required
def profile():
    return render_template("users/profile.html", user=current_user)


@users_bp.route("/profile/editar", methods=["GET", "POST"])
@login_required
def edit_profile():
    profile = current_user.profile
    form = ProfileForm(obj=profile)
    if form.validate_on_submit():
        profile.display_name = form.display_name.data
        profile.avatar_key = form.avatar_key.data
        profile.bio = form.bio.data
        db.session.commit()
        flash("Perfil atualizado.", "info")
        return redirect(url_for("users.profile"))
    return render_template("users/edit_profile.html", form=form)
