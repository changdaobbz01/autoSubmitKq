"use strict";

const elements = {
  version: document.querySelector("#version-pill"),
  cloudUrl: document.querySelector("#cloud-url"),
  accessKey: document.querySelector("#access-key"),
  testCloud: document.querySelector("#test-cloud"),
  connectionState: document.querySelector("#connection-state"),
  form: document.querySelector("#auth-form"),
  userAccount: document.querySelector("#user-account"),
  password: document.querySelector("#password"),
  togglePassword: document.querySelector("#toggle-password"),
  sendSms: document.querySelector("#send-sms"),
  verificationPanel: document.querySelector("#verification-panel"),
  smsCode: document.querySelector("#sms-code"),
  completeLogin: document.querySelector("#complete-login"),
  countdown: document.querySelector("#countdown"),
  stepKicker: document.querySelector("#step-kicker"),
  stepTwo: document.querySelector("#step-two"),
  inlineMessage: document.querySelector("#inline-message"),
  successCard: document.querySelector("#success-card"),
  successTitle: document.querySelector("#success-title"),
  successDetail: document.querySelector("#success-detail"),
  toast: document.querySelector("#toast"),
  toastIcon: document.querySelector("#toast-icon"),
  toastMessage: document.querySelector("#toast-message")
};

const state = {
  ready: false,
  cloudReady: false,
  challengeId: "",
  challengeAccount: "",
  challengePassword: "",
  expiresAt: 0,
  resendAt: 0,
  busy: false,
  retryableUpload: false,
  timerId: 0,
  toastId: 0
};

function payload() {
  return {
    cloudBaseUrl: elements.cloudUrl.value.trim(),
    accessKey: elements.accessKey.value.trim(),
    userAccount: elements.userAccount.value.trim(),
    password: elements.password.value,
    smsCode: elements.smsCode.value.trim(),
    challengeId: state.challengeId
  };
}

async function invoke(method, data = {}) {
  if (!state.ready || !window.pywebview?.api?.[method]) {
    return { ok: false, message: "桌面服务尚未就绪，请稍候重试" };
  }
  try {
    return await window.pywebview.api[method](data);
  } catch (error) {
    return { ok: false, message: "桌面服务调用失败，请重新启动程序" };
  }
}

function setBusy(button, busy) {
  state.busy = busy;
  button.classList.toggle("loading", busy);
  button.disabled = busy;
  elements.testCloud.disabled = busy;
  elements.sendSms.disabled = busy || Date.now() < state.resendAt;
  elements.completeLogin.disabled = busy || !elements.smsCode.value.trim();
}

function setMessage(message = "", kind = "error") {
  elements.inlineMessage.hidden = !message;
  elements.inlineMessage.textContent = message;
  elements.inlineMessage.classList.toggle("success", kind === "success");
}

function showToast(message, kind = "success") {
  window.clearTimeout(state.toastId);
  elements.toastMessage.textContent = message;
  elements.toastIcon.textContent = kind === "error" ? "!" : "✓";
  elements.toast.classList.toggle("error", kind === "error");
  elements.toast.hidden = false;
  state.toastId = window.setTimeout(() => { elements.toast.hidden = true; }, 4200);
}

function setConnection(status, label) {
  elements.connectionState.classList.remove("connected", "error");
  if (status) elements.connectionState.classList.add(status);
  elements.connectionState.lastChild.textContent = label;
}

function resetCloudState() {
  state.cloudReady = false;
  setConnection("", "待检测");
}

async function clearChallenge(message = "") {
  state.challengeId = "";
  state.challengeAccount = "";
  state.challengePassword = "";
  state.expiresAt = 0;
  state.retryableUpload = false;
  elements.verificationPanel.hidden = true;
  elements.smsCode.value = "";
  elements.completeLogin.querySelector(".button-label").textContent = "验证并上传 Token";
  elements.stepKicker.textContent = "STEP 1 / 2";
  elements.stepTwo.classList.remove("active");
  if (state.ready) await invoke("cancel_challenge");
  if (message) setMessage(message);
  updateTimer();
}

function activateChallenge(result, current) {
  state.challengeId = result.challengeId;
  state.challengeAccount = current.userAccount;
  state.challengePassword = current.password;
  state.expiresAt = Number(result.expiresAt) * 1000;
  state.resendAt = Date.now() + Number(result.retryAfterSeconds || 60) * 1000;
  state.retryableUpload = false;
  elements.verificationPanel.hidden = false;
  elements.stepKicker.textContent = "STEP 2 / 2";
  elements.stepTwo.classList.add("active");
  setMessage(result.message || "短信验证码已发送，请注意查收。", "success");
  elements.smsCode.focus();
  startTimer();
}

function formatRemaining(milliseconds) {
  const seconds = Math.max(0, Math.ceil(milliseconds / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function updateTimer() {
  const now = Date.now();
  const resend = state.resendAt - now;
  const expires = state.expiresAt - now;
  const sendLabel = elements.sendSms.querySelector(".button-label");
  if (resend > 0) {
    sendLabel.textContent = `${Math.ceil(resend / 1000)} 秒后可重发`;
    elements.sendSms.disabled = true;
  } else {
    sendLabel.textContent = state.challengeId ? "重新发送短信验证码" : "发送短信验证码";
    elements.sendSms.disabled = state.busy;
  }

  if (state.challengeId && expires > 0) {
    elements.countdown.textContent = formatRemaining(expires);
    elements.completeLogin.disabled = state.busy || (!state.retryableUpload && !elements.smsCode.value.trim());
  } else if (state.challengeId) {
    clearChallenge("短信验证码已超时，请重新发送");
  } else {
    elements.completeLogin.disabled = true;
  }
}

function startTimer() {
  window.clearInterval(state.timerId);
  updateTimer();
  state.timerId = window.setInterval(updateTimer, 1000);
}

async function validateCloud(showSuccess = true) {
  const current = payload();
  if (!current.cloudBaseUrl) {
    elements.cloudUrl.focus();
    showToast("请输入云端服务地址", "error");
    return false;
  }
  if (!current.accessKey) {
    elements.accessKey.focus();
    showToast("请输入云端访问口令", "error");
    return false;
  }

  setBusy(elements.testCloud, true);
  setConnection("", "检测中");
  const result = await invoke("validate_cloud", current);
  setBusy(elements.testCloud, false);
  if (!result.ok) {
    state.cloudReady = false;
    setConnection("error", "连接失败");
    showToast(result.message, "error");
    return false;
  }
  state.cloudReady = true;
  elements.cloudUrl.value = result.cloudBaseUrl;
  setConnection("connected", "连接正常");
  if (showSuccess) showToast("云端收集服务连接正常");
  return true;
}

async function requestSms() {
  setMessage();
  elements.successCard.hidden = true;
  const current = payload();
  if (!current.userAccount) {
    elements.userAccount.focus();
    setMessage("请输入门户账号");
    return;
  }
  if (!current.password) {
    elements.password.focus();
    setMessage("请输入门户密码");
    return;
  }

  setBusy(elements.sendSms, true);
  setConnection("", "检测中");
  const result = await invoke("request_sms", current);
  setBusy(elements.sendSms, false);
  if (!result.ok) {
    if (result.message.includes("云端") || result.message.includes("访问口令")) {
      state.cloudReady = false;
      setConnection("error", "连接失败");
    }
    setMessage(result.message);
    showToast(result.message, "error");
    return;
  }
  state.cloudReady = true;
  setConnection("connected", "连接正常");
  activateChallenge(result, current);
  showToast("短信验证码已发送");
}

async function completeLogin(event) {
  event.preventDefault();
  setMessage();
  if (!state.challengeId) {
    setMessage("请先发送短信验证码");
    return;
  }

  const current = payload();
  if (current.userAccount !== state.challengeAccount || current.password !== state.challengePassword) {
    await clearChallenge("账号或密码已修改，请重新发送短信验证码");
    return;
  }
  if (!state.retryableUpload && !current.smsCode) {
    elements.smsCode.focus();
    setMessage("请输入短信验证码");
    return;
  }

  setBusy(elements.completeLogin, true);
  const result = await invoke("complete_login", current);
  setBusy(elements.completeLogin, false);
  if (!result.ok) {
    state.retryableUpload = Boolean(result.retryableUpload);
    if (state.retryableUpload) {
      elements.completeLogin.querySelector(".button-label").textContent = "重新上传到云端";
      elements.completeLogin.disabled = false;
    }
    setMessage(result.message);
    showToast(result.message, "error");
    return;
  }

  const account = result.account || {};
  state.challengeId = "";
  state.challengeAccount = "";
  state.challengePassword = "";
  state.expiresAt = 0;
  state.retryableUpload = false;
  elements.password.value = "";
  elements.smsCode.value = "";
  elements.verificationPanel.hidden = true;
  elements.stepKicker.textContent = "STEP 1 / 2";
  elements.stepTwo.classList.remove("active");
  elements.successTitle.textContent = `${account.userAccount || current.userAccount} 上传完成`;
  const name = account.realName ? ` · ${account.realName}` : "";
  elements.successDetail.textContent = `云端已生成修订版本 ${account.revision ?? "-"}${name}，本地考勤程序现在可以同步。`;
  elements.successCard.hidden = false;
  setMessage(result.message || "Token 已安全上传云端。", "success");
  showToast("Token 已上传云端");
  updateTimer();
}

function credentialChanged() {
  setMessage();
  if (!state.challengeId) return;
  const current = payload();
  if (current.userAccount !== state.challengeAccount || current.password !== state.challengePassword) {
    clearChallenge("账号或密码已修改，请重新发送短信验证码");
  }
}

elements.testCloud.addEventListener("click", () => validateCloud(true));
elements.cloudUrl.addEventListener("input", resetCloudState);
elements.accessKey.addEventListener("input", resetCloudState);
elements.accessKey.addEventListener("keydown", event => {
  if (event.key === "Enter") { event.preventDefault(); validateCloud(true); }
});
elements.togglePassword.addEventListener("click", () => {
  const hidden = elements.password.type === "password";
  elements.password.type = hidden ? "text" : "password";
  elements.togglePassword.setAttribute("aria-label", hidden ? "隐藏密码" : "显示密码");
});
elements.userAccount.addEventListener("input", credentialChanged);
elements.password.addEventListener("input", credentialChanged);
elements.smsCode.addEventListener("input", updateTimer);
elements.sendSms.addEventListener("click", requestSms);
elements.form.addEventListener("submit", completeLogin);

window.addEventListener("pywebviewready", async () => {
  state.ready = true;
  const defaults = await invoke("get_defaults");
  if (defaults.ok) {
    elements.version.textContent = `V${defaults.version}`;
    elements.cloudUrl.value = defaults.cloudBaseUrl;
  }
  startTimer();
});
