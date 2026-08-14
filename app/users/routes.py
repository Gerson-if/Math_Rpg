from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Attempt, Level, Mastery, Subject, Topic, User, UserAchievement
from app.services import classes as classes_service, guardians, mentor_tips
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

    stats = current_user.stats
    next_level = None
    level_progress_pct = 100
    if stats and stats.level:
        next_level = (
            Level.query.filter(Level.xp_required > stats.xp)
            .order_by(Level.xp_required.asc())
            .first()
        )
        if next_level:
            span = next_level.xp_required - stats.level.xp_required
            done = stats.xp - stats.level.xp_required
            level_progress_pct = max(0, min(100, round(done / span * 100))) if span > 0 else 100

    review_count = Mastery.query.filter_by(user_id=current_user.id, needs_review=True).count()

    # "Heróis do Reino" gallery: same discovered/locked check as the
    # Crônicas page, previewed here so the dashboard teases the story
    # instead of duplicating that page's content wholesale.
    subjects = Subject.query.filter_by(is_active=True).order_by(Subject.order).all()
    discovered_subject_ids = {
        row[0]
        for row in (
            db.session.query(Topic.subject_id)
            .join(Attempt, Attempt.topic_id == Topic.id)
            .filter(Attempt.user_id == current_user.id)
            .distinct()
            .all()
        )
    }
    hero_gallery = [
        (subject, guardians.for_subject(subject.slug), subject.id in discovered_subject_ids)
        for subject in subjects
    ]

    tips = mentor_tips.random_tips(6)
    return render_template(
        "users/dashboard.html", user=current_user, can_choose_class=can_choose,
        next_level=next_level, level_progress_pct=level_progress_pct,
        review_count=review_count, mentor_tip=tips[0], mentor_tips_cycle=tips,
        hero_gallery=hero_gallery,
    )


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
    class_lore_line = classes_service.CLASS_LORE.get(class_key) if class_key else None
    return render_template(
        "users/profile.html", user=current_user,
        class_info=class_info, ability=ability, can_choose_class=can_choose,
        class_lore_line=class_lore_line,
    )


@users_bp.route("/jogador/<username>")
@login_required
def public_profile(username):
    """Read-only view of any player's profile — reachable from chat, the
    Salão dos Heróis leaderboard, etc. Your own /profile stays the
    editable version; this is what everyone else sees of you."""
    user = User.query.filter_by(username=username).first_or_404()
    if user.id == current_user.id:
        return redirect(url_for("users.profile"))

    profile = user.profile
    class_key = profile.character_class if profile else None
    class_info = classes_service.CLASSES.get(class_key) if class_key else None
    ability = None
    if class_info and profile.class_tier_claimed >= 0:
        ability = classes_service.ability_for(class_key, profile.class_tier_claimed)
    class_lore_line = classes_service.CLASS_LORE.get(class_key) if class_key else None

    featured = (
        UserAchievement.query.filter_by(user_id=user.id, is_featured=True)
        .order_by(UserAchievement.unlocked_at.asc())
        .all()
    )
    return render_template(
        "users/public_profile.html", user=user,
        class_info=class_info, ability=ability, class_lore_line=class_lore_line,
        featured_achievements=[ua.achievement for ua in featured],
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
        class_lore=classes_service.CLASS_LORE,
        is_reclass=tier_claimed >= 0,
    )
