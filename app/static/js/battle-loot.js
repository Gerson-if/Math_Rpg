/* Loot toasts — the item itself is always already persisted server-side
   (see loot_service.py) by the time this fires; this module only ever
   renders what the server already decided, never invents a drop. */
const BattleLoot = (() => {
  const RARITY_LABEL = { comum: "Comum", magico: "Mágico", raro: "Raro", lendario: "Lendário" };
  const RARITY_COLOR = { comum: "#cbd5e1", magico: "#60a5fa", raro: "#c084fc", lendario: "#fbbf24" };
  const PASSIVE_LABEL = {
    dano: (v) => `+${Math.round(v * 100)}% Dano`,
    critico: (v) => `+${Math.round(v * 100)}% Crítico`,
    furia: (v) => `+${Math.round(v)} Fúria/acerto`,
    combo: (v) => `+${Math.round(v * 100)}% por Combo`,
    vida: (v) => `+${Math.round(v)} Vida Máx.`,
    vampirismo: (v) => `+${Math.round(v * 100)}% Vampirismo`,
  };

  function toast(containerId, item) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const color = RARITY_COLOR[item.rarity] || "#cbd5e1";
    const label = RARITY_LABEL[item.rarity] || item.rarity;
    const passiveText = (PASSIVE_LABEL[item.passive_type] || (() => ""))(item.passive_value);

    // icon_key is a real image path ("images/icons/items/...") for the
    // curated Raven Fantasy Icons item set, or a bare FontAwesome class
    // for anything without curated art yet — same dual-mode convention as
    // the server-side ui.item_icon macro (see _macros.html), duplicated
    // here only because this toast is built client-side from data
    // attributes rather than rendered by Jinja.
    const iconHtml = item.icon_key && item.icon_key.indexOf("images/") === 0
      ? `<img src="/static/${item.icon_key}" alt="" class="loot-icon-img">`
      : `<i class="fa-solid ${item.icon_key} loot-icon"></i>`;

    const el = document.createElement("div");
    el.className = "loot-toast";
    el.style.setProperty("--rc", color);
    el.innerHTML =
      iconHtml +
      '<div class="loot-info">' +
      `<span class="loot-name">${item.name}</span>` +
      `<span class="loot-rarity">${label} · ${passiveText}</span>` +
      "</div>";
    container.appendChild(el);
    if (window.BattleAudio) window.BattleAudio.sfx.loot(item.rarity);
    setTimeout(() => el.remove(), 3200);
  }

  return { toast };
})();
