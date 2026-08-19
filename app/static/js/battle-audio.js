/* Procedural sound effects for the battle arena — Web Audio oscillators
   and filtered noise only, zero audio files, ported from the reference
   battle template almost verbatim. Needs a user gesture to unlock
   (browsers block autoplay audio contexts) — call BattleAudio.unlock()
   from the same click handler that starts the battle. */
const BattleAudio = (() => {
  let actx = null;

  function unlock() {
    if (!actx) actx = new (window.AudioContext || window.webkitAudioContext)();
    if (actx.state === "suspended") actx.resume();
    return actx;
  }

  function tone(freq, dur, type, vol, startOffset, freqEnd) {
    if (!actx) return;
    const osc = actx.createOscillator();
    const gain = actx.createGain();
    osc.type = type || "sine";
    const t0 = actx.currentTime + (startOffset || 0);
    osc.frequency.setValueAtTime(freq, t0);
    if (freqEnd) osc.frequency.exponentialRampToValueAtTime(freqEnd, t0 + dur);
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.linearRampToValueAtTime(vol || 0.2, t0 + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.001, t0 + dur);
    osc.connect(gain).connect(actx.destination);
    osc.start(t0);
    osc.stop(t0 + dur + 0.05);
  }

  function noiseBurst(dur, vol, filterFreq) {
    if (!actx) return;
    const bufferSize = Math.max(1, Math.floor(actx.sampleRate * dur));
    const buffer = actx.createBuffer(1, bufferSize, actx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < bufferSize; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / bufferSize);
    const src = actx.createBufferSource();
    src.buffer = buffer;
    const filter = actx.createBiquadFilter();
    filter.type = "bandpass";
    filter.frequency.value = filterFreq || 1200;
    const gain = actx.createGain();
    gain.gain.value = vol || 0.2;
    src.connect(filter).connect(gain).connect(actx.destination);
    src.start();
  }

  const sfx = {
    cast() { tone(440, 0.18, "sine", 0.15, 0, 880); },
    hit(isCrit) {
      if (isCrit) { tone(220, 0.25, "sawtooth", 0.22, 0, 90); tone(660, 0.2, "square", 0.12, 0.02); }
      else { noiseBurst(0.15, 0.25, 900); tone(140, 0.15, "sine", 0.15, 0, 60); }
    },
    heal() { tone(523, 0.15, "sine", 0.15, 0); tone(659, 0.15, "sine", 0.15, 0.1); tone(784, 0.2, "sine", 0.15, 0.2); },
    ultimate() { tone(200, 0.5, "sawtooth", 0.2, 0, 900); noiseBurst(0.4, 0.3, 2000); },
    // Boss "second wind" — a low rumble/roar (distinct from ultimate(),
    // which is the *player's* big hit) followed by a rising, laugh-like
    // three-note motif timed to land as the HP bar finishes refilling.
    enrage() {
      tone(90, 0.55, "sawtooth", 0.2, 0, 150);
      noiseBurst(0.3, 0.22, 500);
      [330, 415, 523].forEach((f, i) => tone(f, 0.3, "triangle", 0.17, 0.4 + i * 0.15));
    },
    victory() { [523, 659, 784, 1046].forEach((f, i) => tone(f, 0.3, "triangle", 0.18, i * 0.15)); },
    defeat() { tone(300, 0.6, "sine", 0.2, 0, 80); },
    loot(rarityId) {
      const notas = { comum: [523], magico: [523, 784], raro: [523, 784, 1046], lendario: [523, 784, 1046, 1318] };
      (notas[rarityId] || notas.comum).forEach((f, i) => tone(f, 0.22, "triangle", 0.12, i * 0.07));
    },
  };

  return { unlock, sfx };
})();
