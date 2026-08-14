/* Canvas particle/projectile/shockwave layer for the battle arena, ported
   from the reference battle template. Damage only actually lands (bar
   moves, sound plays) when the projectile arrives — not the instant the
   server confirms the answer — so the hit still *reads* as an attack. */
const BattleFx = (() => {
  let canvas, ctx, arenaEl;
  let particles = [], projectiles = [], shockwaves = [];
  let loopRunning = false;

  function init(canvasId, arenaId) {
    canvas = document.getElementById(canvasId);
    arenaEl = document.getElementById(arenaId);
    ctx = canvas.getContext("2d");
    resize();
    window.addEventListener("resize", resize);
  }

  function resize() {
    if (!canvas || !arenaEl) return;
    const rect = arenaEl.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;
  }

  function relativePoint(el) {
    const r = el.getBoundingClientRect();
    const arenaRect = arenaEl.getBoundingClientRect();
    return { x: r.left + r.width / 2 - arenaRect.left, y: r.top + r.height / 2 - arenaRect.top };
  }

  function launchProjectile(fromEl, toEl, color, onArrive, big) {
    const from = relativePoint(fromEl);
    const to = relativePoint(toEl);
    projectiles.push({
      x: from.x, y: from.y, x0: from.x, y0: from.y, tx: to.x, ty: to.y,
      t: 0, dur: big ? 550 : 380, color, onArrive, size: big ? 14 : 8,
    });
    ensureLoop();
  }

  function spawnBurst(el, color, count) {
    const p = relativePoint(el);
    for (let i = 0; i < count; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = 1 + Math.random() * 4;
      particles.push({
        x: p.x, y: p.y, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed,
        life: 0, maxLife: 30 + Math.random() * 20, color, size: 2 + Math.random() * 3,
      });
    }
    ensureLoop();
  }

  function spawnShockwave(el, color) {
    const p = relativePoint(el);
    shockwaves.push({ x: p.x, y: p.y, r: 4, maxR: 90, life: 0, maxLife: 26, color });
    ensureLoop();
  }

  function ensureLoop() { if (!loopRunning) { loopRunning = true; requestAnimationFrame(tick); } }

  function drawGlow(x, y, size, color) {
    const grad = ctx.createRadialGradient(x, y, 0, x, y, size * 3);
    grad.addColorStop(0, color);
    grad.addColorStop(1, "transparent");
    ctx.fillStyle = grad;
    ctx.beginPath(); ctx.arc(x, y, size * 3, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.beginPath(); ctx.arc(x, y, size * 0.4, 0, Math.PI * 2); ctx.fill();
  }

  function tick() {
    if (!ctx) { loopRunning = false; return; }
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    for (let i = projectiles.length - 1; i >= 0; i--) {
      const pr = projectiles[i];
      pr.t += 16.67;
      const progress = Math.min(1, pr.t / pr.dur);
      const ease = 1 - Math.pow(1 - progress, 3);
      pr.x = pr.x0 + (pr.tx - pr.x0) * ease;
      pr.y = pr.y0 + (pr.ty - pr.y0) * ease;
      drawGlow(pr.x, pr.y, pr.size, pr.color);
      if (progress >= 1) {
        const cb = pr.onArrive;
        projectiles.splice(i, 1);
        if (cb) cb();
      }
    }

    for (let i = particles.length - 1; i >= 0; i--) {
      const P = particles[i];
      P.x += P.vx; P.y += P.vy; P.vy += 0.08; P.life++;
      const alpha = 1 - P.life / P.maxLife;
      if (alpha <= 0) { particles.splice(i, 1); continue; }
      ctx.globalAlpha = Math.max(0, alpha);
      ctx.fillStyle = P.color;
      ctx.beginPath(); ctx.arc(P.x, P.y, P.size, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalAlpha = 1;

    for (let i = shockwaves.length - 1; i >= 0; i--) {
      const s = shockwaves[i];
      s.life++;
      s.r = 4 + (s.maxR - 4) * (s.life / s.maxLife);
      const alpha = 1 - s.life / s.maxLife;
      if (alpha <= 0) { shockwaves.splice(i, 1); continue; }
      ctx.globalAlpha = Math.max(0, alpha * 0.8);
      ctx.strokeStyle = s.color;
      ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.globalAlpha = 1;

    if (projectiles.length || particles.length || shockwaves.length) requestAnimationFrame(tick);
    else loopRunning = false;
  }

  function triggerCritFlash(flashId, big) {
    const flash = document.getElementById(flashId);
    flash.classList.remove("flash-anim", "flash-anim-big");
    void flash.offsetWidth;
    flash.classList.add(big ? "flash-anim-big" : "flash-anim");
  }

  function showFloatingDamage(targetId, text, color, isCrit) {
    const target = document.getElementById(targetId);
    const rect = target.getBoundingClientRect();
    const el = document.createElement("div");
    el.className = "damage-text" + (isCrit ? " crit-text" : "");
    el.style.color = color;
    el.innerText = text;
    el.style.left = rect.left + rect.width / 2 + "px";
    el.style.top = rect.top + rect.height / 2 + "px";
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 1000);
  }

  return { init, launchProjectile, spawnBurst, spawnShockwave, triggerCritFlash, showFloatingDamage };
})();
