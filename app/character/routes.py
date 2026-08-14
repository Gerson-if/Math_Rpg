"""Equipment/loadout ("Personagem") — deliberately real, full pages rather
than the reference template's inventory modal: equipment is a persistent
collection (see app/services/loot_service.py) chosen before a battle, not
mid-fight, so it belongs with the rest of the app's real pages (Amigos,
Conquistas, ...), not layered over the arena."""
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app.services import loot_service

character_bp = Blueprint("character", __name__, url_prefix="/personagem")


@character_bp.route("/equipamentos")
@login_required
def equipamentos():
    return render_template(
        "character/equipamentos.html",
        equipped=loot_service.list_equipped(current_user.id),
        buffs=loot_service.compute_buffs(current_user.id),
    )


@character_bp.route("/espolios")
@login_required
def espolios():
    rarity = request.args.get("raridade") or None
    return render_template(
        "character/espolios.html",
        items=loot_service.list_unequipped(current_user.id, rarity=rarity),
        rarities=loot_service.RARITIES,
        selected_rarity=rarity,
    )


@character_bp.route("/equipar/<int:item_id>", methods=["POST"])
@login_required
def equipar(item_id):
    try:
        item = loot_service.equip(item_id, current_user.id)
        flash(f"Equipou {item.name}!", "info")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(request.referrer or url_for("character.espolios"))


@character_bp.route("/desequipar/<slot>", methods=["POST"])
@login_required
def desequipar(slot):
    loot_service.unequip(current_user.id, slot)
    return redirect(url_for("character.equipamentos"))
