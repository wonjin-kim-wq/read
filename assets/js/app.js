"use strict";

/**
 * 비문학 독해 연습 앱
 * - 지문 목록을 불러와 선택하면 제한 시간과 함께 지문 읽기 화면으로 이동
 * - 지문 위에서 드래그로 범위를 선택하고 형광펜/밑줄 도구를 적용할 수 있음
 * - 제한 시간 내 객관식 문제를 풀고 채점 결과를 확인
 * - 맞힌 문제 수만큼 경험치(XP)를 얻고, 레벨이 오르면 새로운 칭호를 얻음
 */

/* ---------------- 경험치 / 레벨 / 칭호 ---------------- */

const XP_PER_CORRECT = 10;
const XP_PER_LEVEL = 50;
const LEVEL_TITLES = [
  "글자 탐험가",
  "문장 수집가",
  "의미 추적자",
  "맥락 분석가",
  "논리 해결사",
  "지식 전략가",
  "통찰의 현자",
  "사고의 지배자",
  "진리의 개척자",
  "독해의 초월자",
];
const XP_STORAGE_KEY = "readingXp";

/**
 * 누적 경험치(totalXp)를 받아 현재 레벨/칭호/진행률 정보를 계산한다.
 * 레벨 1은 0xp부터 시작하고, XP_PER_LEVEL(50xp)마다 한 레벨씩 오른다.
 * 최고 레벨(10, "독해의 초월자")에 도달하면 더 이상 레벨이 오르지 않는다.
 */
function computeLevelInfo(totalXp) {
  const maxLevel = LEVEL_TITLES.length;
  const safeXp = Math.max(0, totalXp || 0);
  const level = Math.min(maxLevel, Math.floor(safeXp / XP_PER_LEVEL) + 1);
  const title = LEVEL_TITLES[level - 1];
  const isMax = level >= maxLevel;
  const currentLevelBaseXp = (level - 1) * XP_PER_LEVEL;
  const xpIntoLevel = isMax ? XP_PER_LEVEL : safeXp - currentLevelBaseXp;
  const xpNeeded = XP_PER_LEVEL;
  const progressPercent = isMax ? 100 : Math.min(100, (xpIntoLevel / xpNeeded) * 100);
  return { level, title, totalXp: safeXp, xpIntoLevel, xpNeeded, progressPercent, isMax, maxLevel };
}

function loadTotalXp() {
  try {
    const raw = window.localStorage.getItem(XP_STORAGE_KEY);
    const n = Number(raw);
    return Number.isFinite(n) && n >= 0 ? n : 0;
  } catch (err) {
    return 0;
  }
}

function saveTotalXp(totalXp) {
  try {
    window.localStorage.setItem(XP_STORAGE_KEY, String(totalXp));
  } catch (err) {
    /* localStorage를 사용할 수 없는 환경이면 조용히 무시 */
  }
}

const state = {
  passages: [],
  current: null,      // 현재 지문 객체
  answers: {},         // { questionIndex: optionIndex }
  timerId: null,
  remainingSec: 0,
  qIndex: 0,            // 현재 보고 있는 문제 번호(한 번에 하나씩만 풀이)
  levelFilter: "all",   // 지문 선택 화면의 난이도 필터
  solving: false,       // 문제 풀기 모드 여부 (true면 지문이 가려짐)
  peeking: false,       // 문제 풀기 중 잠깐 지문을 다시 보고 있는지 여부
  savedRange: null,     // 모바일에서 도구 버튼을 누르는 순간 선택이 풀리는 것에 대비해 기억한 지문 선택 범위
  totalXp: loadTotalXp(),
};

const el = {
  screenSelect: document.getElementById("screen-select"),
  screenSolve: document.getElementById("screen-solve"),
  screenResult: document.getElementById("screen-result"),
  passageList: document.getElementById("passage-list"),
  levelFilter: document.getElementById("level-filter"),
  passageWrap: document.querySelector(".passage-wrap"),
  passageControls: document.getElementById("passage-controls"),
  btnPeekPassage: document.getElementById("btn-peek-passage"),
  passageOverlay: document.getElementById("passage-overlay"),
  panelIntro: document.getElementById("panel-intro"),
  panelQuestions: document.getElementById("panel-questions"),
  btnStartSolve: document.getElementById("btn-start-solve"),
  passageContent: document.getElementById("passage-content"),
  passageTitle: document.getElementById("passage-title"),
  questionList: document.getElementById("question-list"),
  timerDisplay: document.getElementById("timer-display"),
  btnBack: document.getElementById("btn-back"),
  btnPrev: document.getElementById("btn-prev"),
  btnNext: document.getElementById("btn-next"),
  btnSubmit: document.getElementById("btn-submit"),
  btnRetry: document.getElementById("btn-retry"),
  btnList: document.getElementById("btn-list"),
  resultSummary: document.getElementById("result-summary"),
  resultDetail: document.getElementById("result-detail"),
  toast: document.getElementById("toast"),
  toolbar: document.getElementById("mark-toolbar"),
  qProgressText: document.getElementById("q-progress-text"),
  qProgressFill: document.getElementById("q-progress-fill"),
  stepsNav: document.querySelectorAll(".steps-nav .step"),
  xpLevelBadge: document.getElementById("xp-level-badge"),
  xpTitle: document.getElementById("xp-title"),
  xpBarFill: document.getElementById("xp-bar-fill"),
  xpProgressText: document.getElementById("xp-progress-text"),
  resultXp: document.getElementById("result-xp"),
};

init();

async function init() {
  try {
    const res = await fetch("data/passages.json", { cache: "no-store" });
    state.passages = await res.json();
  } catch (err) {
    el.passageList.innerHTML =
      '<p class="list-message error">지문 데이터를 불러오지 못했어요. 페이지를 새로고침 해보세요.</p>';
    console.error(err);
    return;
  }
  renderPassageList();
  renderXpWidget();
  bindGlobalEvents();
  showScreen("select");
}

/* ---------------- 화면 전환 ---------------- */

function showScreen(name) {
  document.body.dataset.screen = name;
  el.screenSelect.classList.toggle("hidden", name !== "select");
  el.screenSolve.classList.toggle("hidden", name !== "solve");
  el.screenResult.classList.toggle("hidden", name !== "result");
  el.stepsNav.forEach((stepEl) => {
    stepEl.classList.toggle("active", stepEl.dataset.step === name);
  });
}

/* ---------------- 1) 지문 선택 ---------------- */

function renderPassageList() {
  el.passageList.innerHTML = "";
  const filtered = state.passages.filter(
    (p) => state.levelFilter === "all" || p.level === state.levelFilter
  );
  if (filtered.length === 0) {
    el.passageList.innerHTML = '<p class="list-message">해당 난이도의 지문이 아직 없어요.</p>';
    return;
  }
  filtered.forEach((p, i) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "passage-card";
    if (p.level) card.dataset.level = p.level;
    const timeLabel = formatMinSec(p.timeLimitSec);
    const levelBadge = p.level ? `<span class="badge badge-level">${escapeHtml(p.level)}</span>` : "";
    card.innerHTML = `
      <span class="card-index" aria-hidden="true">${pad2(i + 1)}</span>
      <span class="badge-row">
        <span class="badge">${escapeHtml(p.category)}</span>
        ${levelBadge}
      </span>
      <h3>${escapeHtml(p.title)}</h3>
      <p class="meta">제한 시간 ${timeLabel} · 문제 ${p.questions.length}개</p>
      <span class="card-cta" aria-hidden="true">읽기 시작 →</span>
    `;
    card.addEventListener("click", () => startPassage(p.id));
    el.passageList.appendChild(card);
  });
}

/* ---------------- 2) 풀이 화면 ---------------- */

function startPassage(id) {
  const passage = state.passages.find((p) => p.id === id);
  if (!passage) return;
  state.current = passage;
  state.answers = {};
  state.qIndex = 0;
  state.solving = false;
  state.peeking = false;

  renderPassageContent(passage);
  renderCurrentQuestion();
  el.passageTitle.textContent = passage.title;
  el.panelIntro.classList.remove("hidden");
  el.panelQuestions.classList.add("hidden");
  el.passageControls.classList.add("hidden");
  updatePassageVisibility();

  startTimer(passage.timeLimitSec);
  showScreen("solve");
}

function renderPassageContent(passage) {
  state.savedRange = null;
  el.passageContent.innerHTML = "";
  passage.paragraphs.forEach((text) => {
    const p = document.createElement("p");
    p.textContent = text;
    el.passageContent.appendChild(p);
  });
}

/**
 * 문제 풀기 시작 전에는 지문만 보여 주고(읽기 모드),
 * "문제 풀기 시작" 버튼을 누르면 문제 패널이 나타나면서 지문은 블러 처리되어 가려진다.
 * "지문 다시 보기" 버튼으로 잠깐 다시 볼 수 있지만, 다시 누르면 다시 가려진다.
 */
function enterSolvingMode() {
  state.solving = true;
  state.peeking = false;
  el.panelIntro.classList.add("hidden");
  el.panelQuestions.classList.remove("hidden");
  el.passageControls.classList.remove("hidden");
  updatePassageVisibility();
}

function togglePeekPassage() {
  if (!state.solving) return;
  state.peeking = !state.peeking;
  updatePassageVisibility();
}

function updatePassageVisibility() {
  const shouldBlur = state.solving && !state.peeking;
  el.passageContent.classList.toggle("blurred", shouldBlur);
  el.screenSolve.classList.toggle("passage-hidden", shouldBlur);
  if (shouldBlur) state.savedRange = null;
  el.passageOverlay.classList.toggle("hidden", !shouldBlur);
  if (el.btnPeekPassage) {
    el.btnPeekPassage.textContent = state.peeking ? "지문 가리기" : "지문 다시 보기";
  }
}

/**
 * 문제는 한 번에 하나씩만 보여 준다.
 * 질문을 끝까지 다 읽고 답을 고른 뒤에만 "다음 문제"로 넘어갈 수 있고,
 * 마지막 문제에서만 채점 버튼이 나타난다.
 */
function renderCurrentQuestion() {
  const passage = state.current;
  if (!passage) return;
  const total = passage.questions.length;
  const idx = state.qIndex;
  const q = passage.questions[idx];
  const isLast = idx === total - 1;

  el.questionList.innerHTML = "";
  const block = document.createElement("div");
  block.className = "question-block";
  const qText = document.createElement("p");
  qText.className = "question-text";
  qText.textContent = `${idx + 1}. ${q.question}`;
  block.appendChild(qText);

  q.options.forEach((opt, optIdx) => {
    const label = document.createElement("label");
    label.className = "option-row";
    const checked = state.answers[idx] === optIdx ? "checked" : "";
    label.innerHTML = `
      <input type="radio" name="q-${idx}" value="${optIdx}" ${checked}>
      <span>${escapeHtml(opt)}</span>
    `;
    label.querySelector("input").addEventListener("change", () => {
      state.answers[idx] = optIdx;
    });
    block.appendChild(label);
  });

  el.questionList.appendChild(block);

  el.qProgressText.textContent = `${idx + 1} / ${total}`;
  el.qProgressFill.style.width = `${((idx + 1) / total) * 100}%`;

  el.btnPrev.disabled = idx === 0;
  el.btnNext.classList.toggle("hidden", isLast);
  el.btnSubmit.classList.toggle("hidden", !isLast);
}

function goPrevQuestion() {
  if (state.qIndex <= 0) return;
  state.qIndex -= 1;
  renderCurrentQuestion();
}

function goNextQuestion() {
  const passage = state.current;
  if (!passage) return;
  if (state.answers[state.qIndex] === undefined) {
    showToast("문제를 다 읽고 답을 선택한 뒤 다음으로 넘어가세요.");
    return;
  }
  if (state.qIndex >= passage.questions.length - 1) return;
  state.qIndex += 1;
  renderCurrentQuestion();
}

/* ---------------- 타이머 ---------------- */

function startTimer(seconds) {
  clearInterval(state.timerId);
  state.remainingSec = seconds;
  updateTimerDisplay();
  state.timerId = setInterval(() => {
    state.remainingSec -= 1;
    updateTimerDisplay();
    if (state.remainingSec <= 0) {
      clearInterval(state.timerId);
      submitAnswers(true);
    }
  }, 1000);
}

function stopTimer() {
  clearInterval(state.timerId);
  state.timerId = null;
}

function updateTimerDisplay() {
  const m = Math.max(0, Math.floor(state.remainingSec / 60));
  const s = Math.max(0, state.remainingSec % 60);
  el.timerDisplay.textContent = `${pad2(m)}:${pad2(s)}`;
  el.timerDisplay.classList.toggle("warning", state.remainingSec <= 60 && state.remainingSec > 20);
  el.timerDisplay.classList.toggle("danger", state.remainingSec <= 20);
}

function pad2(n) {
  return String(n).padStart(2, "0");
}

function formatMinSec(totalSec) {
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  if (m === 0) return `${s}초`;
  if (s === 0) return `${m}분`;
  return `${m}분 ${s}초`;
}

/* ---------------- 밑줄 / 형광펜 ---------------- */

function bindGlobalEvents() {
  el.toolbar.querySelectorAll(".tool-btn").forEach((btn) => {
    // 데스크톱: 버튼을 누를 때 포커스가 옮겨 가며 지문 선택이 풀리지 않도록 한다.
    btn.addEventListener("mousedown", (e) => e.preventDefault());
    btn.addEventListener("click", () => applyTool(btn.dataset.tool));
  });

  // 모바일(iOS·Android)은 버튼을 탭하는 순간 선택이 사라지므로, 선택이 바뀔 때마다 범위를 기억해 둔다.
  document.addEventListener("selectionchange", rememberPassageSelection);
  el.passageContent.addEventListener("pointerdown", () => {
    state.savedRange = null;
  });

  el.levelFilter.querySelectorAll(".level-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.levelFilter = btn.dataset.level;
      el.levelFilter.querySelectorAll(".level-btn").forEach((b) => {
        b.classList.toggle("active", b === btn);
      });
      renderPassageList();
    });
  });

  el.btnStartSolve.addEventListener("click", enterSolvingMode);
  el.btnPeekPassage.addEventListener("click", togglePeekPassage);

  el.btnBack.addEventListener("click", () => {
    stopTimer();
    showScreen("select");
  });

  el.btnPrev.addEventListener("click", goPrevQuestion);
  el.btnNext.addEventListener("click", goNextQuestion);
  el.btnSubmit.addEventListener("click", () => submitAnswers(false));

  el.btnRetry.addEventListener("click", () => {
    if (state.current) startPassage(state.current.id);
  });

  el.btnList.addEventListener("click", () => {
    stopTimer();
    showScreen("select");
  });
}

function rememberPassageSelection() {
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return;
  const range = clipRangeToPassage(selection.getRangeAt(0));
  if (range) state.savedRange = range;
}

/**
 * 선택 범위 중 지문 안에 들어간 부분만 잘라 돌려준다.
 * 모바일에서는 선택 핸들이 제목 등 지문 밖까지 쉽게 넘어가므로, 겹치는 부분만 표시한다.
 */
function clipRangeToPassage(range) {
  const root = el.passageContent;
  if (!range.intersectsNode(root)) return null;
  const clipped = range.cloneRange();
  if (!root.contains(range.startContainer)) clipped.setStart(root, 0);
  if (!root.contains(range.endContainer)) clipped.setEnd(root, root.childNodes.length);
  return clipped.collapsed ? null : clipped;
}

function getPassageRange() {
  const selection = window.getSelection();
  const hasLiveSelection = selection && selection.rangeCount > 0 && !selection.isCollapsed;
  if (hasLiveSelection) {
    const range = clipRangeToPassage(selection.getRangeAt(0));
    if (range) return { range };
  }
  if (state.savedRange && !state.savedRange.collapsed && el.passageContent.contains(state.savedRange.commonAncestorContainer)) {
    return { range: state.savedRange };
  }
  return { range: null, outside: hasLiveSelection };
}

function applyTool(tool) {
  if (state.solving && !state.peeking) {
    showToast("지문이 가려져 있어요. '지문 다시 보기'를 누른 뒤 표시하세요.");
    return;
  }
  const { range, outside } = getPassageRange();
  if (!range) {
    showToast(outside ? "지문 영역 안에서만 표시할 수 있어요." : "먼저 지문에서 표시할 범위를 선택하세요.");
    return;
  }

  if (tool === "erase") {
    eraseInRange(range);
  } else {
    const className =
      tool === "highlight-yellow" ? "hl-yellow" : tool === "highlight-green" ? "hl-green" : "hl-underline";
    markRange(range, className);
  }
  state.savedRange = null;
  const selection = window.getSelection();
  if (selection) selection.removeAllRanges();
}

function markRange(range, className) {
  const textNodes = collectIntersectingTextNodes(range);
  textNodes.forEach(({ node, start, end }) => {
    wrapTextNode(node, start, end, className);
  });
}

function collectIntersectingTextNodes(range) {
  const walker = document.createTreeWalker(el.passageContent, NodeFilter.SHOW_TEXT, null);
  const results = [];
  let node;
  while ((node = walker.nextNode())) {
    if (!node.textContent || !range.intersectsNode(node)) continue;
    const start = node === range.startContainer ? range.startOffset : 0;
    const end = node === range.endContainer ? range.endOffset : node.textContent.length;
    if (end > start) results.push({ node, start, end });
  }
  return results;
}

function wrapTextNode(textNode, start, end, className) {
  let middle = textNode;
  if (end < middle.textContent.length) {
    middle.splitText(end);
  }
  if (start > 0) {
    middle = middle.splitText(start);
  }
  const mark = document.createElement("mark");
  mark.className = className;
  middle.parentNode.insertBefore(mark, middle);
  mark.appendChild(middle);
}

function eraseInRange(range) {
  const marks = Array.from(el.passageContent.querySelectorAll("mark"));
  marks.forEach((mark) => {
    if (range.intersectsNode(mark)) {
      unwrapMark(mark);
    }
  });
  el.passageContent.normalize();
}

function unwrapMark(mark) {
  const parent = mark.parentNode;
  while (mark.firstChild) {
    parent.insertBefore(mark.firstChild, mark);
  }
  parent.removeChild(mark);
}

/* ---------------- 채점 ---------------- */

function submitAnswers(isTimeout) {
  const passage = state.current;
  if (!passage) return;
  if (!isTimeout && state.answers[state.qIndex] === undefined) {
    showToast("마지막 문제의 답을 선택한 뒤 채점할 수 있어요.");
    return;
  }
  stopTimer();

  let correctCount = 0;
  const details = passage.questions.map((q, idx) => {
    const chosen = state.answers[idx];
    const isCorrect = chosen === q.answerIndex;
    if (isCorrect) correctCount += 1;
    return {
      question: q.question,
      chosenText: chosen === undefined ? "선택하지 않음" : q.options[chosen],
      correctText: q.options[q.answerIndex],
      isCorrect,
      explanation: q.explanation,
    };
  });

  renderResult(passage, correctCount, details, isTimeout);
  showScreen("result");
}

/**
 * 맞힌 문제 수(correctCount)만큼 경험치를 지급하고, 레벨업 여부를 계산해
 * 결과 화면에 표시할 수 있는 정보를 돌려준다. 동시에 헤더의 경험치 위젯도 갱신한다.
 */
function awardXp(correctCount) {
  const xpGained = correctCount * XP_PER_CORRECT;
  const before = computeLevelInfo(state.totalXp);
  state.totalXp += xpGained;
  saveTotalXp(state.totalXp);
  const after = computeLevelInfo(state.totalXp);
  renderXpWidget();
  return { xpGained, before, after, leveledUp: after.level > before.level };
}

function renderXpWidget() {
  const info = computeLevelInfo(state.totalXp);
  if (el.xpLevelBadge) el.xpLevelBadge.textContent = `Lv.${info.level}`;
  if (el.xpTitle) el.xpTitle.textContent = info.title;
  if (el.xpBarFill) el.xpBarFill.style.width = `${info.progressPercent}%`;
  if (el.xpProgressText) {
    el.xpProgressText.textContent = info.isMax
      ? `MAX · ${info.totalXp} XP`
      : `${info.xpIntoLevel} / ${info.xpNeeded} XP`;
  }
}

function renderResult(passage, correctCount, details, isTimeout) {
  const total = passage.questions.length;
  const xpResult = awardXp(correctCount);
  el.resultSummary.innerHTML = `
    <div class="result-score">${correctCount} / ${total}</div>
    <div>
      <p class="result-time ${isTimeout ? "timeout" : ""}">
        ${isTimeout ? "시간 종료로 자동 제출되었어요." : "시간 안에 제출을 완료했어요."}
      </p>
      <p class="result-passage">${escapeHtml(passage.title)}</p>
    </div>
  `;

  renderResultXp(xpResult);

  el.resultDetail.innerHTML = "";
  details.forEach((d, idx) => {
    const item = document.createElement("div");
    item.className = `result-item ${d.isCorrect ? "correct" : "wrong"}`;
    item.innerHTML = `
      <p class="q">${idx + 1}. ${escapeHtml(d.question)} ${d.isCorrect ? "✅" : "❌"}</p>
      <p class="a">내가 고른 답: ${escapeHtml(d.chosenText)}</p>
      ${d.isCorrect ? "" : `<p class="a">정답: ${escapeHtml(d.correctText)}</p>`}
      <p class="explain">${escapeHtml(d.explanation)}</p>
    `;
    el.resultDetail.appendChild(item);
  });
}

function renderResultXp(xpResult) {
  if (!el.resultXp) return;
  const { xpGained, after, leveledUp } = xpResult;
  const levelUpHtml = leveledUp
    ? `<p class="result-xp-levelup">🎉 레벨 업! Lv.${after.level} &ldquo;${escapeHtml(after.title)}&rdquo; 칭호를 얻었어요!</p>`
    : "";
  const progressHtml = after.isMax
    ? `<span class="xp-progress-text">최고 레벨 달성 · 누적 ${after.totalXp} XP</span>`
    : `<span class="xp-progress-text">${after.xpIntoLevel} / ${after.xpNeeded} XP</span>`;
  el.resultXp.innerHTML = `
    <p class="result-xp-gain">맞힌 문제 ${xpGained / XP_PER_CORRECT}개 × ${XP_PER_CORRECT}XP = 경험치 +${xpGained} 획득!</p>
    ${levelUpHtml}
    <div>
      <span class="xp-title">Lv.${after.level} ${escapeHtml(after.title)}</span>
      <div class="xp-bar"><div class="xp-bar-fill" style="width:${after.progressPercent}%"></div></div>
      ${progressHtml}
    </div>
  `;
}

/* ---------------- 유틸 ---------------- */

function showToast(message) {
  el.toast.textContent = message;
  el.toast.classList.remove("hidden");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => el.toast.classList.add("hidden"), 2200);
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
