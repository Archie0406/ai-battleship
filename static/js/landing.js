// landing.js — scroll-reveal, HUD status ticker, algorithm card cursor glow
(function () {
  // ------------------------------------------------------------------
  // Scroll reveal (IntersectionObserver) — respects reduced motion
  // ------------------------------------------------------------------
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const revealEls = document.querySelectorAll(".reveal, .reveal-stagger");

  if (revealEls.length) {
    if (prefersReducedMotion || !("IntersectionObserver" in window)) {
      revealEls.forEach((el) => el.classList.add("is-visible"));
    } else {
      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              entry.target.classList.add("is-visible");
              observer.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.15, rootMargin: "0px 0px -40px 0px" }
      );
      revealEls.forEach((el) => observer.observe(el));
    }
  }

  // ------------------------------------------------------------------
  // HUD readout ticker — cycles through short AI status lines
  // ------------------------------------------------------------------
  const readout = document.getElementById("readoutStatus");
  if (readout) {
    const messages = [
      "SCANNING GRID SECTOR 4-7",
      "PROBABILITY MAP UPDATING",
      "TARGET CONFIDENCE 82%",
      "AWAITING NEXT CONTACT",
      "FLEET STATUS NOMINAL",
    ];
    let i = 0;
    setInterval(() => {
      i = (i + 1) % messages.length;
      readout.textContent = messages[i];
    }, 2600);
  }

  // ------------------------------------------------------------------
  // Algorithm card cursor-tracked glow
  // ------------------------------------------------------------------
  document.querySelectorAll(".algo-card").forEach((card) => {
    card.addEventListener("pointermove", (e) => {
      const rect = card.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 100;
      const y = ((e.clientY - rect.top) / rect.height) * 100;
      card.style.setProperty("--mx", x + "%");
      card.style.setProperty("--my", y + "%");
    });
  });
})();
