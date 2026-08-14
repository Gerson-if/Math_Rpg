from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.services import classes as classes_service
from app.users.forms import ProfileForm, ClassForm

users_bp = Blueprint("users", __name__, url_prefix="/")


def _level_number(user) -> int:
    if user.stats and user.stats.level:
        return user.stats.level.number
    return 1


@users_bp.route("/dashboard")
@login_required
def dashboard():
    profile = current_user.profile
    can_choose = classes_service.can_choose_class(
        _level_number(current_user), profile.class_tier_claimed if profile else -1
    )
    return render_template("users/dashboard.html", user=current_user, can_choose_class=can_choose)


@users_bp.route("/profile")
@login_required
def profile():
    profile = current_user.profile
    class_key = profile.character_class if profile else None
    class_info = classes_service.CLASSES.get(class_key) if class_key else None
    ability = None
    if class_info and profile.class_tier_claimed >= 0:
        ability = classes_service.ability_for(class_key, profile.class_tier_claimed)
    can_choose = classes_service.can_choose_class(
        _level_number(current_user), profile.class_tier_claimed if profile else -1
    )
    return render_template(
        "users/profile.html", user=current_user,
        class_info=class_info, ability=ability, can_choose_class=can_choose,
    )


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


@users_bp.route("/profile/classe", methods=["GET", "POST"])
@login_required
def choose_class():
    profile = current_user.profile
    level_number = _level_number(current_user)
    tier_claimed = profile.class_tier_claimed
    if not classes_service.can_choose_class(level_number, tier_claimed):
        flash("Sua classe atual ainda não pode ser trocada — alcance o próximo nível de habilidade.", "warning")
        return redirect(url_for("users.profile"))

    target_tier = classes_service.current_tier(level_number)
    form = ClassForm(character_class=profile.character_class or "")
    if form.validate_on_submit():
        profile.character_class = form.character_class.data
        profile.class_tier_claimed = target_tier
        db.session.commit()
        ability = classes_service.ability_for(profile.character_class, target_tier)
        flash(f"Classe definida! Nova habilidade: {ability}.", "info")
        return redirect(url_for("users.profile"))

    return render_template(
        "users/choose_class.html", form=form,
        classes=classes_service.CLASSES, target_tier=target_tier,
        tier_label=classes_service.ABILITY_TIERS[target_tier]["label"],
        abilities=classes_service.CLASS_ABILITIES,
        is_reclass=tier_claimed >= 0,
    )
