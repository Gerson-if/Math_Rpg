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
  // A lucky combo/crit/ultimate streak used to be able to end a fight in
  // 4-5 correct answers — barely any practice at all. Boss HP can no
  // longer actually hit 0 (see applyBossDamage) until at least this many
  // correct answers have landed, regardless of how much damage is dealt;
  // it just sits at a sliver of HP until the player gets there.
  const MIN_HITS_FOR_VICTORY = 10;

  // Second wind: the first time the boss drops to a quarter health, it
  // refuses to just die quietly — it taunts, tops its own bar back up,
  // and hits harder for the rest of the fight. Once per fight (see
  // bossEnraged below), not every time HP dips low.
  const ENRAGE_HP_THRESHOLD = 0.25;
  const ENRAGE_DMG_MULT = 1.3;
  const ENRAGE_TAUNTS = [
    "Achou que seria fácil?",
    "Isso é só o começo da minha fúria!",
    "Você não vai vencer tão fácil assim!",
    "Sinta o verdadeiro poder do guardião!",
  ];

  // A wrong answer already counters with a normal hit (see onMiss) — this
  // gives the boss a chance to throw a named, harder-hitting special
  // attack instead, with its own callout and bigger impact fx. Names come
  // from the server per-subject (cfg.specialAttacks, see guardians.py) so
  // every enemy — not just the final guardian — has its own flavor
  // instead of one generic shared pool; this array is only the fallback
  // if that ever comes through empty.
  const SPECIAL_ATTACK_CHANCE = 0.22;
  const SPECIAL_ATTACK_MULT = 1.6;
  const SPECIAL_ATTACK_NAMES_FALLBACK = [
    "Investida Sombria", "Fúria Arcana", "Golpe Devastador",
    "Investida Ancestral", "Lâmina do Caos",
  ];

  // Enemy dialogue: a small chance per wrong answer (higher on a special
  // attack) that the enemy taunts the player — same per-subject flavor
  // source as the special attack names.
  const BATTLE_TAUNT_CHANCE = 0.18;
  const BATTLE_TAUNT_FALLBACK = ["Você não é páreo para mim!", "Tente de novo, aprendiz!"];

  let cfg = {
    topicSlug: "", indexUrl: "/math/", buffs: {}, bossName: "O guardião", playerName: "aprendiz",
    specialAttacks: SPECIAL_ATTACK_NAMES_FALLBACK, battleTaunts: BATTLE_TAUNT_FALLBACK,
  };
  let maxHP = BASE_MAX_HP, playerHP = maxHP;
  let bossMaxHP = BOSS_HP_BY_TIER.boss, bossHP = bossMaxHP;
  let combo = 0, fury = 0, lastPhase = 1;
  let hitsLanded = 0;
  let bossEnraged = false;
  let totalStars = 0, starRatingsCount = 0;
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

  /* Same ring+icon+fade language, one more time, for leaving mid-fight —
     "Fugir" used to just jump straight to the map with no transition at
     all, out of step with every other moment in the arena getting this
     treatment. Personalized with the player's own name for the "waiting
     for you" framing. */
  function showFarewell(onDone) {
    const overlay = document.createElement("div");
    overlay.className = "intro-overlay";
    overlay.innerHTML =
      '<div class="intro-sigil-wrap">' +
      '<div class="intro-ring"></div>' +
      '<div class="intro-ring reverse"></div>' +
      '<div class="intro-icon"><i class="fa-solid fa-dungeon"></i></div>' +
      "</div>" +
      `<div class="intro-text">Até logo, ${escapeHtml(cfg.playerName || "aprendiz")}. O Reino aguarda seu retorno...</div>`;
    document.body.appendChild(overlay);
    setTimeout(onDone, 1700);
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

  /* Aggregate star performance across every correct answer this fight
     (see totalStars/starRatingsCount above) into a 1-3 star "battle
     rank" — the same per-question rating, just recapped as one epic
     number at the end instead of only flashing by one question at a
     time during the fight itself. */
  function performanceStarsHtml() {
    if (starRatingsCount === 0) return "";
    const avg = totalStars / starRatingsCount;
    const rounded = Math.max(1, Math.min(3, Math.round(avg)));
    const labels = { 1: "Bom combate!", 2: "Ótimo desempenho!", 3: "Desempenho Lendário!" };
    let stars = "";
    for (let i = 0; i < 3; i++) {
      const delay = (0.9 + i * 0.15).toFixed(2);
      stars += `<i class="fa-solid fa-star victory-star${i < rounded ? " filled" : ""}" style="animation-delay:${delay}s"></i>`;
    }
    return `<div class="victory-stars">${stars}</div><div class="victory-stars-label">${labels[rounded]}</div>`;
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
      '<div class="victory-title">Vitória!</div>' +
      performanceStarsHtml();
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
    hitsLanded = 0;
    bossEnraged = false;
    totalStars = 0; starRatingsCount = 0;
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
    updateConsumablesBadge();
    $("speech-bubble-container") && ($("speech-bubble-container").innerHTML = "");
    $("battle-alert-container") && ($("battle-alert-container").innerHTML = "");
    $("loot-toast-container") && ($("loot-toast-container").innerHTML = "");
    renderHitsProgress();
  }

  /* Ten dots tracking real progress toward MIN_HITS_FOR_VICTORY — lets the
     player see "how much further" instead of just watching an HP bar that
     mysteriously refuses to hit zero once it's down to a sliver. */
  function renderHitsProgress() {
    const track = $("hits-progress");
    if (!track) return;
    let html = "";
    for (let i = 0; i < MIN_HITS_FOR_VICTORY; i++) {
      html += `<span class="hit-dot${i < hitsLanded ? " filled" : ""}"></span>`;
    }
    track.innerHTML = html;
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

  /* Response-time star rating (0-3, server-decided — see
     STAR_TIME_THRESHOLDS_MS in app/mathematics/routes.py) shown next to
     the correct-answer bubble. Purely cosmetic: a slow-but-correct answer
     still counts fully for real XP/mastery, it just earns fewer stars. */
  function starsHtml(rawStars) {
    const n = Math.max(0, Math.min(3, parseInt(rawStars || "0", 10) || 0));
    let html = "";
    for (let i = 0; i < 3; i++) {
      html += `<i class="fa-solid fa-star" style="color:${i < n ? "#fbbf24" : "rgba(255,255,255,0.2)"}; font-size:0.7em;"></i>`;
    }
    return html;
  }

  document.body.addEventListener("htmx:afterSwap", (evt) => {
    if (evt.target.id !== "question-slot") return;
    const d = evt.target.dataset;
    if (d.correct === "true") {
      onHit(d.crit === "true", {
        name: d.lootName, icon_key: d.lootIcon, rarity: d.lootRarity,
        passive_type: d.lootPassive, passive_value: parseFloat(d.lootValue || "0"),
      });
      // Tallied for the end-of-fight performance recap (see
      // showVictoryReveal) — every correct answer counts, not just the
      // ones landed after the boss is already low on HP.
      totalStars += parseInt(d.stars || "0", 10) || 0;
      starRatingsCount++;
      let msg = `<i class="fa-solid fa-check"></i> Correto! +${escapeHtml(d.xp || "0")} XP <span class="ml-1">${starsHtml(d.stars)}</span>`;
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
    hitsLanded++;
    renderHitsProgress();
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
    // Boss can't actually fall below 1 HP until MIN_HITS_FOR_VICTORY
    // correct answers have landed — see the constant's comment above.
    const floor = hitsLanded >= MIN_HITS_FOR_VICTORY ? 0 : 1;
    bossHP = Math.max(floor, bossHP - dmg);
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

    // Second wind — checked before the normal death/phase handling below,
    // so a killing blow that also happens to cross the enrage threshold
    // for the first time triggers the comeback instead of ending the fight.
    if (!bossEnraged && bossHP > 0 && bossHP / bossMaxHP <= ENRAGE_HP_THRESHOLD) {
      triggerBossEnrage();
      return;
    }

    checkPhaseTransition();
    if (bossHP <= 0) {
      boss.classList.add("boss-dead");
      setTimeout(victory, 800);
    }
  }

  /* Boss "levels up" once per fight instead of just quietly losing: taunts,
     refills its own bar, and hits harder for the remainder of the fight
     (see ENRAGE_DMG_MULT in onMiss). Purely a mid-fight twist — it never
     changes what a correct/wrong answer means for real XP/mastery. */
  function triggerBossEnrage() {
    bossEnraged = true;
    const boss = $("boss-sprite");

    BattleAudio.sfx.ultimate();
    BattleFx.triggerCritFlash("crit-flash", true);
    BattleFx.spawnShockwave(boss, "#ef4444");
    boss.classList.remove("crit-shake"); void boss.offsetWidth; boss.classList.add("crit-shake");

    bossHP = bossMaxHP;
    updateHpBar("boss-hp", bossHP, bossMaxHP);
    lastPhase = 3;
    updateBossPhaseUi(3);
    const aura = $("boss-aura");
    aura.classList.add("aura-active", "aura-intense");

    const taunt = ENRAGE_TAUNTS[rand(0, ENRAGE_TAUNTS.length - 1)];
    showEnrageBanner(taunt);
  }

  function showEnrageBanner(taunt) {
    const banner = document.createElement("div");
    banner.className = "phase-banner enrage-banner";
    banner.innerHTML =
      `<div>💢 ${escapeHtml(cfg.bossName)} desperta com fúria renovada!</div>` +
      `<div class="enrage-taunt">"${escapeHtml(taunt)}"</div>`;
    document.body.appendChild(banner);
    setTimeout(() => banner.remove(), 3200);
  }

  function randomFrom(arr, fallback) {
    const pool = arr && arr.length ? arr : fallback;
    return pool && pool.length ? pool[rand(0, pool.length - 1)] : null;
  }

  /* Enemy "speech" floating above its own sprite — same technique as
     BattleFx.showFloatingDamage (positioned from the live target rect),
     just longer-lived and styled like a taunt instead of a number. */
  function showEnemyBubble(text) {
    if (!text) return;
    const boss = $("boss-sprite");
    if (!boss) return;
    const rect = boss.getBoundingClientRect();
    const el = document.createElement("div");
    el.className = "enemy-bubble";
    el.innerText = text;
    el.style.left = (rect.left + rect.width / 2) + "px";
    el.style.top = (rect.top - 14) + "px";
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 2800);
  }

  function onMiss() {
    combo = 0;
    updateComboUi();

    // The boss occasionally throws a named special attack instead of a
    // plain counter-hit — more likely once it's enraged. Every enemy tier
    // (minion/elite/boss/supreme) can throw one, not just the final
    // guardian — this isn't gated by bossTier anywhere above.
    const isSpecial = Math.random() < (bossEnraged ? SPECIAL_ATTACK_CHANCE * 1.6 : SPECIAL_ATTACK_CHANCE);

    const range = CONFIG.bossDmgByPhase[getPhase() - 1];
    let dmg = rand(range.min, range.max);
    if (bossEnraged) dmg = Math.round(dmg * ENRAGE_DMG_MULT);
    if (isSpecial) dmg = Math.round(dmg * SPECIAL_ATTACK_MULT);

    const boss = $("boss-sprite"), hero = $("hero-avatar");
    if (isSpecial) {
      const name = randomFrom(cfg.specialAttacks, SPECIAL_ATTACK_NAMES_FALLBACK);
      showBattleAlert("💥 " + name + "!", "danger");
      showEnemyBubble(randomFrom(cfg.battleTaunts, BATTLE_TAUNT_FALLBACK));
      BattleFx.spawnShockwave(boss, "#ef4444");
    } else if (Math.random() < BATTLE_TAUNT_CHANCE) {
      showEnemyBubble(randomFrom(cfg.battleTaunts, BATTLE_TAUNT_FALLBACK));
    }
    BattleFx.launchProjectile(boss, hero, "#ef4444", () => applyPlayerDamage(dmg, isSpecial), isSpecial);

    const arena = $("battle-arena");
    arena.classList.remove("hit-flash"); void arena.offsetWidth; arena.classList.add("hit-flash");
    hero.classList.remove("hero-hurt-anim"); void hero.offsetWidth; hero.classList.add("hero-hurt-anim");
    if (isSpecial) {
      arena.classList.remove("crit-shake"); void arena.offsetWidth; arena.classList.add("crit-shake");
      setTimeout(() => arena.classList.remove("crit-shake"), 450);
    }
    const fx = $("hero-fx");
    fx.innerHTML = '<i class="fa-solid fa-bolt-lightning miss-spark"></i>';
    setTimeout(() => { fx.innerHTML = ""; }, 500);
  }

  function applyPlayerDamage(dmg, isSpecial) {
    playerHP = Math.max(0, playerHP - dmg);
    BattleFx.showFloatingDamage("hero-avatar", "-" + dmg, "#ef4444", !!isSpecial);
    updateHpBar("player-hp", playerHP, maxHP);
    BattleFx.spawnBurst($("hero-avatar"), "#ef4444", isSpecial ? 26 : 14);
    BattleAudio.sfx.hit(!!isSpecial);
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
    updateConsumablesBadge();
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
    updateConsumablesBadge();
    BattleFx.spawnBurst($("hero-avatar"), "#f472b6", 14);
    BattleAudio.sfx.heal();
    showBattleAlert("📜 Pergaminho usado! +" + CONFIG.furyScrollAmount + " Fúria");
  }

  // Small resource-count badge on the "Consumíveis" HUD button, so the
  // player can see at a glance whether anything's left without opening
  // the screen.
  function updateConsumablesBadge() {
    const badge = $("consumables-total-badge");
    if (badge) badge.innerText = potions + furyScrolls;
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

  let advancingChallenge = false;

  function victory() {
    // A hit that lands just as the boss reaches 0 HP can overlap with
    // another already-in-flight hit (combo tail, ultimate) that also
    // clamps to 0 and re-triggers this — without a guard, each call built
    // its own non-auto-dismissing overlay, stacking blocking screens.
    if (victoryTriggered) return;
    victoryTriggered = true;

    BattleAudio.sfx.victory();
    // The chapter-reveal overlay below IS the victory transition — it
    // still waits for a manual "Continuar" since there's actual reading
    // on it, but once dismissed the next fight starts right away. There
    // used to be a "Novo desafio" / "Voltar ao mapa" box in between —
    // showing a choice screen right after the player just confirmed they
    // won read as a leftover decision gate, not a smooth transition,
    // so it's gone; "Fugir" in the arena footer is the one bail-out now,
    // same as during any other fight.
    showVictoryReveal(() => nextChallenge());

    if (claimingVictory) return;
    claimingVictory = true;
    fetch(cfg.victoryUrl, {
      method: "POST",
      headers: { "X-CSRFToken": cfg.csrfToken },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((item) => {
        claimingVictory = false;
        if (item) BattleLoot.toast("loot-toast-container", item);
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
    // A hit landing right as the reveal's "Continuar" is tapped could
    // theoretically fire this twice — guard keeps the transition single.
    if (advancingChallenge) return;
    advancingChallenge = true;

    const ring = $("next-portal-ring");
    const content = $("arena-content");

    showAdvanceOverlay();
    ring.className = "portal-ring portal-ring--open";

    setTimeout(() => {
      resetBars();
      content.classList.remove("arena-portal-reveal"); void content.offsetWidth;
      content.classList.add("arena-portal-reveal");
      spawnDust();
      focusAnswer();
      advancingChallenge = false;
    }, 1200);

    setTimeout(() => { ring.className = "portal-ring"; }, 1800);
  }

  function flee() {
    showFarewell(() => { window.location.href = cfg.indexUrl; });
  }

  return {
    init, start, revive, nextChallenge, flee,
    useUltimate, usarPocao, usarPergaminhoFuria,
    abrirConsumiveis, fecharConsumiveis,
  };
})();
