"use strict";

/**
 * 읽는 힘 — 첫 진입 인트로 애니메이션 (독립 컴포넌트)
 * - 원고지 네 칸(읽 / 는 / 빈칸 / 힘)에 글자가 날아와 안착하고, 두 문구가 차례로 나타난다.
 * - 탭(sessionStorage)마다 한 번만 자동 재생하고, 새로고침·재방문에서는 건너뛴다.
 * - 건너뛰기 버튼(또는 Esc)으로 즉시 종료하고, 개발용 '인트로 다시 보기'로 다시 재생한다.
 * - <head>에서 동기 로드해 메인 화면이 먼저 비치는 깜빡임을 막는다.
 */
(function () {
  const INTRO_CONFIG = {
    storageKey: "readingIntroSeen",
    // 개발·시연용 '인트로 다시 보기' 버튼
    // "auto": localhost·127.0.0.1에서만 표시 / true: 항상 표시 / false: 항상 숨김(배포 기본)
    showReplayButton: "auto",
    // 주소에 ?intro=1 을 붙이면 이미 본 탭에서도 강제로 재생(미리보기용)
    forceParam: "intro",
  };

  const CELLS = ["읽", "는", "", "힘"];
  const LINE_1 = "하얀 건 종이, 검은 건 글씨?";
  const LINE_2 = "읽을 수 있다고 다 이해하는 것은 아니니까!";
  const SWARM_CHARS = "가나다라마바사아자차카타파하글말뜻문장생각이해책쓰기종이낱말읽는힘";

  // 시나리오 타임라인(ms) — 총 7초
  const T = {
    sheetStart: 100,
    sheetDur: 800,
    swarmStart: 900,
    swarmEnd: 2700,
    glyphLand: [1500, 2000, null, 2500],
    glyphFlight: 520,
    line1Start: 3000,
    line1Dur: 700,
    markStart: 3750,
    markDur: 600,
    line2Start: 4500,
    line2Dur: 800,
    exitStart: 6300,
    exitDur: 700,
  };

  const root = document.documentElement;
  const forced = new URLSearchParams(window.location.search).get(INTRO_CONFIG.forceParam) === "1";
  let current = null; // 재생 중인 인트로 { overlay, timers, lastFocus }

  function hasSeen() {
    try {
      return window.sessionStorage.getItem(INTRO_CONFIG.storageKey) === "1";
    } catch (err) {
      return false;
    }
  }

  function markSeen() {
    try {
      window.sessionStorage.setItem(INTRO_CONFIG.storageKey, "1");
    } catch (err) {
      /* sessionStorage를 쓸 수 없으면 매번 재생될 수 있지만 앱 동작에는 영향 없음 */
    }
  }

  function replayEnabled() {
    const opt = INTRO_CONFIG.showReplayButton;
    if (opt === "auto") {
      return ["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname);
    }
    return opt === true;
  }

  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  // 자동 재생할 탭이면 DOM이 그려지기 전에 흰 화면으로 덮어 둔다.
  const shouldAutoplay = forced || !hasSeen();
  if (shouldAutoplay) root.classList.add("intro-pending");

  /* ---------------- 화면 구성 ---------------- */

  function buildOverlay() {
    const overlay = document.createElement("div");
    overlay.className = "intro";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", `읽는 힘 — ${LINE_1} ${LINE_2}`);

    const skip = document.createElement("button");
    skip.type = "button";
    skip.className = "intro-skip";
    skip.textContent = "건너뛰기";
    overlay.appendChild(skip);

    const stage = document.createElement("div");
    stage.className = "intro-stage";
    stage.setAttribute("aria-hidden", "true");

    const sheet = document.createElement("div");
    sheet.className = "intro-sheet";
    CELLS.forEach((ch) => {
      const cell = document.createElement("div");
      cell.className = "intro-cell";
      if (ch) {
        const glyph = document.createElement("span");
        glyph.className = "intro-glyph";
        glyph.textContent = ch;
        cell.appendChild(glyph);
      }
      sheet.appendChild(cell);
    });

    const line1 = document.createElement("p");
    line1.className = "intro-line intro-line1";
    const mark = document.createElement("span");
    mark.className = "intro-mark";
    const markText = document.createElement("span");
    markText.className = "intro-mark-text";
    markText.textContent = LINE_1;
    const markBar = document.createElement("span");
    markBar.className = "intro-mark-bar";
    mark.append(markBar, markText);
    line1.appendChild(mark);

    const line2 = document.createElement("p");
    line2.className = "intro-line intro-line2";
    line2.textContent = LINE_2;

    const swarm = document.createElement("div");
    swarm.className = "intro-swarm";

    stage.append(sheet, line1, line2);
    overlay.append(swarm, stage);
    return { overlay, skip, sheet, line1, line2, markBar, swarm };
  }

  /* ---------------- 재생 / 종료 ---------------- */

  async function play(options = {}) {
    if (current) return;
    markSeen();

    const parts = buildOverlay();
    const { overlay, skip } = parts;
    const lastFocus = document.activeElement;
    const inertTargets = Array.from(document.body.children).filter((node) => !node.hasAttribute("inert"));

    document.body.appendChild(overlay);
    inertTargets.forEach((node) => node.setAttribute("inert", ""));
    root.classList.add("intro-active");
    root.classList.remove("intro-pending");

    current = { overlay, timers: [], lastFocus, inertTargets, closing: false };
    skip.addEventListener("click", () => close(true));
    overlay.addEventListener("keydown", (e) => {
      if (e.key === "Escape") close(true);
    });
    skip.focus({ preventScroll: true });

    await waitForFont();
    if (!current || current.overlay !== overlay) return;

    const canAnimate = typeof overlay.animate === "function";
    if (prefersReducedMotion() || !canAnimate || options.static) {
      // 빠른 모션 없이 완성 화면만 짧게 보여 준다.
      overlay.classList.add("is-static");
      schedule(() => close(false), 1600);
      return;
    }

    overlay.classList.add("is-playing");
    runTimeline(parts);
    schedule(() => close(false), T.exitStart);
  }

  function close(skipped) {
    if (!current || current.closing) return;
    const ctx = current;
    ctx.closing = true;
    ctx.timers.forEach(clearTimeout);

    const duration = skipped ? 300 : prefersReducedMotion() ? 400 : T.exitDur;
    ctx.overlay.classList.add("is-leaving");
    ctx.overlay.style.setProperty("--intro-exit", `${duration}ms`);

    // 메인 화면은 페이드아웃이 시작되면 바로 조작할 수 있게 복구한다.
    ctx.inertTargets.forEach((node) => node.removeAttribute("inert"));
    root.classList.remove("intro-active");

    window.setTimeout(() => {
      ctx.overlay.remove();
      if (current === ctx) current = null;
      if (ctx.lastFocus && typeof ctx.lastFocus.focus === "function" && document.contains(ctx.lastFocus)) {
        ctx.lastFocus.focus({ preventScroll: true });
      }
    }, duration);
  }

  function schedule(fn, delay) {
    if (!current) return;
    current.timers.push(window.setTimeout(fn, delay));
  }

  function waitForFont() {
    if (!document.fonts || typeof document.fonts.load !== "function") return Promise.resolve();
    const load = document.fonts.load('40px "Nanum Pen Script"', LINE_1 + LINE_2 + CELLS.join("")).catch(() => {});
    const timeout = new Promise((resolve) => window.setTimeout(resolve, 900));
    return Promise.race([load, timeout]);
  }

  /* ---------------- 타임라인 ---------------- */

  function runTimeline({ overlay, sheet, line1, line2, markBar, swarm }) {
    const ease = "cubic-bezier(0.22, 1, 0.36, 1)";

    // STEP 1. 원고지 테두리가 위에서 아래로 그려진다.
    sheet.animate(
      [
        { clipPath: "inset(0 0 100% 0)", opacity: 0.4 },
        { clipPath: "inset(0 0 0% 0)", opacity: 1 },
      ],
      { duration: T.sheetDur, delay: T.sheetStart, easing: "cubic-bezier(0.65, 0, 0.35, 1)", fill: "both" }
    );

    // STEP 2. 작은 글자 떼가 사방에서 원고지로 빨려 들어오고, 읽·는·힘이 차례로 안착한다.
    const box = overlay.getBoundingClientRect();
    const cells = Array.from(sheet.querySelectorAll(".intro-cell"));
    const centers = cells.map((cell) => {
      const r = cell.getBoundingClientRect();
      return { x: r.left + r.width / 2 - box.left, y: r.top + r.height / 2 - box.top };
    });

    launchSwarm(swarm, box, centers);

    cells.forEach((cell, i) => {
      const glyph = cell.querySelector(".intro-glyph");
      const land = T.glyphLand[i];
      if (!glyph || land == null) return;
      const from = edgePoint(box, i);
      const dx = from.x - centers[i].x;
      const dy = from.y - centers[i].y;
      glyph.animate(
        [
          { transform: `translate(${dx}px, ${dy}px) scale(0.35)`, filter: "blur(6px)", opacity: 0 },
          { opacity: 1, offset: 0.25 },
          { transform: "translate(0, 0) scale(1.38)", filter: "blur(0)", opacity: 1, offset: 0.72 },
          { transform: "translate(0, 0) scale(1)", filter: "blur(0)", opacity: 1 },
        ],
        { duration: T.glyphFlight, delay: land - T.glyphFlight * 0.72, easing: "cubic-bezier(0.3, 0.7, 0.2, 1)", fill: "both" }
      );
    });

    // STEP 3. 첫 번째 문구가 아래에서 올라오고, 노란 형광펜 밑줄이 왼쪽에서 오른쪽으로 그어진다.
    line1.animate(
      [
        { transform: "translateY(18px)", opacity: 0 },
        { transform: "translateY(0)", opacity: 1 },
      ],
      { duration: T.line1Dur, delay: T.line1Start, easing: ease, fill: "both" }
    );
    markBar.animate([{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }], {
      duration: T.markDur,
      delay: T.markStart,
      easing: "cubic-bezier(0.55, 0, 0.25, 1)",
      fill: "both",
    });

    // STEP 4. 두 번째 문구가 부드럽게 나타난다.
    line2.animate(
      [
        { transform: "translateY(8px)", opacity: 0 },
        { transform: "translateY(0)", opacity: 1 },
      ],
      { duration: T.line2Dur, delay: T.line2Start, easing: ease, fill: "both" }
    );
  }

  function launchSwarm(swarm, box, centers) {
    const count = box.width < 600 ? 34 : 60;
    const targets = centers.filter((_, i) => CELLS[i]);
    for (let i = 0; i < count; i += 1) {
      const span = document.createElement("span");
      span.className = "intro-bit";
      span.textContent = SWARM_CHARS[Math.floor(Math.random() * SWARM_CHARS.length)];
      span.style.fontSize = `${Math.round(15 + Math.random() * 13)}px`;
      swarm.appendChild(span);

      const from = edgePoint(box, i);
      const to = targets[i % targets.length];
      const jitter = () => (Math.random() - 0.5) * 30;
      const delay = T.swarmStart - 400 + Math.random() * (T.swarmEnd - T.swarmStart - 300);
      const duration = 520 + Math.random() * 360;

      span.animate(
        [
          { transform: `translate(${from.x}px, ${from.y}px) scale(1)`, filter: "blur(1.2px)", opacity: 0 },
          { opacity: 0.7, offset: 0.18 },
          { opacity: 0.6, offset: 0.75 },
          { transform: `translate(${to.x + jitter()}px, ${to.y + jitter()}px) scale(0.45)`, filter: "blur(0.6px)", opacity: 0 },
        ],
        { duration, delay, easing: "cubic-bezier(0.5, 0, 0.9, 0.6)", fill: "both" }
      );
    }
  }

  // 화면 가장자리(상·우·하·좌를 번갈아)의 임의 지점
  function edgePoint(box, seed) {
    const side = (seed + Math.floor(Math.random() * 4)) % 4;
    const pad = 30;
    const rx = Math.random() * box.width;
    const ry = Math.random() * box.height;
    if (side === 0) return { x: rx, y: -pad };
    if (side === 1) return { x: box.width + pad, y: ry };
    if (side === 2) return { x: rx, y: box.height + pad };
    return { x: -pad, y: ry };
  }

  /* ---------------- 연결 ---------------- */

  function mountReplayButton() {
    if (!replayEnabled()) return;
    const host = document.getElementById("topbar-actions") || document.body;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "intro-replay";
    btn.textContent = "인트로 다시 보기";
    btn.addEventListener("click", () => play());
    host.appendChild(btn);
  }

  function boot() {
    mountReplayButton();
    if (shouldAutoplay) play();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.ReadingIntro = { play, config: INTRO_CONFIG };
})();
