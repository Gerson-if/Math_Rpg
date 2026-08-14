from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from app.extensions import db, limiter
from app.models import User, Profile, PlayerStats, Level, Rank
from app.auth.forms import RegisterForm, LoginForm

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("users.dashboard"))

    form = RegisterForm()
    if form.validate_on_submit():
        existing = User.query.filter(
            (User.email == form.email.data) | (User.username == form.username.data)
        ).first()
        if existing:
            flash("Email ou nome de usuário já cadastrado.", "error")
            return render_template("auth/register.html", form=form)

        user = User(email=form.email.data, username=form.username.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()  # get user.id before creating dependents

        # Every player starts already placed on the rank ladder (level 1,
        # lowest rank) instead of showing blank "-" in the ranking until
        # their first answer — that blank state read as confusing/broken.
        starting_level = Level.query.filter_by(number=1).first()
        starting_rank = Rank.query.order_by(Rank.order.asc()).first()

        db.session.add(Profile(user_id=user.id, display_name=form.username.data))
        db.session.add(PlayerStats(
            user_id=user.id,
            last_active_at=datetime.utcnow(),
            level_id=starting_level.id if starting_level else None,
            rank_id=starting_rank.id if starting_rank else None,
        ))
        db.session.commit()

        login_user(user)
        return redirect(url_for("users.dashboard"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("users.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            return redirect(request.args.get("next") or url_for("users.dashboard"))
        flash("Email ou senha inválidos.", "error")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
