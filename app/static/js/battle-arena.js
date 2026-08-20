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

  // One last line as the boss goes down — the "epic exit" beat, before
  // the disintegrate animation finishes and victory() takes over.
  const DEFEAT_TAUNTS = [
    "Isso... isso ainda não acabou!",
    "Vocês vão se arrepender disso!",
    "Esta não é a minha forma final!",
    "Retornarei mais forte, aprendiz!",
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
    topicSlug: "", topicName: "", indexUrl: "/math/", buffs: {}, bossName: "O guardião", playerName: "aprendiz",
    bossIcon: "fa-dragon", bossColor: "purple-400",
    specialAttacks: SPECIAL_ATTACK_NAMES_FALLBACK, battleTaunts: BATTLE_TAUNT_FALLBACK,
    masteryThreshold: 0.5, nextTopicSlug: null, nextTopicName: null, nextTopicUrl: null, nextTopicResumoUrl: null,
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
  let defeatTriggered = false;
  let furyWasReady = false, comboAlertedTier = 0;

  function $(id) { return document.getElementById(id); }
  function rand(min, max) { return Math.floor(Math.random() * (max - min + 1)) + min; }
  function getPhase() { const pct = (bossHP / bossMaxHP) * 100; return pct > 66 ? 1 : pct > 33 ? 2 : 3; }

  function init(config) {
    cfg = Object.assign(cfg, config);

    // Fallback path only — reached when advanceToNextTopic()'s own
    // fetch-and-render-in-place transition (see below) fails and falls
    // back to a real page navigation instead. Arriving here means the
    // player already said "Avançar" once on the previous fight's victory
    // screen; the manual Enfrentar/Voltar choice on this fresh page load
    // would just be asking the same question again with no time to
    // actually use it before the timer fires. Swap that choice out for
    // the same presentation-only loading bar the normal (no-reload)
    // transition uses, so this fallback reads the same way instead of
    // flashing a decision screen it doesn't intend to honor.
    if (new URLSearchParams(window.location.search).get("autoentrar") === "1") {
      const ctaRow = $("story-cta-row");
      if (ctaRow) {
        ctaRow.outerHTML = loadingBarHtml() + cancelLinkHtml();
      }
      runLoadingBar(() => start());
    }
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
     it waits for the player to tap a button, then fades out and hands
     control back via the matching callback (onAdvance for moving on to
     the next topic, onPracticeAgain for rematching the one just won, to
     build up more mastery before moving on). When there's no next topic
     unlocked yet, only the practice-again option makes sense, so it's the
     one button shown, labeled "Continuar" like before. */
  function showVictoryReveal(onAdvance, onPracticeAgain) {
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
    // If a next topic in the trail is already unlocked, offer both moving
    // on AND replaying this one for more mastery — previously the win
    // only ever offered whichever one made the game's own decision for
    // the player. With nothing unlocked yet, replaying is the only
    // sensible option, so it's the lone button, still labeled "Continuar".
    if (cfg.nextTopicUrl) {
      html += '<div class="victory-btn-row">' +
        `<button type="button" class="victory-continue-btn" data-action="advance"><i class="fa-solid fa-wand-magic-sparkles"></i> Avançar para ${escapeHtml(cfg.nextTopicName)}</button>` +
        `<button type="button" class="victory-secondary-btn" data-action="practice"><i class="fa-solid fa-arrows-rotate"></i> Praticar ${escapeHtml(cfg.topicName)} de novo</button>` +
        "</div>";
    } else {
      html += `<button type="button" class="victory-continue-btn" data-action="practice"><i class="fa-solid fa-wand-magic-sparkles"></i> Continuar</button>`;
    }
    overlay.innerHTML = html;
    document.body.appendChild(overlay);

    const dismiss = (callback) => {
      overlay.classList.add("closing");
      setTimeout(() => {
        overlay.remove();
        if (callback) callback();
      }, 700);
    };
    const advanceBtn = overlay.querySelector('[data-action="advance"]');
    if (advanceBtn) advanceBtn.addEventListener("click", () => dismiss(onAdvance));
    const practiceBtn = overlay.querySelector('[data-action="practice"]');
    if (practiceBtn) practiceBtn.addEventListener("click", () => dismiss(onPracticeAgain));
  }

  /* ---------------- screen flow (story -> arena -> victory/defeat) ---------------- */

  function start() {
    // unlock() needs a real user gesture to actually resume the audio
    // context — true for the normal "Enfrentar" click, not guaranteed
    // when this fires on a timer via the ?autoentrar=1 auto-transition
    // (see init() above). Harmless either way: it just stays silently
    // suspended until some later click/tap resumes it, no error, no
    // broken battle — sound is the only thing that can be missing.
    BattleAudio.unlock();
    showInvocation();

    setTimeout(() => {
      $("story-screen").classList.add("hidden");
      const arena = $("battle-arena");
      arena.classList.remove("hidden");
      // remove+reflow+add so the entrance animation replays on a second
      // start() call (advancing to the next topic re-enters the arena
      // without a page reload — see advanceToNextTopic below) instead of
      // silently no-opping because the class was already present from the
      // very first fight.
      arena.classList.remove("epic-enter"); void arena.offsetWidth; arena.classList.add("epic-enter");
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
    defeatTriggered = false;
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
     shifts position between questions. Optional `delay` lets several
     bubbles from the same event queue up in sequence instead of all
     popping in at once (see the htmx:afterSwap handler below). */
  function showSpeechBubble(html, variant, delay) {
    const container = $("speech-bubble-container");
    if (!container) return;
    const spawn = () => {
      const el = document.createElement("div");
      el.className = "speech-bubble" + (variant ? " bubble-" + variant : "");
      el.innerHTML = html;
      container.appendChild(el);
      setTimeout(() => el.remove(), 3400);
    };
    if (delay) setTimeout(spawn, delay);
    else spawn();
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

    // Bubbles queue up in sequence instead of all firing at once — a
    // correct answer with a duo bonus AND a level-up used to get crammed
    // into one long wrapped line (or several bubbles landing on top of
    // each other), both hard to read in the ~3s they're on screen. Each
    // fact now gets its own short bubble, staggered so the eye can
    // actually track them one at a time.
    let queueDelay = 0;
    const STAGGER_MS = 500;
    const queueBubble = (html, variant) => {
      showSpeechBubble(html, variant, queueDelay);
      queueDelay += STAGGER_MS;
    };

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
      queueBubble(`<i class="fa-solid fa-check"></i> Correto! +${escapeHtml(d.xp || "0")} XP <span class="ml-1">${starsHtml(d.stars)}</span>`, "correct");
      if (d.bonusXp) {
        queueBubble(`<i class="fa-solid fa-people-arrows"></i> +${escapeHtml(d.bonusXp)} XP de dupla com ${escapeHtml(d.allyName)}`, "correct");
      }
      if (d.levelup === "true") {
        queueBubble(`<i class="fa-solid fa-star"></i> Subiu para o Nível ${escapeHtml(d.level)}!`, "achievement");
      }
    } else if (d.correct === "false") {
      onMiss();
      queueBubble(`<i class="fa-solid fa-xmark"></i> Quase — era <strong>${escapeHtml(d.correctAnswer)}</strong>`, "wrong");
    }
    if (d.achievements) {
      d.achievements.split("||").forEach((name) => {
        queueBubble(`<i class="fa-solid fa-trophy"></i> Nova conquista: <strong>${escapeHtml(name)}</strong>`, "achievement");
      });
    }
    if (d.needsReview === "true") {
      queueBubble(`<i class="fa-solid fa-book-bookmark"></i> Domínio caiu — vale revisar em breve.`, "review");
    }
    if (d.masteryRecovered === "true") {
      queueBubble(`<i class="fa-solid fa-arrow-trend-up"></i> Domínio recuperado!`, "recovered");
    }
    if (d.masteryScore !== undefined && d.masteryScore !== "") {
      updateNextTopicProgress(parseFloat(d.masteryScore));
    }
    focusAnswer();
  });

  /* Domínio em tempo real rumo ao próximo tópico da trilha (ex.: tabuada
     do 1 -> tabuada do 2) — a barra vive fora de #question-slot (não é
     substituída a cada troca de pergunta) então só precisa ser
     atualizada, nunca recriada. Quando o limiar é cruzado, o jogador
     avança sozinho para o próximo tópico em vez de precisar voltar ao
     mapa manualmente. */
  function updateNextTopicProgress(masteryScore) {
    if (!cfg.nextTopicSlug) return;
    const fill = $("next-topic-progress-fill");
    const pct = $("next-topic-progress-pct");
    const ratio = Math.max(0, Math.min(100, Math.round((masteryScore / cfg.masteryThreshold) * 100)));
    if (fill) fill.style.width = ratio + "%";
    if (pct) pct.textContent = ratio + "%";
    // Purely informational — this used to also redirect the page the
    // instant mastery crossed the threshold, *mid-fight*, with no boss
    // defeated and no victory screen: from the player's side that read
    // as "the game randomly leaves and jumps to something else" (real
    // bug report). Advancing to the next topic now only ever happens
    // through an actual victory (see victory() below), after the full
    // defeat sequence and a deliberate "Avançar" click — this bar is
    // just a preview of where that's heading.
  }

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
    // Boss can't actually fall to 0 until MIN_HITS_FOR_VICTORY correct
    // answers have landed (see the constant's comment above) — but the
    // floor itself drains gradually with each hit instead of clamping to
    // a flat near-zero value. A flat floor made the bar look completely
    // dead after a single lucky combo, even though several more correct
    // answers were still required — confusing ("the enemy has no health
    // left, why do I still have to answer questions?"). This way the bar
    // reads as real progress the whole fight: it starts able to drop to
    // half health on the very first hit, and that ceiling drains in step
    // with hitsLanded, reaching a true 0 exactly when the fight can end.
    const hitsProgress = Math.min(1, hitsLanded / MIN_HITS_FOR_VICTORY);
    const floor = hitsLanded >= MIN_HITS_FOR_VICTORY ? 0 : Math.round(bossMaxHP * 0.5 * (1 - hitsProgress));
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
      // Epic exit instead of cutting straight to the victory screen: a
      // bigger burst/shockwave than a normal hit, a last defiant line
      // from the boss (manga bubble, same "shout" style as the enrage
      // taunt), *then* the 1.5s disintegrate animation — and victory()
      // only fires once that's actually finished playing, not 700ms into
      // it like before (which cut the death animation off early).
      BattleFx.triggerCritFlash("crit-flash", true);
      BattleFx.spawnShockwave(boss, "#f87171");
      BattleFx.spawnBurst(boss, "#f87171", 46);
      showEnemyBubble(DEFEAT_TAUNTS[rand(0, DEFEAT_TAUNTS.length - 1)], true);
      setTimeout(() => boss.classList.add("boss-dead"), 250);
      setTimeout(victory, 1900);
    }
  }

  /* Boss "levels up" once per fight instead of just quietly losing: taunts,
     refills its own bar, and hits harder for the remainder of the fight
     (see ENRAGE_DMG_MULT in onMiss). Purely a mid-fight twist — it never
     changes what a correct/wrong answer means for real XP/mastery.

     Sequenced in three beats instead of firing everything on the same
     frame, so each is actually perceivable instead of blurring into one
     instant:
       1. immediate impact (shockwave/shake) — same language as any hit.
       2. ~400ms later, the actual surge: dedicated sound, a close-up
          pulse on the sprite, and the HP bar refilling with a slow,
          visible sweep instead of the ~0.2s snap a normal hit uses.
       3. once the bar has visibly filled, the boss "laughs" about it —
          a real manga-style speech bubble, the same dialogue system as
          its normal battle taunts. */
  function triggerBossEnrage() {
    bossEnraged = true;
    const boss = $("boss-sprite");
    const arena = $("battle-arena");
    const hpFill = $("boss-hp");
    const hpWrap = $("boss-hp-bar-wrap");

    BattleFx.triggerCritFlash("crit-flash", true);
    BattleFx.spawnShockwave(boss, "#ef4444");
    boss.classList.remove("crit-shake"); void boss.offsetWidth; boss.classList.add("crit-shake");

    lastPhase = 3;
    updateBossPhaseUi(3);
    const aura = $("boss-aura");
    aura.classList.add("aura-active", "aura-intense");
    showEnrageBanner();

    setTimeout(() => {
      BattleAudio.sfx.enrage();
      boss.classList.remove("boss-power-surge"); void boss.offsetWidth; boss.classList.add("boss-power-surge");
      arena.classList.remove("arena-zoom-punch"); void arena.offsetWidth; arena.classList.add("arena-zoom-punch");
      hpWrap.classList.add("hp-bar-surge-wrap");
      hpFill.classList.add("hp-bar-surge-fill");

      bossHP = bossMaxHP;
      updateHpBar("boss-hp", bossHP, bossMaxHP);

      setTimeout(() => {
        boss.classList.remove("boss-power-surge");
        arena.classList.remove("arena-zoom-punch");
        hpWrap.classList.remove("hp-bar-surge-wrap");
        hpFill.classList.remove("hp-bar-surge-fill");
      }, 1700);
    }, 400);

    setTimeout(() => {
      const taunt = ENRAGE_TAUNTS[rand(0, ENRAGE_TAUNTS.length - 1)];
      showEnemyBubble(taunt, true);
    }, 1550);
  }

  function showEnrageBanner() {
    const banner = document.createElement("div");
    banner.className = "phase-banner enrage-banner";
    banner.innerText = `💢 ${cfg.bossName} desperta com fúria renovada!`;
    // Anchored inside the arena card (position:absolute against
    // #battle-arena's position:relative), not document.body — this used
    // to be a position:fixed; inset:0 overlay that blotted out the whole
    // screen; now it's contained the same way the other battle toasts
    // (speech bubbles, battle alerts) are.
    $("battle-arena").appendChild(banner);
    setTimeout(() => banner.remove(), 2600);
  }

  function randomFrom(arr, fallback) {
    const pool = arr && arr.length ? arr : fallback;
    return pool && pool.length ? pool[rand(0, pool.length - 1)] : null;
  }

  /* Enemy "speech" floating above its own sprite — same technique as
     BattleFx.showFloatingDamage (positioned from the live target rect),
     just longer-lived and styled like a taunt instead of a number. */
  function showEnemyBubble(text, shout) {
    if (!text) return;
    const boss = $("boss-sprite");
    if (!boss) return;
    const rect = boss.getBoundingClientRect();
    const el = document.createElement("div");
    el.className = "enemy-bubble" + (shout ? " shout" : "");
    el.innerText = text;
    el.style.left = (rect.left + rect.width / 2) + "px";
    el.style.top = (rect.top - 14) + "px";
    document.body.appendChild(el);
    setTimeout(() => el.remove(), shout ? 3400 : 2800);
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
    if (defeatTriggered) return;
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
    showBattleAlert("☄️ " + (cfg.ultimateName || "Fúria Arcana Suprema") + "!", "crit");
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
    // See showEnrageBanner — anchored inside the arena card, not
    // document.body, so it no longer takes over the whole screen.
    $("battle-arena").appendChild(banner);
    setTimeout(() => banner.remove(), 2800);
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
    // still waits for a manual tap since there's actual reading on it,
    // but once dismissed the next step starts right away. There used to
    // be a "Novo desafio" / "Voltar ao mapa" box in between — showing a
    // choice screen right after the player just confirmed they won read
    // as a leftover decision gate, not a smooth transition, so it's gone;
    // "Fugir" in the arena footer is the one bail-out now, same as during
    // any other fight.
    //
    // Two real choices now instead of the game picking one for the
    // player: advance to the next unlocked topic (if any), or replay this
    // one for more mastery before moving on. See showVictoryReveal.
    showVictoryReveal(
      () => advanceToNextTopic(),
      () => nextChallenge()
    );

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
    // Same race as victory() above, mirrored: a wrong answer landing while
    // HP is already ~0 (rapid-fire or blank submits queue up several
    // in-flight misses) can call applyPlayerDamage more than once before
    // the first setTimeout(defeat, 800) fires — without this guard, each
    // one restacked its own defeat sound/screen.
    if (defeatTriggered) return;
    defeatTriggered = true;

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

  /* ---------------- advancing to the next topic without a page reload ---------------- */

  // Long enough to read the transition screen's info AND watch the
  // loading bar sweep across — a bare 1.4s was tuned for a screen with
  // interactive buttons the player might've clicked early; a pure
  // presentation screen wants a bit more room to actually register as
  // "loading" rather than a flicker.
  const STORY_TRANSITION_DELAY_MS = 2200;

  function progressColorClass(pct) {
    if (pct >= 75) return "text-emerald-400";
    if (pct >= 40) return "text-yellow-400";
    return "text-blood";
  }

  // The transition screen's one interactive element: a quiet escape
  // hatch (styled as a plain underlined link, not a button) in case the
  // player wants out before the timer commits them — same role "Fugir"
  // plays mid-fight, just muted so it doesn't compete with the loading
  // bar for attention.
  function cancelLinkHtml() {
    return `<a href="${cfg.indexUrl}" class="transition-cancel-link"><i class="fa-solid fa-arrow-left mr-1"></i>Cancelar e voltar ao mapa</a>`;
  }

  // Presentation only — no Enfrentar/Voltar choice, since the fight
  // starts on its own regardless of whether either would've been
  // clicked. This sweeping bar is what actually communicates "time
  // remaining" instead of a decision the timer overrides anyway.
  function loadingBarHtml() {
    return `
      <div class="transition-loading">
        <div class="transition-loading-icon"><i class="fa-solid fa-dungeon"></i></div>
        <div class="transition-loading-track"><div id="transition-loading-fill" class="transition-loading-fill"></div></div>
        <p class="transition-loading-label">Preparando o confronto...</p>
      </div>`;
  }

  // Animates #transition-loading-fill from 0 to 100% over
  // STORY_TRANSITION_DELAY_MS and calls onDone once that time is up — the
  // single timer both the visual bar and the actual transition are tied
  // to, so the bar never lies about how long is actually left.
  function runLoadingBar(onDone) {
    const fill = $("transition-loading-fill");
    if (fill) {
      fill.style.transitionDuration = STORY_TRANSITION_DELAY_MS + "ms";
      // Double rAF: without it the browser can coalesce the 0% starting
      // width and the 100% target into the same paint, skipping the
      // transition entirely instead of animating between them.
      requestAnimationFrame(() => requestAnimationFrame(() => { fill.style.width = "100%"; }));
    }
    setTimeout(onDone, STORY_TRANSITION_DELAY_MS);
  }

  // Applies one topic's battle config (fetched from .../resumo, see
  // practice_summary in app/mathematics/routes.py) onto cfg — the same
  // fields the inline <script> at the bottom of practice.html seeds on a
  // normal page load, just arriving over fetch() instead of a server
  // render, so the fight that follows behaves identically either way.
  function applyTopicConfig(data) {
    const prevBossColor = cfg.bossColor;

    cfg.topicSlug = data.topicSlug;
    cfg.topicName = data.topicName;
    cfg.victoryUrl = data.victoryUrl;
    cfg.newQuestionUrl = data.newQuestionUrl;
    cfg.bossName = data.guardian.name;
    cfg.bossIcon = data.guardian.icon;
    cfg.bossColor = data.guardian.color;
    cfg.bossTier = data.bossTier;
    if (data.specialAttacks && data.specialAttacks.length) cfg.specialAttacks = data.specialAttacks;
    if (data.battleTaunts && data.battleTaunts.length) cfg.battleTaunts = data.battleTaunts;
    if (data.ultimateName) cfg.ultimateName = data.ultimateName;
    cfg.masteryThreshold = data.masteryThreshold;
    cfg.chronicle = data.chronicle;
    if (data.buffs) cfg.buffs = data.buffs;
    cfg.nextTopicSlug = data.nextTopic ? data.nextTopic.slug : null;
    cfg.nextTopicName = data.nextTopic ? data.nextTopic.name : null;
    cfg.nextTopicUrl = data.nextTopic ? data.nextTopic.url : null;
    cfg.nextTopicResumoUrl = data.nextTopic ? data.nextTopic.resumoUrl : null;

    const avatarIcon = $("boss-avatar-icon");
    if (avatarIcon) avatarIcon.className = `fa-solid ${data.guardian.icon} text-${data.guardian.color}`;
    const nameLabel = $("boss-name-label");
    if (nameLabel) nameLabel.textContent = data.guardian.name;
    const spriteIcon = $("boss-sprite-icon");
    if (spriteIcon) spriteIcon.className = `fa-solid ${data.guardian.icon}`;
    // #boss-sprite itself carries the color class (see practice.html) —
    // same icon/color for every topic in a subject in practice (only the
    // tier name changes, see for_topic's docstring), but this keeps it
    // correct even if that ever stops being true.
    const sprite = $("boss-sprite");
    if (sprite) {
      if (prevBossColor) sprite.classList.remove(`text-${prevBossColor}`);
      sprite.classList.add(`text-${data.guardian.color}`);
    }

    const nextProgress = $("next-topic-progress");
    if (nextProgress) nextProgress.style.display = data.nextTopic ? "" : "none";
    const nextLabel = $("next-topic-name-label");
    if (nextLabel) nextLabel.textContent = cfg.nextTopicName || "";
    updateNextTopicProgress(data.topicMastery ? data.topicMastery.score : 0);
  }

  // Rebuilds the dedicated transition screen's content from a .../resumo
  // payload — the "nova template de dados daquela fase" the hand-off is
  // supposed to show, generated on the fly instead of coming from a fresh
  // page render, so advancing never has to leave the page. Deliberately a
  // *different* screen from #story-screen (see the comment on that div in
  // practice.html): #story-screen's Enfrentar/Voltar choice only makes
  // sense when a person is actually being asked to decide something —
  // here the fight starts on its own regardless, so this one swaps that
  // choice out for a loading bar (see loadingBarHtml) instead of
  // reusing buttons nobody has time to act on.
  function renderTransitionScreen(data) {
    const screen = $("transition-screen");
    if (!screen) return;

    let masteryHtml = "";
    if (data.topicMastery) {
      const pct = data.topicMastery.pct;
      masteryHtml = `
        <div class="inline-flex flex-wrap items-center justify-center gap-x-4 gap-y-2 bg-stone-900/70 border border-stone-700 rounded-lg px-4 py-2.5 text-sm font-sans text-stone-300">
          <span class="flex items-center gap-1.5">
            <i class="fa-solid fa-book-open text-stone-400"></i> Seu progresso:
            <strong class="${progressColorClass(pct)}">${pct}% de domínio</strong>
          </span>
          <span class="flex items-center gap-1.5">
            <i class="fa-solid fa-check text-green-400"></i> ${data.topicMastery.correctCount} acertos
            <i class="fa-solid fa-xmark text-red-400 ml-1"></i> ${data.topicMastery.wrongCount} erros
          </span>
          ${data.bestStars != null ? `<span class="flex items-center gap-1" title="Melhor tempo de resposta já registrado neste tópico">Recorde: ${starsHtml(data.bestStars)}</span>` : ""}
        </div>`;
    }

    let allyHtml = "";
    if (data.ally) {
      allyHtml = `
        <div class="inline-flex items-center gap-2 bg-purple-950/50 border border-purple-500 rounded-full px-4 py-1.5 text-purple-200 text-sm font-sans">
          <i class="fa-solid fa-people-group text-purple-300"></i>
          Lutando ao lado de <strong class="text-white">${escapeHtml(data.ally.username)}</strong> — respostas certas rendem bônus de dupla
        </div>`;
    }

    let recommendHtml = "";
    if (data.recommendFirst && data.recommendFirst.length) {
      const links = data.recommendFirst.map((t) =>
        `<a href="${t.url}" class="inline-flex items-center gap-1 bg-black/30 border border-gold/60 rounded-full px-3 py-0.5 text-gold hover:bg-gold hover:text-black transition-colors">
          <i class="fa-solid fa-map-pin"></i> ${escapeHtml(t.name)}
        </a>`
      ).join("");
      recommendHtml = `
        <div class="flex flex-wrap items-center justify-center gap-2 bg-yellow-950/40 border border-gold rounded-full px-4 py-1.5 text-yellow-100 text-sm font-sans">
          <i class="fa-solid fa-compass text-gold"></i>
          Recomendado praticar primeiro: ${links}
        </div>`;
    }

    const eqCount = data.equippedCount || 0;
    const guardian = data.guardian;

    screen.innerHTML = `
      <h1 class="text-3xl sm:text-4xl font-medieval text-gold drop-shadow-[0_0_15px_rgba(212,175,55,0.4)]">${escapeHtml(data.topicName)}</h1>
      <p class="text-stone-300 italic font-serif max-w-xl mx-auto">
        <strong class="text-${guardian.color}">${escapeHtml(guardian.name)}</strong> vigia esta trilha. Prove seu domínio de <strong class="text-gold">${escapeHtml(data.topicName)}</strong> para seguir em frente.
      </p>
      ${masteryHtml}
      ${allyHtml}
      ${recommendHtml}
      <div class="inline-flex items-center gap-3 bg-stone-900/70 border border-stone-700 rounded-lg px-4 py-2 text-sm font-sans text-stone-300">
        <i class="fa-solid fa-khanda text-purple-300"></i>
        ${eqCount ? eqCount + " equipamento(s) ativo(s)" : "Nenhum equipamento ativo"}
        <a href="${data.equipamentosUrl}" class="inline-flex items-center gap-1 bg-purple-950/50 border border-purple-500 rounded-full px-3 py-0.5 text-purple-200 hover:bg-purple-800 hover:text-white transition-colors">
          <i class="fa-solid fa-shield-halved"></i> preparar
        </a>
      </div>
      <div class="mentor-tip inline-flex items-start gap-3 bg-stone-900/70 border border-stone-700 rounded-lg p-4 text-left max-w-lg mx-auto">
        <span class="text-2xl shrink-0" aria-hidden="true">🦉</span>
        <div>
          <strong class="text-gold font-medieval">${data.mentorTip.kind === "curiosidade" ? "Você sabia?" : "Regra do jogo"}</strong>
          <p class="text-stone-300 text-sm mt-1 font-sans">${escapeHtml(data.mentorTip.text)}</p>
        </div>
      </div>
      ${loadingBarHtml()}
      ${cancelLinkHtml()}`;
    screen.classList.remove("epic-enter"); void screen.offsetWidth; screen.classList.add("epic-enter");
  }

  let advancingTopic = false;

  function advanceToNextTopic() {
    if (!cfg.nextTopicSlug || !cfg.nextTopicResumoUrl) { nextChallenge(); return; }
    if (advancingTopic) return;
    advancingTopic = true;

    fetch(cfg.nextTopicResumoUrl)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("bad response"))))
      .then((data) => {
        advancingTopic = false;
        applyTopicConfig(data);
        if (window.history && window.history.pushState) {
          window.history.pushState(null, "", data.practiceUrl);
        }
        document.title = data.topicName;

        $("battle-arena").classList.add("hidden");
        renderTransitionScreen(data);
        const screen = $("transition-screen");
        screen.classList.remove("hidden");

        runLoadingBar(() => {
          screen.classList.add("hidden");
          start();
        });
      })
      .catch(() => {
        advancingTopic = false;
        // Network hiccup fetching the summary — fall back to the old,
        // reliable full-page-navigation path rather than stranding the
        // player on a dead victory screen. That fallback lands on a fresh
        // page load with ?autoentrar=1, which init() (above) also treats
        // as presentation-only — same loading bar, not the manual
        // Enfrentar/Voltar screen.
        const url = cfg.nextTopicUrl || cfg.indexUrl;
        const sep = url.includes("?") ? "&" : "?";
        window.location.href = url + sep + "autoentrar=1";
      });
  }

  return {
    init, start, revive, nextChallenge, flee,
    useUltimate, usarPocao, usarPergaminhoFuria,
    abrirConsumiveis, fecharConsumiveis,
  };
})();
