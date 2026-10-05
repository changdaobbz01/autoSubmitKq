"use strict";

const appBaseUrl = new URL(".", window.location.href);

const elements = {
  connectionToggle: document.querySelector("#connection-toggle"),
  connectionPanel: document.querySelector("#connection-panel"),
  connectionDot: document.querySelector("#connection-dot"),
  connectionLabel: document.querySelector("#connection-label"),
  accessKey: document.querySelector("#access-key"),
  saveAccessKey: document.querySelector("#save-access-key"),
  form: document.querySelector("#auth-form"),
  userAccount: document.querySelector("#user-account"),
  password: document.querySelector("#password"),
  savePassword: document.querySelector("#save-password"),
  togglePassword: document.querySelector("#toggle-password"),
  sendSms: document.querySelector("#send-sms"),
  verificationPanel: document.querySelector("#verification-panel"),
  smsCode: document.querySelector("#sms-code"),
  completeLogin: document.querySelector("#complete-login"),
  challengeCountdown: document.querySelector("#challenge-countdown"),
  stepKicker: document.querySelector("#step-kicker"),
  stepTwoMarker: document.querySelector("#step-two-marker"),
  inlineMessage: document.querySelector("#inline-message"),
  refreshAccounts: document.querySelector("#refresh-accounts"),
  accountsList: document.querySelector("#accounts-list"),
  toast: document.querySelector("#toast"),
  toastMessage: document.querySelector("#toast-message")
};

const state = {
  accessKey: sessionStorage.getItem("tokenHubAccessKey") || "",
  challengeId: "",
  challengeAccount: "",
  challengePassword: "",
  challengeExpiresAt: 0,
  resendAvailableAt: 0,
  timerId: 0,
  busy: false,
  toastId: 0
};

function setConnectionPanel(open) {
  elements.connectionToggle.setAttribute("aria-expanded", String(open));
  elements.connectionPanel.hidden = !open;
  if (open) {
    requestAnimationFrame(() => elements.accessKey.focus());
  }
}

function updateConnectionState() {
  const connected = Boolean(state.accessKey);
  elements.connectionDot.classList.toggle("connected", connected);
  elements.connectionLabel.textContent = connected ? "访问口令已应用" : "请先填写访问口令";
  elements.accessKey.value = state.accessKey;
}

function setButtonBusy(button, busy) {
  button.classList.toggle("loading", busy);
  button.disabled = busy;
  button.setAttribute("aria-busy", String(busy));
}

function setMessage(message, kind = "error") {
  if (!message) {
    elements.inlineMessage.hidden = true;
    elements.inlineMessage.textContent = "";
    elements.inlineMessage.classList.remove("success");
    return;
  }
  elements.inlineMessage.textContent = message;
  elements.inlineMessage.classList.toggle("success", kind === "success");
  elements.inlineMessage.hidden = false;
}

function showToast(message, kind = "success") {
  window.clearTimeout(state.toastId);
  elements.toastMessage.textContent = message;
  elements.toast.classList.toggle("error", kind === "error");
  elements.toast.querySelector(".toast-icon").textContent = kind === "error" ? "!" : "✓";
  elements.toast.hidden = false;
  state.toastId = window.setTimeout(() => {
    elements.toast.hidden = true;
  }, 3600);
}

async function api(path, options = {}) {
  if (!state.accessKey) {
    setConnectionPanel(true);
    throw new Error("请先填写服务访问口令");
  }

  let response;
  try {
    response = await fetch(new URL(path.replace(/^\/+/, ""), appBaseUrl), {
      ...options,
      headers: {
        "Content-Type": "application/json",
        "X-Mobile-Access-Key": state.accessKey,
        ...(options.headers || {})
      }
    });
  } catch (error) {
    throw new Error("暂时无法连接服务，请检查网络后重试");
  }

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json().catch(() => ({}))
    : {};

  if (!response.ok) {
    if (response.status === 401) {
      setConnectionPanel(true);
      throw new Error("服务访问口令无效，请重新填写");
    }
    throw new Error(payload.message || payload.error || `请求失败（${response.status}）`);
  }
  return payload;
}

function credentials() {
  return {
    userAccount: elements.userAccount.value.trim(),
    password: elements.password.value
  };
}

function validateCredentials() {
  const current = credentials();
  if (!current.userAccount) {
    elements.userAccount.focus();
    throw new Error("请输入门户账号");
  }
  if (!current.password) {
    elements.password.focus();
    throw new Error("请输入门户密码");
  }
  return current;
}

function clearChallenge(message = "") {
  state.challengeId = "";
  state.challengeAccount = "";
  state.challengePassword = "";
  state.challengeExpiresAt = 0;
  elements.verificationPanel.hidden = true;
  elements.smsCode.value = "";
  elements.stepKicker.textContent = "步骤 1 / 2";
  elements.stepTwoMarker.classList.remove("active");
  if (message) {
    setMessage(message);
  }
  updateTimers();
}

function activateChallenge(challenge, current) {
  state.challengeId = challenge.challengeId;
  state.challengeAccount = current.userAccount;
  state.challengePassword = current.password;
  state.challengeExpiresAt = Date.parse(challenge.expiresAt) || Date.now() + challenge.expiresInSeconds * 1000;
  state.resendAvailableAt = Date.now() + challenge.retryAfterSeconds * 1000;
  elements.verificationPanel.hidden = false;
  elements.stepKicker.textContent = "步骤 2 / 2";
  elements.stepTwoMarker.classList.add("active");
  setMessage(challenge.message || "短信验证码已发送，请注意查收。", "success");
  elements.smsCode.focus();
  startTimer();
}

function formatRemaining(milliseconds) {
  const totalSeconds = Math.max(0, Math.ceil(milliseconds / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function updateTimers() {
  const now = Date.now();
  const resendRemaining = state.resendAvailableAt - now;
  const challengeRemaining = state.challengeExpiresAt - now;
  const buttonLabel = elements.sendSms.querySelector(".button-label");

  if (resendRemaining > 0) {
    buttonLabel.textContent = `${Math.ceil(resendRemaining / 1000)} 秒后可重发`;
    elements.sendSms.disabled = true;
  } else {
    buttonLabel.textContent = state.challengeId ? "重新发送短信验证码" : "发送短信验证码";
    elements.sendSms.disabled = state.busy;
  }

  if (state.challengeId && challengeRemaining > 0) {
    elements.challengeCountdown.textContent = formatRemaining(challengeRemaining);
    elements.completeLogin.disabled = state.busy || !elements.smsCode.value.trim();
  } else if (state.challengeId) {
    clearChallenge("短信验证码已超时，请重新发送");
  } else {
    elements.completeLogin.disabled = true;
  }
}

function startTimer() {
  window.clearInterval(state.timerId);
  updateTimers();
  state.timerId = window.setInterval(updateTimers, 1000);
}

async function requestSms() {
  setMessage("");
  let current;
  try {
    current = validateCredentials();
  } catch (error) {
    setMessage(error.message);
    return;
  }

  state.busy = true;
  setButtonBusy(elements.sendSms, true);
  try {
    const challenge = await api("/api/mobile/auth/sms", {
      method: "POST",
      body: JSON.stringify(current)
    });
    activateChallenge(challenge, current);
    showToast("短信验证码已发送");
  } catch (error) {
    setMessage(error.message);
    showToast(error.message, "error");
  } finally {
    state.busy = false;
    setButtonBusy(elements.sendSms, false);
    updateTimers();
  }
}

async function completeLogin(event) {
  event.preventDefault();
  setMessage("");

  if (!state.challengeId) {
    setMessage("请先发送短信验证码");
    return;
  }

  let current;
  try {
    current = validateCredentials();
  } catch (error) {
    setMessage(error.message);
    return;
  }

  if (current.userAccount !== state.challengeAccount || current.password !== state.challengePassword) {
    clearChallenge("账号或密码已修改，请重新发送短信验证码");
    return;
  }

  const smsCode = elements.smsCode.value.trim();
  if (!smsCode) {
    elements.smsCode.focus();
    setMessage("请输入短信验证码");
    return;
  }

  state.busy = true;
  setButtonBusy(elements.completeLogin, true);
  elements.sendSms.disabled = true;
  try {
    const result = await api("/api/mobile/auth/complete", {
      method: "POST",
      body: JSON.stringify({
        challengeId: state.challengeId,
        userAccount: current.userAccount,
        password: current.password,
        smsCode,
        savePassword: elements.savePassword.checked
      })
    });
    clearChallenge();
    elements.password.value = "";
    setMessage(`${result.account.userAccount} 的考勤 Token 已更新。`, "success");
    showToast("Token 更新成功，本地程序可同步获取");
    await loadAccounts();
  } catch (error) {
    setMessage(error.message);
    showToast(error.message, "error");
  } finally {
    state.busy = false;
    setButtonBusy(elements.completeLogin, false);
    updateTimers();
  }
}

function handleCredentialChange() {
  if (!state.challengeId) {
    return;
  }
  const current = credentials();
  if (current.userAccount !== state.challengeAccount || current.password !== state.challengePassword) {
    clearChallenge("账号或密码已修改，请重新发送短信验证码");
  }
}

function initialLetter(account) {
  const normalized = (account.realName || account.userAccount || "?").trim();
  return normalized.slice(0, 1).toUpperCase();
}

function formatDate(value) {
  if (!value) {
    return "服务端未提供";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(date);
}

function renderAccounts(accounts) {
  elements.accountsList.replaceChildren();
  if (!accounts.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const symbol = document.createElement("span");
    symbol.className = "empty-symbol";
    symbol.setAttribute("aria-hidden", "true");
    symbol.textContent = "+";
    const copy = document.createElement("p");
    copy.textContent = "还没有已同步账号，完成上方短信验证后会显示在这里。";
    empty.append(symbol, copy);
    elements.accountsList.append(empty);
    return;
  }

  accounts.forEach((account, index) => {
    const item = document.createElement("article");
    item.className = "account-item";
    item.style.animationDelay = `${Math.min(index * 45, 225)}ms`;

    const avatar = document.createElement("span");
    avatar.className = "account-avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = initialLetter(account);

    const copy = document.createElement("div");
    copy.className = "account-copy";
    const nameLine = document.createElement("div");
    nameLine.className = "account-name-line";
    const name = document.createElement("strong");
    name.textContent = account.userAccount;
    const realName = document.createElement("span");
    realName.textContent = account.realName || "";
    nameLine.append(name, realName);
    const meta = document.createElement("p");
    meta.className = "account-meta";
    const passwordLabel = account.passwordSaved ? "密码已加密保存" : "未保存密码";
    meta.textContent = `${passwordLabel} · 更新于 ${formatDate(account.updatedAt)}`;
    copy.append(nameLine, meta);

    const status = document.createElement("span");
    status.className = `status-badge${account.tokenStatus === "active" ? "" : " expired"}`;
    status.textContent = account.tokenStatus === "active" ? "Token 有效" : "Token 已过期";

    item.append(avatar, copy, status);
    elements.accountsList.append(item);
  });
}

async function loadAccounts() {
  if (!state.accessKey) {
    return;
  }
  elements.refreshAccounts.classList.add("loading");
  elements.refreshAccounts.disabled = true;
  try {
    const accounts = await api("/api/mobile/accounts?limit=50");
    renderAccounts(accounts);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    elements.refreshAccounts.classList.remove("loading");
    elements.refreshAccounts.disabled = false;
  }
}

elements.connectionToggle.addEventListener("click", () => {
  setConnectionPanel(elements.connectionToggle.getAttribute("aria-expanded") !== "true");
});

elements.saveAccessKey.addEventListener("click", async () => {
  const nextKey = elements.accessKey.value.trim();
  if (!nextKey) {
    showToast("请输入服务访问口令", "error");
    return;
  }
  state.accessKey = nextKey;
  sessionStorage.setItem("tokenHubAccessKey", nextKey);
  updateConnectionState();
  setConnectionPanel(false);
  showToast("访问口令已应用");
  await loadAccounts();
});

elements.accessKey.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    elements.saveAccessKey.click();
  }
});

elements.togglePassword.addEventListener("click", () => {
  const visible = elements.password.type === "text";
  elements.password.type = visible ? "password" : "text";
  elements.togglePassword.classList.toggle("visible", !visible);
  elements.togglePassword.setAttribute("aria-label", visible ? "显示密码" : "隐藏密码");
});

elements.userAccount.addEventListener("input", handleCredentialChange);
elements.password.addEventListener("input", handleCredentialChange);
elements.smsCode.addEventListener("input", updateTimers);
elements.sendSms.addEventListener("click", requestSms);
elements.form.addEventListener("submit", completeLogin);
elements.refreshAccounts.addEventListener("click", loadAccounts);

updateConnectionState();
updateTimers();
if (state.accessKey) {
  loadAccounts();
} else {
  setConnectionPanel(true);
}
