/* Battle arena orchestrator. Combat feel (combo/crit-flourish/fury/boss
   phases) is a cosmetic layer over the REAL question/answer loop — the
   question comes from the server via HTMX, correctness and crit are
   decided server-side (see _question.html's data-correct/data-crit), and
   this module only reacts to what already happened. It never invents a
   correct/wrong/crit outcome on its own.

   Depends on BattleAudio (battle-audio.js), BattleFx (battle-fx.js) and
   BattleLoot (battle-loot.js) being loaded first. Reads its per-page
   config (topic slug, CSRF token, starting buffs) from window.BATTLE_CONFIG,
   set by an inline <script> in practice.html. */
const MathBattle = (() => {
  const CONFIG = {
    playerDmgMin: 16, playerDmgMax: 24,
    critMult: 1.8,
    comboStep: 0.075, comboCap: 8,
    furyPerHit: 14, furyPerCrit: 26,
    ultimateDamage: 55,
    bossDmgByPhase: [{ min: 10, max: 16 }, { min: 14, max: 20 }, { min: 18, max: 26 }],
    potionHeal: 40, furyScrollAmount: 40,
    potionsStart: 3, furyScrollsStart: 2,
  };
  const BASE_MAX_HP = 100;
  // Every topic in a subject used to fight the exact same boss at the
  // exact same HP — now it's a real escalation: lesser minion, then an
  // elite minion, then the guardian itself, then (once already beaten
  // once) its resurrected supreme form.
  const BOSS_HP_BY_TIER = { minion: 90, elite: 120, boss: 150, supreme: 190 };

  let cfg = { topicSlug: "", indexUrl: "/math/", buffs: {} };
  let maxHP = BASE_MAX_HP, playerHP = maxHP;
  let bossMaxHP = BOSS_HP_BY_TIER.boss, bossHP = bossMaxHP;
  let combo = 0, fury = 0, lastPhase = 1;
  let potions = CONFIG.potionsStart, furyScrolls = CONFIG.furyScrollsStart;
  let claimingVictory = false;
  let victoryTriggered = false;
  let furyWasReady = false, comboAlertedTier = 0;

  function $(id) { return document.getElementById(id); }
  function rand(min, max) { return Math.floor(Math.random() * (max - min + 1)) + min; }
  function getPhase() { const pct = (bossHP / bossMaxHP) * 100; return pct > 66 ? 1 : pct > 33 ? 2 : 3; }

  function init(config) {
    cfg = Object.assign(cfg, config);
  }

  /* ---------------- full-viewport invocation / rebirth overlays ---------------- */

  const INTRO_PHRASES = ["A Provação Começa", "As Ruínas Despertam", "O Destino Convoca o Aprendiz"];
  const REBIRTH_PHRASES = ["A Chama Ascende Novamente", "Das Cinzas, a Vontade Retorna", "Um Novo Fôlego Desafia o Destino"];

  function showInvocation() {
    const phrase = INTRO_PHRASES[rand(0, INTRO_PHRASES.length - 1)];
    const overlay = document.createElement("div");
    overlay.className = "intro-overlay";
    overlay.innerHTML =
      '<div class="intro-sigil-wrap">' +
      '<div class="intro-ring"></div>' +
      '<div class="intro-ring reverse"></div>' +
      '<div class="intro-icon"><i class="fa-solid fa-dragon"></i></div>' +
      "</div>" +
      `<div class="intro-text">${phrase}</div>`;
    document.body.appendChild(overlay);
    setTimeout(() => overlay.remove(), 2800);
  }

  function showRebirth() {
    const phrase = REBIRTH_PHRASES[rand(0, REBIRTH_PHRASES.length - 1)];
    const overlay = document.createElement("div");
    overlay.className = "rebirth-overlay";
    overlay.innerHTML =
      '<div class="rebirth-flame"><i class="fa-solid fa-fire-flame-curved"></i></div>' +
      `<div class="rebirth-text">${phrase}</div>`;
    document.body.appendChild(overlay);
    setTimeout(() => overlay.remove(), 3400);
  }

  const ADVANCE_PHRASES = ["Uma Nova Provação Surge no Horizonte", "O Caminho Segue Adiante", "Outro Enigma Aguarda em Arith"];

  /* Same ring+icon+fade language as the invocation, reused verbatim for
     "moving forward" (next challenge) so the two moments read as a pair,
     per the request to make these transitions feel like the opening one. */
  function showAdvanceOverlay() {
    const phrase = ADVANCE_PHRASES[rand(0, ADVANCE_PHRASES.length - 1)];
    const overlay = document.createElement("div");
    overlay.className = "intro-overlay";
    overlay.innerHTML =
      '<div class="intro-sigil-wrap">' +
      '<div class="intro-ring"></div>' +
      '<div class="intro-ring reverse"></div>' +
      '<div class="intro-icon"><i class="fa-solid fa-road"></i></div>' +
      "</div>" +
      `<div class="intro-text">${phrase}</div>`;
    document.body.appendChild(overlay);
    setTimeout(() => overlay.remove(), 2800);
  }

  /* One chapter ("stage") of that subject's chronicle per boss defeated —
     purely narrative flavor (see app/services/lore.py), tracked
     client-side only since it has no bearing on real progression. Loops
     back to the last chapter once the chronicle has been fully told. */
  function nextLoreSnippet() {
    const chronicle = cfg.chronicle;
    if (!chronicle || !chronicle.stages || !chronicle.stages.length) return null;
    const stages = chronicle.stages;
    const key = "mathrpg_lore_" + (cfg.subjectSlug || "geral");
    let idx = parseInt(localStorage.getItem(key) || "0", 10);
    if (isNaN(idx) || idx < 0) idx = 0;
    const snippet = stages[Math.min(idx, stages.length - 1)].trim();
    const isComplete = idx >= stages.length - 1;
    localStorage.setItem(key, String(Math.min(idx + 1, stages.length - 1)));
    return { title: chronicle.title, snippet, isComplete, stageNumber: Math.min(idx + 1, stages.length) };
  }

  /* Doesn't auto-dismiss — there's a chronicle sliver to actually read —
     it waits for the player to tap "Continuar", then fades out and hands
     control back via onContinue (which reveals the victory-screen box). */
  function showVictoryReveal(onContinue) {
    const lore = nextLoreSnippet();
    const overlay = document.createElement("div");
    overlay.className = "victory-overlay";
    let html =
      '<div class="intro-sigil-wrap">' +
      '<div class="intro-ring"></div>' +
      '<div class="intro-ring reverse"></div>' +
      '<div class="victory-icon"><i class="fa-solid fa-scroll"></i></div>' +
      "</div>" +
      '<div class="victory-title">Vitória!</div>';
    if (lore) {
      html += `<div class="victory-snippet"><strong>${escapeHtml(lore.title)} — Capítulo ${lore.stageNumber}</strong><br>${escapeHtml(lore.snippet)}${lore.isComplete ? " <em>(crônica completa — reveja em Crônicas do Reino)</em>" : ""}</div>`;
    }
    html += '<button type="button" class="victory-continue-btn"><i class="fa-solid fa-wand-magic-sparkles"></i> Continuar</button>';
    overlay.innerHTML = html;
    document.body.appendChild(overlay);

    overlay.querySelector(".victory-continue-btn").addEventListener("click", () => {
      overlay.classList.add("closing");
      setTimeout(() => {
        overlay.remove();
        if (onContinue) onContinue();
      }, 700);
    });
  }

  /* ---------------- screen flow (story -> arena -> victory/defeat) ---------------- */

  function start() {
    BattleAudio.unlock();
    showInvocation();

    setTimeout(() => {
      $("story-screen").classList.add("hidden");
      const arena = $("battle-arena");
      arena.classList.remove("hidden");
      arena.classList.add("epic-enter");
      spawnDust();
      resetCombatState();
      arena.scrollIntoView({ behavior: "smooth", block: "start" });
      focusAnswer();
    }, 1200);
  }

  function resetCombatState() {
    bossMaxHP = BOSS_HP_BY_TIER[cfg.bossTier] || BOSS_HP_BY_TIER.boss;
    playerHP = maxHP; bossHP = bossMaxHP;
    combo = 0; fury = 0; lastPhase = 1;
    furyWasReady = false; comboAlertedTier = 0;
    victoryTriggered = false;
    potions = CONFIG.potionsStart; furyScrolls = CONFIG.furyScrollsStart;
    $("arena-content").classList.remove("player-dead");
    $("boss-sprite").classList.remove("boss-dead");
    updateHpBar("player-hp", playerHP, maxHP);
    updateHpBar("boss-hp", bossHP, bossMaxHP);
    updateFuryUi();
    updateComboUi();
    updateBossPhaseUi(1);
    $("potion-count") && ($("potion-count").innerText = potions);
    $("scroll-count") && ($("scroll-count").innerText = furyScrolls);
    $("speech-bubble-container") && ($("speech-bubble-container").innerHTML = "");
    $("battle-alert-container") && ($("battle-alert-container").innerHTML = "");
    $("loot-toast-container") && ($("loot-toast-container").innerHTML = "");
  }

  function spawnDust() {
    const c = $("dust-container");
    c.innerHTML = "";
    for (let i = 0; i < 10; i++) {
      const d = document.createElement("div");
      d.className = "magic-dust";
      d.style.left = Math.random() * 100 + "%";
      const size = Math.random() * 4 + 2;
      d.style.width = size + "px";
      d.style.height = size + "px";
      d.style.animationDuration = Math.random() * 3 + 3 + "s";
      d.style.animationDelay = Math.random() * 3 + "s";
      c.appendChild(d);
    }
  }

  function focusAnswer() {
    const input = document.querySelector("#question-slot input[name='answer']");
    if (input && window.innerWidth > 768) input.focus();
  }

  /* ---------------- reacting to the real question loop ---------------- */

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : str;
    return div.innerHTML;
  }

  /* Answer/achievement/mastery-review feedback as floating speech bubbles
     near the hero — never inline blocks, so the challenge box below never
     shifts position between questions. */
  function showSpeechBubble(html, variant) {
    const container = $("speech-bubble-container");
    if (!container) return;
    const el = document.createElement("div");
    el.className = "speech-bubble" + (variant ? " bubble-" + variant : "");
    el.innerHTML = html;
    container.appendChild(el);
    setTimeout(() => el.remove(), 3400);
  }

  document.body.addEventListener("htmx:afterSwap", (evt) => {
    if (evt.target.id !== "question-slot") return;
    const d = evt.target.dataset;
    if (d.correct === "true") {
      onHit(d.crit === "true", {
        name: d.lootName, icon_key: d.lootIcon, rarity: d.lootRarity,
        passive_type: d.lootPassive, passive_value: parseFloat(d.lootValue || "0"),
      });
      let msg = `<i class="fa-solid fa-check"></i> Correto! +${escapeHtml(d.xp || "0")} XP`;
      if (d.bonusXp) msg += ` <span style="color:#c084fc">(+${escapeHtml(d.bonusXp)} dupla c/ ${escapeHtml(d.allyName)})</span>`;
      if (d.levelup === "true") msg += ` · <i class="fa-solid fa-star"></i> Nível ${escapeHtml(d.level)}!`;
      showSpeechBubble(msg, "correct");
    } else if (d.correct === "false") {
      onMiss();
      showSpeechBubble(`<i class="fa-solid fa-xmark"></i> Quase — era <strong>${escapeHtml(d.correctAnswer)}</strong>`, "wrong");
    }
    if (d.achievements) {
      d.achievements.split("||").forEach((name) => {
        showSpeechBubble(`<i class="fa-solid fa-trophy"></i> Nova conquista: <strong>${escapeHtml(name)}</strong>`, "achievement");
      });
    }
    if (d.needsReview === "true") {
      showSpeechBubble(`<i class="fa-solid fa-book-bookmark"></i> Domínio caiu — vale revisar em breve.`, "review");
    }
    if (d.masteryRecovered === "true") {
      showSpeechBubble(`<i class="fa-solid fa-arrow-trend-up"></i> Domínio recuperado!`, "recovered");
    }
    focusAnswer();
  });

  /* A question's signed token expires (30min — see question_token.py) or a
     request can otherwise fail; htmx only swaps on 2xx by default, so
     without this the old, now-dead form just sits there silently
     "frozen", accepting no input and giving no feedback. Self-heal by
     pulling a fresh question instead of leaving the player stuck. */
  document.body.addEventListener("htmx:responseError", (evt) => {
    const slot = $("question-slot");
    if (!slot || !evt.detail.elt || !slot.contains(evt.detail.elt)) return;
    showBattleAlert("⏳ Pergunta expirou — carregando uma nova...", "danger");
    if (window.htmx) htmx.ajax("GET", cfg.newQuestionUrl, { target: "#question-slot", swap: "outerHTML" });
  });

  document.body.addEventListener("htmx:sendError", (evt) => {
    const slot = $("question-slot");
    if (!slot || !evt.detail.elt || !slot.contains(evt.detail.elt)) return;
    showBattleAlert("⚠️ Falha de conexão — tente responder de novo.", "danger");
  });

  function onHit(isCrit, lootItem) {
    combo++;
    fury = Math.min(100, fury + (isCrit ? CONFIG.furyPerCrit : CONFIG.furyPerHit) + (cfg.buffs.furiaBonus || 0));
    updateFuryUi();
    updateComboUi();
    BattleAudio.sfx.cast();

    const comboMult = 1 + Math.min(combo, CONFIG.comboCap) * (CONFIG.comboStep + (cfg.buffs.comboBonus || 0));
    let dmg = rand(CONFIG.playerDmgMin, CONFIG.playerDmgMax) * comboMult * (1 + (cfg.buffs.danoPct || 0));
    if (isCrit) dmg *= CONFIG.critMult;
    dmg = Math.round(dmg);

    const hero = $("hero-avatar"), boss = $("boss-sprite");
    hero.classList.remove("hero-attack-anim"); void hero.offsetWidth; hero.classList.add("hero-attack-anim");

    BattleFx.launchProjectile(hero, boss, isCrit ? "#fbbf24" : "#a855f7", () => applyBossDamage(dmg, isCrit, lootItem), isCrit);
  }

  function applyBossDamage(dmg, isCrit, lootItem) {
    bossHP = Math.max(0, bossHP - dmg);
    const boss = $("boss-sprite");

    BattleFx.showFloatingDamage("boss-sprite", "-" + dmg, isCrit ? "#fbbf24" : "#22c55e", isCrit);
    updateHpBar("boss-hp", bossHP, bossMaxHP);

    boss.classList.remove("spell-hit"); void boss.offsetWidth; boss.classList.add("spell-hit");
    BattleFx.spawnBurst(boss, isCrit ? "#fbbf24" : "#c084fc", isCrit ? 34 : 18);
    if (isCrit) {
      BattleFx.triggerCritFlash("crit-flash", false);
      BattleFx.spawnShockwave(boss, "#fbbf24");
      const arena = $("battle-arena");
      arena.classList.remove("crit-shake"); void arena.offsetWidth; arena.classList.add("crit-shake");
      setTimeout(() => arena.classList.remove("crit-shake"), 450);
      showBattleAlert("💥 Golpe Crítico!", "crit");
    }
    BattleAudio.sfx.hit(isCrit);

    const vamp = cfg.buffs.vampirismoPct || 0;
    if (vamp > 0 && playerHP > 0) {
      const heal = Math.round(dmg * vamp);
      if (heal > 0) {
        playerHP = Math.min(maxHP, playerHP + heal);
        updateHpBar("player-hp", playerHP, maxHP);
        BattleFx.showFloatingDamage("hero-avatar", "+" + heal, "#4ade80", false);
      }
    }

    if (lootItem && lootItem.name) BattleLoot.toast("loot-toast-container", lootItem);

    checkPhaseTransition();
    if (bossHP <= 0) {
      boss.classList.add("boss-dead");
      setTimeout(victory, 800);
    }
  }

  function onMiss() {
    combo = 0;
    updateComboUi();

    const range = CONFIG.bossDmgByPhase[getPhase() - 1];
    const dmg = rand(range.min, range.max);

    const boss = $("boss-sprite"), hero = $("hero-avatar");
    BattleFx.launchProjectile(boss, hero, "#ef4444", () => applyPlayerDamage(dmg));

    const arena = $("battle-arena");
    arena.classList.remove("hit-flash"); void arena.offsetWidth; arena.classList.add("hit-flash");
    hero.classList.remove("hero-hurt-anim"); void hero.offsetWidth; hero.classList.add("hero-hurt-anim");
    const fx = $("hero-fx");
    fx.innerHTML = '<i class="fa-solid fa-bolt-lightning miss-spark"></i>';
    setTimeout(() => { fx.innerHTML = ""; }, 500);
  }

  function applyPlayerDamage(dmg) {
    playerHP = Math.max(0, playerHP - dmg);
    BattleFx.showFloatingDamage("hero-avatar", "-" + dmg, "#ef4444", false);
    updateHpBar("player-hp", playerHP, maxHP);
    BattleFx.spawnBurst($("hero-avatar"), "#ef4444", 14);
    BattleAudio.sfx.hit(false);
    if (playerHP <= 0) {
      $("arena-content").classList.add("player-dead");
      setTimeout(defeat, 800);
    }
  }

  /* ---------------- ultimate / consumables (cosmetic, client-only) ---------------- */

  function useUltimate() {
    if (fury < 100 || bossHP <= 0 || playerHP <= 0) return;
    fury = 0;
    updateFuryUi();
    BattleAudio.sfx.ultimate();
    BattleFx.triggerCritFlash("crit-flash", true);
    showBattleAlert("☄️ Fúria Arcana Suprema!", "crit");
    BattleFx.launchProjectile($("hero-avatar"), $("boss-sprite"), "#f472b6", () => applyBossDamage(CONFIG.ultimateDamage, true, null), true);
  }

  function usarPocao() {
    if (potions <= 0 || playerHP >= maxHP) return;
    potions--;
    playerHP = Math.min(maxHP, playerHP + CONFIG.potionHeal);
    updateHpBar("player-hp", playerHP, maxHP);
    $("potion-count").innerText = potions;
    BattleFx.spawnBurst($("hero-avatar"), "#60a5fa", 14);
    BattleAudio.sfx.heal();
    showBattleAlert("🧪 Poção usada! +" + CONFIG.potionHeal + " HP");
  }

  function usarPergaminhoFuria() {
    if (furyScrolls <= 0 || fury >= 100) return;
    furyScrolls--;
    fury = Math.min(100, fury + CONFIG.furyScrollAmount);
    updateFuryUi();
    $("scroll-count").innerText = furyScrolls;
    BattleFx.spawnBurst($("hero-avatar"), "#f472b6", 14);
    BattleAudio.sfx.heal();
    showBattleAlert("📜 Pergaminho usado! +" + CONFIG.furyScrollAmount + " Fúria");
  }

  /* ---------------- UI helpers ---------------- */

  function updateHpBar(id, value, max) {
    const pct = Math.max(0, (value / max) * 100);
    $(id).style.width = pct + "%";
    // Ghost bar trails behind on a slower transition so damage reads as
    // an afterimage — same trick the reference template uses.
    const ghost = document.getElementById(id + "-ghost");
    if (ghost) setTimeout(() => { ghost.style.width = pct + "%"; }, 220);
    const text = document.getElementById(id + "-text");
    if (text) text.innerText = `${Math.max(0, Math.round(value))}/${max}`;
  }

  function updateFuryUi() {
    $("fury-fill").style.width = fury + "%";
    const btn = $("ultimate-btn");
    const ready = fury >= 100;
    btn.disabled = !ready;
    btn.classList.toggle("ready", ready);
    if (ready && !furyWasReady) showBattleAlert("⚡ Fúria pronta! Use a Ultimate!", "crit");
    furyWasReady = ready;
  }

  function updateComboUi() {
    const badge = $("combo-badge");
    if (combo >= 2) {
      badge.classList.remove("hidden");
      $("combo-value").innerText = combo;
      badge.classList.toggle("tier-2", combo >= 5 && combo < 8);
      badge.classList.toggle("tier-3", combo >= 8);
    } else {
      badge.classList.add("hidden");
      badge.classList.remove("tier-2", "tier-3");
    }
    if (combo === 0) {
      comboAlertedTier = 0;
    } else if (combo >= 8 && comboAlertedTier < 3) {
      comboAlertedTier = 3;
      showBattleAlert("⚔️ Combo Máximo!");
    } else if (combo >= 5 && comboAlertedTier < 2) {
      comboAlertedTier = 2;
      showBattleAlert("🔥 Combo x5!");
    }
  }

  function updateBossPhaseUi(phase) {
    const boss = $("boss-sprite");
    boss.classList.remove("boss-phase-2", "boss-phase-3");
    if (phase === 2) boss.classList.add("boss-phase-2");
    if (phase === 3) boss.classList.add("boss-phase-3");
    const aura = $("boss-aura");
    aura.classList.toggle("aura-active", phase >= 2);
    aura.classList.toggle("aura-intense", phase === 3);
    $("boss-phase-tag").innerText = "Fase " + phase;
  }

  function checkPhaseTransition() {
    const p = getPhase();
    if (p !== lastPhase) {
      lastPhase = p;
      updateBossPhaseUi(p);
      showPhaseBanner(p);
    }
  }

  function showPhaseBanner(phase) {
    const textos = { 2: "⚡ Fase 2: O Guardião Desperta ⚡", 3: "🔥 Fase Final: Fúria Ancestral 🔥" };
    if (!textos[phase]) return;
    const banner = document.createElement("div");
    banner.className = "phase-banner";
    banner.innerText = textos[phase];
    document.body.appendChild(banner);
    setTimeout(() => banner.remove(), 2600);
  }

  /* ---------------- small floating battle alerts (combo/fury/crit) ----------------
     Purely cosmetic, never shift layout — absolutely positioned inside the
     arena, auto-dismissing, several can stack briefly. */
  function showBattleAlert(text, variant) {
    const container = $("battle-alert-container");
    if (!container) return;
    const el = document.createElement("div");
    el.className = "battle-alert" + (variant ? " alert-" + variant : "");
    el.innerText = text;
    container.appendChild(el);
    setTimeout(() => el.remove(), 2200);
  }

  /* ---------------- consumables screen (in-arena, no server round trip) ---------------- */

  function abrirConsumiveis() { $("screen-consumables").classList.remove("hidden"); }
  function fecharConsumiveis() { $("screen-consumables").classList.add("hidden"); }

  /* ---------------- victory / defeat / revive / next-challenge ---------------- */

  function victory() {
    // A hit that lands just as the boss reaches 0 HP can overlap with
    // another already-in-flight hit (combo tail, ultimate) that also
    // clamps to 0 and re-triggers this — without a guard, each call built
    // its own non-auto-dismissing overlay, stacking blocking screens.
    if (victoryTriggered) return;
    victoryTriggered = true;

    BattleAudio.sfx.victory();
    // The chapter-reveal overlay below IS the victory transition now — no
    // need for the small in-arena gate-rift portal underneath it too.
    // The victory-screen box (with loot) only appears once the player has
    // dismissed the chapter-reveal overlay themselves — no fixed timer.
    showVictoryReveal(() => $("victory-screen").classList.remove("hidden"));

    if (claimingVictory) return;
    claimingVictory = true;
    fetch(cfg.victoryUrl, {
      method: "POST",
      headers: { "X-CSRFToken": cfg.csrfToken },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((item) => {
        claimingVictory = false;
        if (item) {
          BattleLoot.toast("loot-toast-container", item);
          const label = { comum: "Comum", magico: "Mágico", raro: "Raro", lendario: "Lendário" }[item.rarity] || item.rarity;
          $("victory-loot").innerHTML = `<i class="fa-solid ${item.icon_key} mr-1"></i> Espólio: ${item.name} (${label})`;
        }
      })
      .catch(() => { claimingVictory = false; });
  }

  function defeat() {
    BattleAudio.sfx.defeat();
    $("defeat-screen").classList.remove("hidden");
  }

  function resetBars() {
    resetCombatState();
    $("portal-effect").className = "gate-rift";
  }

  function revive() {
    showRebirth();

    const portal = $("portal-effect");
    portal.className = "gate-rift gate-rift--fire";

    const wipe = $("revive-wipe");
    wipe.className = "revive-wipe revive-wipe--in";

    setTimeout(() => {
      resetBars();
      $("defeat-screen").classList.add("hidden");
      wipe.className = "revive-wipe revive-wipe--out";
      focusAnswer();
    }, 550);

    setTimeout(() => { wipe.className = "revive-wipe"; }, 1050);
  }

  function nextChallenge() {
    const ring = $("next-portal-ring");
    const content = $("arena-content");

    showAdvanceOverlay();
    ring.className = "portal-ring portal-ring--open";

    setTimeout(() => {
      resetBars();
      $("victory-screen").classList.add("hidden");
      $("victory-loot").innerHTML = "";
      content.classList.remove("arena-portal-reveal"); void content.offsetWidth;
      content.classList.add("arena-portal-reveal");
      spawnDust();
      focusAnswer();
    }, 1200);

    setTimeout(() => { ring.className = "portal-ring"; }, 1800);
  }

  function flee() { window.location.href = cfg.indexUrl; }

  return {
    init, start, revive, nextChallenge, flee,
    useUltimate, usarPocao, usarPergaminhoFuria,
    abrirConsumiveis, fecharConsumiveis,
  };
})();
