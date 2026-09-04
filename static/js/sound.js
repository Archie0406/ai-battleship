// sound.js — subtle, synthesized sound effects via the Web Audio API.
// No external audio files: every sound is a short generated tone, so
// there's nothing to fail to load. Fully optional — every call is
// wrapped so a browser that blocks audio (or hasn't granted permission
// yet) never breaks gameplay; muting is a no-op fallback, not a crash.
window.BattleshipSound = (function () {
  const STORAGE_KEY = "ai-battleship-muted";
  let ctx = null;
  let muted = localStorage.getItem(STORAGE_KEY) === "true";

  function getContext() {
    if (!ctx) {
      try {
        ctx = new (window.AudioContext || window.webkitAudioContext)();
      } catch (e) {
        ctx = null;
      }
    }
    if (ctx && ctx.state === "suspended") {
      ctx.resume().catch(() => {});
    }
    return ctx;
  }

  function tone(freqStart, freqEnd, duration, gainPeak, type) {
    if (muted) return;
    const audioCtx = getContext();
    if (!audioCtx) return;
    try {
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = type || "sine";
      const now = audioCtx.currentTime;
      osc.frequency.setValueAtTime(freqStart, now);
      if (freqEnd !== freqStart) {
        osc.frequency.exponentialRampToValueAtTime(Math.max(freqEnd, 1), now + duration);
      }
      gain.gain.setValueAtTime(0.0001, now);
      gain.gain.exponentialRampToValueAtTime(gainPeak, now + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + duration);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start(now);
      osc.stop(now + duration + 0.02);
    } catch (e) {
      // audio is entirely optional; swallow any failure silently
    }
  }

  function chord(notes, noteDuration, gap) {
    notes.forEach((freq, i) => {
      setTimeout(() => tone(freq, freq, noteDuration, 0.08, "triangle"), i * gap);
    });
  }

  const SOUNDS = {
    select: () => tone(760, 900, 0.06, 0.05, "square"),
    hit: () => tone(420, 180, 0.14, 0.11, "sawtooth"),
    miss: () => tone(160, 110, 0.16, 0.06, "sine"),
    sink: () => tone(560, 90, 0.45, 0.1, "sawtooth"),
    victory: () => chord([440, 554, 659, 880], 0.16, 130),
    defeat: () => tone(300, 140, 0.6, 0.09, "triangle"),
    turn: () => tone(500, 500, 0.04, 0.03, "sine"),
  };

  function play(name) {
    const fn = SOUNDS[name];
    if (fn) fn();
  }

  function isMuted() {
    return muted;
  }

  function setMuted(value) {
    muted = value;
    localStorage.setItem(STORAGE_KEY, String(muted));
    updateButtons();
  }

  function toggleMute() {
    setMuted(!muted);
    if (!muted) play("select");
  }

  function updateButtons() {
    document.querySelectorAll("#muteBtn").forEach((btn) => {
      btn.classList.toggle("muted", muted);
      btn.setAttribute("aria-pressed", String(muted));
      const icon = btn.querySelector("#muteIcon, .mute-icon");
      if (icon) icon.textContent = muted ? "✕" : "♪";
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    updateButtons();
    document.querySelectorAll("#muteBtn").forEach((btn) => {
      btn.addEventListener("click", toggleMute);
    });
  });

  return { play, toggleMute, isMuted, setMuted };
})();
