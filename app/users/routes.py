from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Attempt, Friendship, Level, Mastery, Notification, Subject, Topic, User, UserAchievement
from app.services import classes as classes_service, friends_service, guardians, loot_service, mentor_tips, progression_service
from app.users.forms import ProfileForm, ClassForm

users_bp = Blueprint("users", __name__, url_prefix="/")


def _level_number(user) -> int:
    if user.stats and user.stats.level:
        return user.stats.level.number
    return 1


def _level_progress(stats):
    """(next_level, progress_pct) for the XP bar shown on both the
    dashboard and the profile — factored out since both need the exact
    same "how far to the next level" math."""
    if not stats or not stats.level:
        return None, 100
    next_level = (
        Level.query.filter(Level.xp_required > stats.xp)
        .order_by(Level.xp_required.asc())
        .first()
    )
    if not next_level:
        return None, 100
    span = next_level.xp_required - stats.level.xp_required
    done = stats.xp - stats.level.xp_required
    pct = max(0, min(100, round(done / span * 100))) if span > 0 else 100
    return next_level, pct


@users_bp.route("/dashboard")
@login_required
def dashboard():
    profile = current_user.profile
    can_choose = classes_service.can_choose_class(profile.character_class if profile else None)

    next_level, level_progress_pct = _level_progress(current_user.stats)

    review_count = Mastery.query.filter_by(user_id=current_user.id, needs_review=True).count()
    focus_topic = progression_service.recommend_focus_topic(current_user.id)

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
        hero_gallery=hero_gallery, focus_topic=focus_topic,
    )


@users_bp.route("/notificacoes")
@login_required
def notifications():
    """General notification inbox — achievement unlocks, chat-report
    verdicts (both "your report was reviewed" and "a message of yours
    was reported"), and anything else Notification.type grows into
    later. Viewing the page marks everything currently shown as read,
    same pattern as chat_service.mark_seen for the chat badge."""
    items = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    unread_ids = [n.id for n in items if not n.is_read]
    if unread_ids:
        Notification.query.filter(Notification.id.in_(unread_ids)).update(
            {"is_read": True}, synchronize_session=False
        )
        db.session.commit()
    return render_template("users/notifications.html", notifications=items)


@users_bp.route("/notificacoes/<int:notification_id>/excluir", methods=["POST"])
@login_required
def delete_notification(notification_id):
    notification = Notification.query.filter_by(
        id=notification_id, user_id=current_user.id
    ).first_or_404()
    db.session.delete(notification)
    db.session.commit()
    return redirect(url_for("users.notifications"))


@users_bp.route("/profile")
@login_required
def profile():
    profile = current_user.profile
    class_key = profile.character_class if profile else None
    tier_claimed = profile.class_tier_claimed if profile else -1
    class_info = classes_service.display_for(class_key, tier_claimed) if class_key else None
    ability = None
    if class_info and tier_claimed >= 0:
        ability = classes_service.ability_for(class_key, tier_claimed)
    class_lore_line = classes_service.CLASS_LORE.get(class_key) if class_key else None

    featured = (
        UserAchievement.query.filter_by(user_id=current_user.id, is_featured=True)
        .order_by(UserAchievement.unlocked_at.asc())
        .all()
    )
    next_level, level_progress_pct = _level_progress(current_user.stats)

    return render_template(
        "users/profile.html", user=current_user,
        class_info=class_info, ability=ability,
        switch_class_cost=classes_service.switch_class_cost(class_key),
        class_lore_line=class_lore_line,
        featured_achievements=[ua.achievement for ua in featured],
        next_level=next_level, level_progress_pct=level_progress_pct,
        equipped=loot_service.list_equipped(current_user.id),
        gold=(current_user.stats.gold if current_user.stats else 0),
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
    tier_claimed = profile.class_tier_claimed if profile else -1
    class_info = classes_service.display_for(class_key, tier_claimed) if class_key else None
    ability = None
    if class_info and tier_claimed >= 0:
        ability = classes_service.ability_for(class_key, tier_claimed)
    class_lore_line = classes_service.CLASS_LORE.get(class_key) if class_key else None

    featured = (
        UserAchievement.query.filter_by(user_id=user.id, is_featured=True)
        .order_by(UserAchievement.unlocked_at.asc())
        .all()
    )

    friend_status = friends_service.relationship_status(current_user.id, user.id)
    incoming_friendship_id = None
    if friend_status == "pending_incoming":
        incoming = Friendship.query.filter_by(
            requester_id=user.id, addressee_id=current_user.id, status=Friendship.STATUS_PENDING,
        ).first()
        incoming_friendship_id = incoming.id if incoming else None

    return render_template(
        "users/public_profile.html", user=user,
        class_info=class_info, ability=ability, class_lore_line=class_lore_line,
        featured_achievements=[ua.achievement for ua in featured],
        friend_status=friend_status, incoming_friendship_id=incoming_friendship_id,
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
    """First pick is free. Once a class is already claimed, this same
    screen re-picking the *same* class is a no-op, and picking a
    *different* one is a paid switch (see classes_service.
    SWITCH_CLASS_GOLD_COST) — evolving within your current class no
    longer happens here at all, it's automatic as you level (see
    progression_service._update_class_tier)."""
    profile = current_user.profile
    level_number = _level_number(current_user)
    current_class_key = profile.character_class
    target_tier = classes_service.current_tier(level_number)
    cost = classes_service.switch_class_cost(current_class_key)

    form = ClassForm(character_class=current_class_key or "")
    if form.validate_on_submit():
        chosen_key = form.character_class.data

        if chosen_key == current_class_key:
            flash("Você já está nessa classe.", "info")
            return redirect(url_for("users.profile"))

        if current_class_key:
            stats = current_user.stats
            gold = stats.gold if stats else 0
            if gold < cost:
                flash(f"Ouro insuficiente para trocar de classe — faltam {cost - gold} de ouro.", "error")
                return redirect(url_for("users.choose_class"))
            stats.gold -= cost

        profile.character_class = chosen_key
        profile.class_tier_claimed = target_tier
        db.session.commit()

        display = classes_service.display_for(chosen_key, target_tier)
        name = display["name"] if display else chosen_key
        if current_class_key:
            flash(f"Classe trocada para {name}! (-{cost} de ouro)", "info")
        else:
            flash(f"Classe definida! Você agora é {name}.", "info")
        return redirect(url_for("users.profile"))

    return render_template(
        "users/choose_class.html", form=form,
        classes={key: classes_service.display_for(key, target_tier) for key in classes_service.CLASSES},
        target_tier=target_tier,
        tier_label=classes_service.ABILITY_TIERS[target_tier]["label"],
        abilities=classes_service.CLASS_ABILITIES,
        class_lore=classes_service.CLASS_LORE,
        is_reclass=bool(current_class_key),
        current_class_key=current_class_key,
        switch_class_cost=cost,
        player_gold=(current_user.stats.gold if current_user.stats else 0),
    )
