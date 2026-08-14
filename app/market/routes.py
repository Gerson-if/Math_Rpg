"""Mercado do Reino ("Loja") — the kingdom's rotating NPC stock plus a
peer-to-peer marketplace where players list their own loot for other
players to buy. See app/services/market_service.py for the actual rules;
this blueprint is just the thin HTTP layer over it, same split as
app/character/routes.py over loot_service."""
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app.extensions import limiter
from app.services import loot_service, market_service

market_bp = Blueprint("market", __name__, url_prefix="/mercado")


def _player_gold(user_id: int) -> int:
    from app.models import PlayerStats
    stats = PlayerStats.query.filter_by(user_id=user_id).first()
    return stats.gold if stats else 0


@market_bp.route("/")
@login_required
def index():
    listings = market_service.list_market_listings(exclude_user_id=current_user.id)
    days_left = {
        item.id: max(0, (item.listed_at + market_service.LISTING_DURATION - datetime.utcnow()).days)
        for item in listings
    }
    return render_template(
        "market/index.html",
        shop_stock=market_service.get_shop_stock(),
        listings=listings,
        days_left=days_left,
        my_listings=market_service.list_my_listings(current_user.id),
        gold=_player_gold(current_user.id),
        player_level=loot_service.player_level(current_user.id),
        min_level_by_rarity=loot_service.MIN_LEVEL_BY_RARITY,
        listing_duration_days=market_service.LISTING_DURATION.days,
    )


@market_bp.route("/comprar-da-loja/<int:offer_id>", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def comprar_da_loja(offer_id):
    try:
        item = market_service.buy_from_shop(offer_id, current_user.id)
        flash(f"Comprou {item.name} da Loja do Reino!", "info")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("market.index"))


@market_bp.route("/anunciar/<int:item_id>", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def anunciar(item_id):
    try:
        price = int(request.form.get("price", 0))
    except ValueError:
        price = 0
    try:
        item = market_service.list_for_sale(item_id, current_user.id, price)
        flash(f"{item.name} anunciado por {price} de Ouro.", "info")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(request.referrer or url_for("character.espolios"))


@market_bp.route("/cancelar-anuncio/<int:item_id>", methods=["POST"])
@login_required
def cancelar_anuncio(item_id):
    try:
        market_service.cancel_listing(item_id, current_user.id)
        flash("Anúncio cancelado — item de volta aos seus espólios.", "info")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("market.index"))


@market_bp.route("/comprar/<int:item_id>", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def comprar(item_id):
    try:
        item = market_service.buy_listing(item_id, current_user.id)
        flash(f"Comprou {item.name}!", "info")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("market.index"))
