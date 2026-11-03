"use strict";

/**
 * 로그인 위젯(화면 오른쪽 위)
 * - 학생/교사 계정으로 회원가입·로그인할 수 있다. 이름 + 비밀번호(6자 이상)로 가입한다.
 * - 로그인 상태는 서버 세션 쿠키로 유지되며, 새로고침해도 /api/auth/me로 복원된다.
 */
(function () {
  const ROLE_LABEL = { student: "학생", teacher: "교사" };

  const trigger = document.getElementById("auth-trigger");
  const triggerText = document.getElementById("auth-trigger-text");
  const panel = document.getElementById("auth-panel");
  const panelGuest = document.getElementById("auth-panel-guest");
  const panelUser = document.getElementById("auth-panel-user");
  const tabs = document.querySelectorAll(".auth-tab");
  const form = document.getElementById("auth-form");
  const nameInput = document.getElementById("auth-name");
  const passwordInput = document.getElementById("auth-password");
  const submitBtn = document.getElementById("auth-submit");
  const errorEl = document.getElementById("auth-error");
  const logoutBtn = document.getElementById("auth-logout");
  const userNameEl = document.getElementById("auth-user-name");
  const userRoleEl = document.getElementById("auth-user-role");

  if (!trigger || !panel) return;

  let mode = "login"; // "login" | "signup"

  function showError(message) {
    errorEl.textContent = message;
    errorEl.classList.toggle("hidden", !message);
  }

  function setMode(nextMode) {
    mode = nextMode;
    document.getElementById("auth-level").value = mode === "signup" ? "중학" : "";
    document.querySelector("#auth-level option[value='']").disabled = mode === "signup";
    tabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.mode === mode));
    submitBtn.textContent = mode === "signup" ? "회원가입" : "로그인";
    passwordInput.autocomplete = mode === "signup" ? "new-password" : "current-password";
    showError("");
  }

  function openPanel() {
    panel.classList.remove("hidden");
    trigger.setAttribute("aria-expanded", "true");
  }

  function closePanel() {
    panel.classList.add("hidden");
    trigger.setAttribute("aria-expanded", "false");
  }

  function togglePanel() {
    if (panel.classList.contains("hidden")) openPanel();
    else closePanel();
  }

  function renderUser(user) {
    window.readingUser = user;
    if (user) {
      triggerText.textContent = `${user.name}님`;
      panelGuest.hidden = true;
      panelUser.hidden = false;
      userNameEl.textContent = user.name;
      userRoleEl.textContent = `(${ROLE_LABEL[user.role] || user.role})`;
    } else {
      triggerText.textContent = "로그인";
      panelGuest.hidden = false;
      panelUser.hidden = true;
      form.reset();
      setMode("login");
    }
    window.dispatchEvent(new CustomEvent("reading-auth", { detail: user }));
  }

  async function fetchMe() {
    try {
      const res = await fetch("/api/auth/me");
      if (!res.ok) throw new Error("auth status");
      const data = await res.json();
      renderUser(data.user || null);
    } catch (err) {
      /* 네트워크 문제여도 로그인 위젯이 화면을 막지 않도록 조용히 둔다 */
    }
  }

  trigger.addEventListener("click", togglePanel);

  document.addEventListener("click", (event) => {
    if (!panel.classList.contains("hidden") && !panel.contains(event.target) && event.target !== trigger && !trigger.contains(event.target)) {
      closePanel();
    }
  });

  tabs.forEach((tab) => tab.addEventListener("click", () => setMode(tab.dataset.mode)));

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    showError("");
    const role = (document.querySelector("input[name='auth-role']:checked") || {}).value;
    const name = nameInput.value.trim();
    const password = passwordInput.value;

    if (!name) {
      showError("이름을 입력해 주세요.");
      return;
    }
    if (password.length < 6) {
      showError("비밀번호는 6자 이상으로 입력해 주세요.");
      return;
    }

    submitBtn.disabled = true;
    try {
      const endpoint = mode === "signup" ? "/api/auth/signup" : "/api/auth/login";
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, name, password, level: document.getElementById("auth-level").value }),
      });
      const data = await res.json();
      if (!res.ok) {
        showError(data.error || "요청을 처리하지 못했어요.");
        return;
      }
      renderUser(data.user);
      closePanel();
    } catch (err) {
      showError("서버에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.");
    } finally {
      submitBtn.disabled = false;
    }
  });

  logoutBtn.addEventListener("click", async () => {
    try {
      const res = await fetch("/api/auth/logout", { method: "POST" });
      if (!res.ok) throw new Error("logout");
    } catch (err) {
      showError("로그아웃하지 못했어요. 다시 시도해 주세요.");
      return;
    }
    renderUser(null);
    closePanel();
  });

  document.querySelectorAll("input[name='auth-role']").forEach((radio) => {
    radio.addEventListener("change", () => showError(""));
  });

  setMode("login");
  fetchMe();
})();
