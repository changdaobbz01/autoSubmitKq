const state = {
  requestId: "",
  config: null,
  session: null,
  accounts: null,
  polling: null,
  notify: null,
  autostart: null,
  timer: null,
  importMeta: null,
  importSummary: null,
  auth: { open: false, account: null, requestId: "" },
  run: { open: false, mode: "flow", selected: "", result: null },
  clear: { open: false },
};

const $ = (selector) => document.querySelector(selector);

const elements = {
  configApi: $("#config-api"),
  output: $("#output"),
  sessionBanner: $("#session-banner"),
  sessionSummary: $("#session-summary"),
  loginForm: $("#login-form"),
  userAccount: $("#userAccount"),
  password: $("#password"),
  verificationCode: $("#verificationCode"),
  agreePolicy: $("#agreePolicy"),
  captchaImage: $("#captcha-image"),
  btnCaptcha: $("#btn-captcha"),
  btnForceCaptcha: $("#btn-force-captcha"),
  btnLogin: $("#btn-login"),
  btnReuse: $("#btn-reuse"),
  btnLogout: $("#btn-logout"),
  btnRefreshSession: $("#btn-refresh-session"),
  accountsFile: $("#accounts-file"),
  btnImportAccounts: $("#btn-import-accounts"),
  btnRefreshAccounts: $("#btn-refresh-accounts"),
  importBanner: $("#import-banner"),
  importFileSummary: $("#import-file-summary"),
  importResultSummary: $("#import-result-summary"),
  importWarningList: $("#import-warning-list"),
  accountsSummary: $("#accounts-summary"),
  accountsTable: $("#accounts-table"),
  btnToggleAccountList: $("#btn-toggle-account-list"),
  accountsListBanner: $("#accounts-list-banner"),
  btnClearAccountTokens: $("#btn-clear-account-tokens"),
  pollingBanner: $("#polling-banner"),
  pollingSummary: $("#polling-summary"),
  pollingCurrent: $("#polling-current"),
  pollingHistory: $("#polling-history"),
  pollingExecutionModeDryRun: $("#polling-execution-mode-dry-run"),
  pollingExecutionModeSubmit: $("#polling-execution-mode-submit"),
  pollingTimeOne: $("#polling-time-1"),
  pollingTimeTwo: $("#polling-time-2"),
  pollingRandomDelayEnabled: $("#polling-random-delay-enabled"),
  btnRefreshPolling: $("#btn-refresh-polling"),
  btnStartPolling: $("#btn-start-polling"),
  btnToggleWeekendPolling: $("#btn-toggle-weekend-polling"),
  btnSavePollingMode: $("#btn-save-polling-mode"),
  btnSavePollingTimes: $("#btn-save-polling-times"),
  btnRunPollingTest: $("#btn-run-polling-test"),
  btnStopPolling: $("#btn-stop-polling"),
  autostartBanner: $("#autostart-banner"),
  autostartSummary: $("#autostart-summary"),
  autostartDetails: $("#autostart-details"),
  autostartEnabled: $("#autostart-enabled"),
  btnRefreshAutostart: $("#btn-refresh-autostart"),
  btnSaveAutostart: $("#btn-save-autostart"),
  notifyBanner: $("#notify-banner"),
  notifySummary: $("#notify-summary"),
  notifyDetails: $("#notify-details"),
  notifyWebhookUrl: $("#notify-webhook-url"),
  notifyEnabled: $("#notify-enabled"),
  notifyOnSubmit: $("#notify-on-submit"),
  notifyOnPolling: $("#notify-on-polling"),
  notifyMentionAllOnFailure: $("#notify-mention-all-on-failure"),
  btnRefreshNotify: $("#btn-refresh-notify"),
  btnSaveNotify: $("#btn-save-notify"),
  btnTestNotify: $("#btn-test-notify"),
  authModal: $("#account-auth-modal"),
  authBanner: $("#account-auth-banner"),
  authSummary: $("#account-auth-summary"),
  authUserAccount: $("#account-auth-user-account"),
  authPassword: $("#account-auth-password"),
  authCode: $("#account-auth-code"),
  authCaptchaImage: $("#account-auth-captcha-image"),
  btnAuthCaptcha: $("#btn-account-auth-captcha"),
  btnAuthRefresh: $("#btn-account-auth-refresh"),
  btnAuthSubmit: $("#btn-account-auth-submit"),
  btnAuthClose: $("#btn-account-auth-close"),
  runModal: $("#polling-run-modal"),
  runBanner: $("#polling-run-banner"),
  runModeFlow: $("#polling-run-mode-flow"),
  runModeSubmit: $("#polling-run-mode-submit"),
  runSubmitFields: $("#polling-run-submit-fields"),
  runAccount: $("#polling-run-account"),
  runPhotoStatus: $("#polling-run-photo-status"),
  runResult: $("#polling-run-result"),
  btnRunConfirm: $("#btn-polling-run-confirm"),
  btnRunCancel: $("#btn-polling-run-cancel"),
  btnRunClose: $("#btn-polling-run-close"),
  clearModal: $("#clear-tokens-modal"),
  clearBanner: $("#clear-tokens-banner"),
  clearSummary: $("#clear-tokens-summary"),
  btnClearConfirm: $("#btn-clear-tokens-confirm"),
  btnClearCancel: $("#btn-clear-tokens-cancel"),
  btnClearClose: $("#btn-clear-tokens-close"),
};

const ACCOUNTS_COLLAPSE_THRESHOLD = 1;
let accountsListInitialized = false;
let accountsListExpanded = true;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function card(label, value) {
  return `<div class="summary-item"><span class="summary-label">${escapeHtml(label)}</span><span class="summary-value">${escapeHtml(value)}</span></div>`;
}

function line(content, className = "") {
  return `<div class="detail-line ${className}">${content}</div>`;
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function getErrorMessage(error) {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  return "未知错误";
}

function setOutput(value) {
  if (!elements.output) return;
  elements.output.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function setBanner(node, tone, text) {
  if (!node) return;
  node.className = `session-banner ${tone}`;
  node.textContent = text;
}

function setLoading(button, loading, text = "处理中...") {
  if (!button) return;
  const hasImage = !!button.querySelector("img");
  if (loading) {
    if (!button.dataset.originalText) button.dataset.originalText = button.textContent || "";
    button.disabled = true;
    button.classList.add("is-loading");
    button.setAttribute("aria-busy", "true");
    if (!hasImage) button.textContent = text;
    return;
  }
  button.disabled = false;
  button.classList.remove("is-loading");
  button.removeAttribute("aria-busy");
  if (!hasImage && button.dataset.originalText) button.textContent = button.dataset.originalText;
}

function syncModalState() {
  document.body.classList.toggle("modal-open", !!(state.auth.open || state.run.open || state.clear.open));
}

function formatBytes(value) {
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(size >= 100 || index === 0 ? 0 : 1)} ${units[index]}`;
}

function buildPollingSummary(details) {
  return `账号 ${details?.totalCount || 0} 个 / 成功 ${details?.successCount || 0} / 跳过 ${details?.skippedCount || 0} / 失败 ${details?.failedCount || 0}`;
}

function getSessionStatusText(account) {
  const session = account?.session || {};
  if (session.reusable) return `可复用 / ${session.tokenExpText || "无到期时间"}`;
  if (session.status === "expired") return `token 已过期 / ${session.tokenExpText || "待重新登录"}`;
  return "无 token";
}

function getSessionStatusTone(account) {
  const session = account?.session || {};
  if (session.reusable) return "success";
  if (session.status === "expired") return "warning";
  return "muted";
}

function getPhotoStatusText(account) {
  return account?.photo?.statusText || "未配置照片";
}

function getNotifyStatusText(payload) {
  return payload?.statusText || "尚未触发";
}

function getNotifyTone(payload) {
  if (!payload) return "";
  if (payload.sent) return "detail-line-success";
  if (payload.attempted) return "detail-line-danger";
  return "";
}

function getReusableAccounts() {
  return (state.accounts?.accounts || []).filter((account) => account.enabled && account.session?.reusable);
}

function renderSession(session) {
  state.session = session;
  const reusableCount = state.accounts?.reusableCount || 0;
  const totalCount = state.accounts?.totalCount || 0;
  if (!session || !session.cached) {
    if (reusableCount > 0) {
      setBanner(elements.sessionBanner, "neutral", `当前主会话没有可复用 token，但多账号池中有 ${reusableCount} 个账号可直接参与轮询。`);
      elements.sessionSummary.innerHTML = [
        card("主会话", "当前没有可复用 token"),
        card("多账号轮询", `${reusableCount} / ${totalCount} 个账号可用`),
        card("提示", "如果只是跑轮询，不需要重新登录主会话"),
      ].join("");
    } else {
      setBanner(elements.sessionBanner, "warning", "当前没有可复用 token，需要手动登录。");
      elements.sessionSummary.innerHTML = [card("状态", "当前没有可复用 token"), card("提示", "需要手动登录并填写验证码")].join("");
    }
    return;
  }

  setBanner(
    elements.sessionBanner,
    session.reusable ? "success" : "warning",
    session.reusable ? `检测到本地可复用 token。${session.tokenExpText ? `到期：${session.tokenExpText}` : ""}` : "检测到本地缓存，但 token 已不可复用。",
  );
  elements.sessionSummary.innerHTML = [
    card("账号", session.userAccount || "-"),
    card("姓名", session.userName || "-"),
    card("部门", session.department || "-"),
    card("Token 到期", session.tokenExpText || "-"),
  ].join("");
}

function renderImport() {
  const meta = state.importMeta;
  const summary = state.importSummary;

  elements.importFileSummary.innerHTML = meta
    ? [
        card("文件名", meta.name),
        card("文件大小", formatBytes(meta.size)),
        card("最后修改", meta.lastModifiedText),
        card("文件类型", meta.type || ".xlsx"),
      ].join("")
    : "";

  elements.importResultSummary.innerHTML = summary
    ? [
        card("工作表", summary.sheetInfo?.activeSheet || "-"),
        card("数据行", summary.sourceRowCount || 0),
        card("唯一账号", summary.importedCount || 0),
        card("新增 / 合并", `${summary.createdCount || 0} / ${summary.mergedCount || 0}`),
        card("密码更新", summary.passwordChangedCount || 0),
        card("照片路径更新", summary.photoPathChangedCount || 0),
        card("照片可用 / 异常", `${summary.photoReadyCount || 0} / ${summary.photoProblemCount || 0}`),
      ].join("")
    : "";

  const warnings = [];
  if (summary?.sheetInfo?.headerRow?.length) {
    warnings.push(line(`<strong>表头</strong><br /><span>${escapeHtml(summary.sheetInfo.headerRow.join(" / "))}</span>`));
  }
  for (const item of summary?.warnings || []) warnings.push(line(escapeHtml(item), "detail-line-danger"));
  for (const item of summary?.mergedChangeDetails || []) {
    const changes = Array.isArray(item.updatedFields) ? item.updatedFields.join("、") : "";
    warnings.push(line(`<strong>合并更新</strong><br /><span>${escapeHtml(item.userAccount)} / 更新字段：${escapeHtml(changes || "-")}</span>`));
  }
  for (const item of summary?.duplicateAccountsInFile || []) {
    warnings.push(
      line(
        `<strong>重复账号</strong><br /><span>${escapeHtml(item.userAccount)} 出现在第 ${escapeHtml((item.rows || []).join("、"))} 行</span>`,
        "detail-line-danger",
      ),
    );
  }
  for (const item of summary?.photoIssues || []) {
    warnings.push(
      line(
        `<strong>照片异常</strong><br /><span>${escapeHtml(item.userAccount)} / ${escapeHtml(item.statusText || "照片不可用")} / ${escapeHtml(item.path || "-")}</span>`,
        "detail-line-danger",
      ),
    );
  }
  elements.importWarningList.innerHTML = warnings.join("");

  if (!meta && !summary) {
    setBanner(elements.importBanner, "neutral", "还没有导入表格。");
  } else if ((summary?.warnings || []).length || summary?.duplicateAccountCount || summary?.photoProblemCount) {
    setBanner(elements.importBanner, "warning", "导入完成，但检测到重复账号或照片路径异常，请确认提示信息。");
  } else if (summary) {
    setBanner(elements.importBanner, "success", `导入完成，共 ${summary.importedCount || 0} 个账号，新增 ${summary.createdCount || 0} 个。`);
  } else {
    setBanner(elements.importBanner, "neutral", "已选择文件，点击“导入账号表”开始解析。");
  }
}

function syncAccountList(registry) {
  const total = registry?.totalCount || 0;
  if (!total) {
    accountsListInitialized = false;
    accountsListExpanded = true;
    elements.btnToggleAccountList.classList.add("hidden");
    elements.accountsListBanner.classList.add("hidden");
    elements.accountsTable.classList.remove("hidden");
    return;
  }

  if (!accountsListInitialized) {
    accountsListExpanded = total <= ACCOUNTS_COLLAPSE_THRESHOLD;
    accountsListInitialized = true;
  }

  const collapsed = !accountsListExpanded;
  elements.btnToggleAccountList.classList.remove("hidden");
  elements.btnToggleAccountList.textContent = collapsed ? `查看账号列表 (${total})` : "收起账号列表";
  elements.accountsListBanner.classList.toggle("hidden", !collapsed);
  elements.accountsListBanner.textContent = collapsed ? `账号较多，已默认收起列表。当前 ${total} 个账号，点击“查看账号列表”展开。` : "";
  elements.accountsTable.classList.toggle("hidden", collapsed);
}

function renderAccounts(registry) {
  state.accounts = registry;
  if (state.session) renderSession(state.session);
  syncAccountList(registry);

  elements.accountsSummary.innerHTML = [
    card("总账号数", registry?.totalCount || 0),
    card("已启用", registry?.enabledCount || 0),
    card("可复用 token", registry?.reusableCount || 0),
    card("待验证码登录", registry?.needsCaptchaLoginCount || 0),
    card("token 已过期", registry?.expiredCount || 0),
    card("无 token", registry?.missingTokenCount || 0),
    card("照片可用", registry?.photoReadyCount || 0),
    card("照片异常", registry?.photoProblemCount || 0),
  ].join("");

  const accounts = registry?.accounts || [];
  if (!accounts.length) {
    elements.accountsTable.innerHTML = '<div class="empty-state">还没有导入账号表。</div>';
    return;
  }

  elements.accountsTable.innerHTML = accounts
    .map((account) => {
      const needsLogin = !!account.needsCaptchaLogin;
      const helper = needsLogin ? account.needsCaptchaLoginReason || "需要人工验证码登录，轮询时会自动跳过。" : "当前账号已有缓存 token，可直接参与轮询。";
      return `
        <article class="account-row ${needsLogin ? "clickable needs-token" : ""}" data-user-account="${escapeHtml(account.userAccount)}">
          <div class="account-main" data-action="${needsLogin ? "open-login" : "show-account"}">
            <div class="account-title-row">
              <strong>${escapeHtml(account.userAccount)}</strong>
              <span class="state-pill ${account.enabled ? "success" : "muted"}">${account.enabled ? "启用" : "停用"}</span>
              <span class="state-pill ${getSessionStatusTone(account)}">${escapeHtml(getSessionStatusText(account))}</span>
            </div>
            <div class="account-meta">
              <span>${escapeHtml(account.realName || "未命名")}</span>
              <span>${escapeHtml(account.department || "未配置部门")}</span>
              <span>密码：${escapeHtml(account.passwordMasked || "未提供")}</span>
            </div>
            <div class="account-status-line">${escapeHtml(helper)}</div>
            <div class="account-status-line ${account.photo?.exists ? "detail-line-success" : "detail-line-danger"}">打卡照片：${escapeHtml(getPhotoStatusText(account))}</div>
            <div class="account-status-line subtle">${account.photoPath ? `照片路径：${escapeHtml(account.photoPath)}` : "照片路径：未配置"}</div>
            <div class="account-status-line subtle">最近结果：${escapeHtml(account.lastRun?.summary || "暂无")}</div>
          </div>
          <div class="account-actions">
            <button class="primary-button" type="button" data-action="${needsLogin ? "open-login" : "show-account"}">${needsLogin ? "获取 token" : "查看状态"}</button>
            <button class="ghost-button" type="button" data-action="toggle">${account.enabled ? "停用" : "启用"}</button>
            <button class="ghost-button danger" type="button" data-action="remove">删除</button>
          </div>
        </article>
      `;
    })
    .join("");
}
function renderPolling(polling) {
  state.polling = polling;
  const overview = polling?.accountsOverview || {};
  const slots = Array.isArray(polling?.slots) ? polling.slots : [];
  const weekendStatus = polling?.allowWeekends ? "已开启" : "已关闭";
  const executionMode = polling?.executionModeLabel || "仅调测";

  setBanner(
    elements.pollingBanner,
    polling?.running ? "success" : polling?.enabled ? "neutral" : "warning",
    polling?.running
      ? `轮询执行中：${polling.activeRun?.slotLabel || "轮询任务"}`
      : polling?.enabled
        ? `轮询已开启，等待下一次${polling.allowWeekends ? "" : "工作日"}时点。`
        : "轮询当前已关闭，可以单独触发一次手动测试。",
  );

  elements.pollingSummary.innerHTML = [
    card("计划", polling?.scheduleText || "-"),
    card("执行模式", executionMode),
    card("轮询状态", polling?.running ? "执行中" : polling?.enabled ? "已开启" : "已关闭"),
    card("周末轮询", weekendStatus),
    card("随机偏移", polling?.randomDelayLabel || "关闭"),
    card("下次执行", polling?.nextRunAtText || "-"),
    card("本次可跑", `${overview.reusableCount || 0} / ${overview.enabledCount || 0}`),
    card("token 已过期", overview.expiredCount || 0),
    card("无 token", overview.missingTokenCount || 0),
    card("照片可用", overview.photoReadyCount || 0),
    card("照片异常", overview.photoProblemCount || 0),
  ].join("");

  elements.btnToggleWeekendPolling.textContent = `周末轮询：${weekendStatus}`;
  elements.pollingExecutionModeDryRun.checked = polling?.executionMode !== "submit";
  elements.pollingExecutionModeSubmit.checked = polling?.executionMode === "submit";
  elements.pollingTimeOne.value = slots[0]?.time || "";
  elements.pollingTimeTwo.value = slots[1]?.time || "";
  if (elements.pollingRandomDelayEnabled) elements.pollingRandomDelayEnabled.checked = !!polling?.randomDelayEnabled;

  const currentLines = [];
  if (polling?.activeRun) {
    currentLines.push(line(`执行中：${escapeHtml(polling.activeRun.slotLabel || "轮询任务")}`));
    currentLines.push(line(`触发方式：${escapeHtml(polling.activeRun.trigger || "schedule")}`));
    currentLines.push(line(`执行模式：${escapeHtml(polling.activeRun.executionModeLabel || executionMode)}`));
    currentLines.push(line(`开始时间：${escapeHtml(polling.activeRun.startedAtText || "-")}`));
  } else if (polling?.enabled) {
    currentLines.push(line(polling.allowWeekends ? "轮询已开启，等待下一次时点。" : "轮询已开启，等待下一次工作日时点。"));
    currentLines.push(line(`轮询模式：${escapeHtml(executionMode)}`));
  } else {
    currentLines.push(line("轮询当前已关闭，可以单独触发一次手动测试。"));
  }

  if (slots.length) currentLines.push(line(`当前时点：${escapeHtml(slots.map((slot) => slot.time).join(" / "))}`));
  currentLines.push(line(`随机偏移：${escapeHtml(polling?.randomDelayLabel || "关闭")}`));
  if ((polling?.nextRunOffsetMinutes || 0) > 0) {
    currentLines.push(
      line(
        `本次偏移：${escapeHtml(polling.nextRunOffsetMinutes)} 分钟 / 基准 ${escapeHtml(
          polling.nextRunBaseTime || "-",
        )} / 预计 ${escapeHtml(polling.nextRunScheduledTime || polling.nextRunAtText || "-")}`,
      ),
    );
  }
  if (polling?.locationProfile) {
    currentLines.push(line(`固定坐标：${escapeHtml(polling.locationProfile.longitude)} / ${escapeHtml(polling.locationProfile.latitude)}`));
    currentLines.push(line(`目标地址：${escapeHtml(polling.locationProfile.expectedAddress || "-")}`));
  }
  if (polling?.lastRun) {
    const details = polling.lastRun.details || {};
    currentLines.push(
      line(
        `最近执行：${escapeHtml(polling.lastRun.finishedAtText || polling.lastRun.startedAtText || "-")} / ${escapeHtml(
          polling.lastRun.summary || buildPollingSummary(details),
        )}`,
        polling.lastRun.ok ? "detail-line-success" : "detail-line-danger",
      ),
    );
    currentLines.push(line(`上次模式：${escapeHtml(polling.lastRun.executionModeLabel || executionMode)}`));
    currentLines.push(
      line(
        `跳过明细：token 过期 ${escapeHtml(details.skippedExpiredCount || 0)} 个，无 token ${escapeHtml(
          details.skippedMissingTokenCount || 0,
        )} 个，照片异常 ${escapeHtml(details.skippedPhotoCount || 0)} 个`,
      ),
    );
    if (polling.lastRun.notification) {
      currentLines.push(
        line(
          `企业微信通知：${escapeHtml(getNotifyStatusText(polling.lastRun.notification))}`,
          getNotifyTone(polling.lastRun.notification),
        ),
      );
    }
  }
  elements.pollingCurrent.innerHTML = currentLines.join("");

  const history = polling?.recentRuns || [];
  elements.pollingHistory.innerHTML = history.length
    ? history
        .map((item) =>
          line(
            `<strong>${escapeHtml(item.slotLabel || "轮询记录")}</strong><br /><span>${escapeHtml(
              item.trigger || "schedule",
            )} / ${escapeHtml(item.executionModeLabel || executionMode)}</span><br /><span>${escapeHtml(
              item.finishedAtText || item.startedAtText || "-",
            )}</span><br /><span>${escapeHtml(item.summary || buildPollingSummary(item.details || {}))}</span>`,
            item.ok ? "detail-line-success" : "detail-line-danger",
          ),
        )
        .join("")
    : line("暂无执行记录。");
}

function renderNotify(config) {
  state.notify = config;

  if (!config?.hasWebhook) {
    setBanner(elements.notifyBanner, "warning", "还没有配置企业微信群机器人 webhook。");
  } else if (config?.enabled) {
    setBanner(elements.notifyBanner, "success", "企业微信群通知已启用。");
  } else {
    setBanner(elements.notifyBanner, "neutral", "已保存 webhook，但当前未启用通知。");
  }

  elements.notifySummary.innerHTML = [
    card("启用状态", config?.enabled ? "已启用" : "未启用"),
    card("Webhook", config?.hasWebhook ? "已保存" : "未配置"),
    card("真实打卡通知", config?.notifyOnSubmit ? "开启" : "关闭"),
    card("轮询汇总通知", config?.notifyOnPolling ? "开启" : "关闭"),
    card("失败 @all", config?.mentionAllOnFailure ? "开启" : "关闭"),
    card("最后更新", config?.updatedAtText || "-"),
  ].join("");

  elements.notifyEnabled.checked = !!config?.enabled;
  elements.notifyOnSubmit.checked = !!config?.notifyOnSubmit;
  elements.notifyOnPolling.checked = !!config?.notifyOnPolling;
  elements.notifyMentionAllOnFailure.checked = !!config?.mentionAllOnFailure;
  elements.notifyWebhookUrl.value = "";
  elements.notifyWebhookUrl.placeholder = config?.webhookMasked
    ? `当前已保存：${config.webhookMasked}`
    : "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...";

  const rows = [];
  if (config?.webhookMasked) rows.push(line(`<strong>当前 Webhook</strong><br /><span>${escapeHtml(config.webhookMasked)}</span>`));
  if (config?.lastTest) {
    rows.push(
      line(
        `<strong>最近测试</strong><br /><span>${escapeHtml(config.lastTest.sentAtText || "-")} / ${escapeHtml(
          getNotifyStatusText(config.lastTest),
        )}</span>`,
        getNotifyTone(config.lastTest),
      ),
    );
  }
  if (config?.lastDelivery) {
    rows.push(
      line(
        `<strong>最近投递</strong><br /><span>${escapeHtml(config.lastDelivery.sentAtText || "-")} / ${escapeHtml(
          getNotifyStatusText(config.lastDelivery),
        )}</span>`,
        getNotifyTone(config.lastDelivery),
      ),
    );
  }
  elements.notifyDetails.innerHTML = rows.join("");
}

function renderAutostart(config) {
  state.autostart = config;

  if (config?.supported === false) {
    setBanner(elements.autostartBanner, "warning", config.statusText || "当前环境不支持开机自启动。");
  } else if (config?.enabled) {
    setBanner(elements.autostartBanner, "success", config.statusText || "已开启开机自启动。");
  } else {
    setBanner(elements.autostartBanner, "neutral", config?.statusText || "当前未开启开机自启动。");
  }

  elements.autostartSummary.innerHTML = [
    card("当前状态", config?.enabled ? "已开启" : "未开启"),
    card("启动方式", config?.modeText || "仅后台启动后端"),
    card("运行模式", config?.runMode === "packaged" ? "打包版" : "源码模式"),
    card("快捷启动器", config?.launcherExists ? "已就绪" : "未找到"),
  ].join("");

  elements.autostartEnabled.checked = !!config?.enabled;
  elements.autostartEnabled.disabled = config?.supported === false;

  const rows = [];
  rows.push(line("<strong>生效范围</strong><br /><span>开机自启动只对当前这台电脑生效，换到其他电脑后需要重新开启。</span>"));
  if (config?.shortcutPath) {
    rows.push(line(`<strong>启动项路径</strong><br /><span>${escapeHtml(config.shortcutPath)}</span>`));
  }
  if (config?.launcherPath) {
    rows.push(
      line(
        `<strong>后台启动脚本</strong><br /><span>${escapeHtml(config.launcherPath)}</span>`,
        config?.launcherExists ? "detail-line-success" : "detail-line-danger",
      ),
    );
  }
  if (config?.target || config?.arguments) {
    rows.push(line(`<strong>目标命令</strong><br /><span>${escapeHtml(`${config.target || ""} ${config.arguments || ""}`.trim() || "-")}</span>`));
  }
  elements.autostartDetails.innerHTML = rows.join("");
}

function renderAuthModal() {
  const open = !!(state.auth.open && state.auth.account);
  elements.authModal.classList.toggle("hidden", !open);
  elements.authModal.setAttribute("aria-hidden", String(!open));
  syncModalState();
  if (!open) return;

  const account = state.auth.account;
  elements.authUserAccount.value = account.userAccount || "";
  elements.authPassword.placeholder = account.hasPassword ? `留空则使用导入密码 ${account.passwordMasked || ""}` : "请输入密码";
  elements.authSummary.innerHTML = [
    card("账号状态", getSessionStatusText(account)),
    card("密码来源", account.hasPassword ? `已导入 / ${account.passwordMasked || ""}` : "未导入，请手动输入"),
    card("打卡照片", getPhotoStatusText(account)),
    card("部门 / 姓名", `${account.department || "-"} / ${account.realName || "-"}`),
    card("最近结果", account.lastRun?.summary || "暂无"),
  ].join("");
}

function closeAuthModal() {
  state.auth = { open: false, account: null, requestId: "" };
  elements.authPassword.value = "";
  elements.authCode.value = "";
  elements.authCaptchaImage.removeAttribute("src");
  renderAuthModal();
}

function buildFlowResultLines(status) {
  const run = status?.lastRun;
  if (!run) return [line("暂未拿到本次流程调测结果。", "detail-line-danger")];
  const details = run.details || {};
  const rows = [];
  rows.push(line(`<strong>执行结果</strong><br /><span>${escapeHtml(run.slotLabel || "手动测试")} / ${escapeHtml(run.summary || buildPollingSummary(details))}</span>`, run.ok ? "detail-line-success" : "detail-line-danger"));
  rows.push(line(`<strong>执行时间</strong><br /><span>${escapeHtml(run.finishedAtText || run.startedAtText || "-")}</span>`));
  rows.push(line(`<strong>执行模式</strong><br /><span>${escapeHtml(run.executionModeLabel || "仅调测")}</span>`));
  rows.push(
    line(
      `<strong>跳过明细</strong><br /><span>token 过期 ${escapeHtml(details.skippedExpiredCount || 0)} 个，无 token ${escapeHtml(
        details.skippedMissingTokenCount || 0,
      )} 个，照片异常 ${escapeHtml(details.skippedPhotoCount || 0)} 个</span>`,
    ),
  );
  if (run.notification) {
    rows.push(line(`<strong>企业微信</strong><br /><span>${escapeHtml(getNotifyStatusText(run.notification))}</span>`, getNotifyTone(run.notification)));
  }
  return rows;
}

function buildSubmitResultLines(result) {
  const rows = [];
  rows.push(
    line(
      `<strong>提交结果</strong><br /><span>${escapeHtml(result.userAccount || "-")} / ${escapeHtml(
        result.productionWritePerformed ? "已触发真实打卡" : "未触发真实打卡",
      )}</span>`,
      result.productionWritePerformed ? "detail-line-success" : "detail-line-danger",
    ),
  );
  if (result.photo) rows.push(line(`<strong>照片状态</strong><br /><span>${escapeHtml(result.photo.statusText || "-")}</span>`));
  if (result.notification) {
    rows.push(line(`<strong>企业微信</strong><br /><span>${escapeHtml(getNotifyStatusText(result.notification))}</span>`, getNotifyTone(result.notification)));
  }
  if (result.result?.submitResponse) {
    rows.push(
      line(
        `<strong>服务端响应</strong><br /><span>${escapeHtml(result.result.submitResponse.retCode || "-")} / ${escapeHtml(
          result.result.submitResponse.retMsg || "-",
        )}</span>`,
      ),
    );
  }
  if (result.error) {
    rows.push(line(`<strong>错误</strong><br /><span>${escapeHtml(result.error)}</span>`, "detail-line-danger"));
  }
  return rows;
}

function renderRunResult(result = state.run.result) {
  state.run.result = result;
  if (!result) {
    elements.runResult.classList.add("hidden");
    elements.runResult.innerHTML = "";
    return;
  }

  const rows = result.kind === "flow" ? buildFlowResultLines(result.status) : buildSubmitResultLines(result);
  elements.runResult.classList.remove("hidden");
  elements.runResult.innerHTML = rows.join("");
}

function renderRunModal() {
  const open = !!state.run.open;
  elements.runModal.classList.toggle("hidden", !open);
  elements.runModal.setAttribute("aria-hidden", String(!open));
  syncModalState();
  if (!open) return;

  const reusableAccounts = getReusableAccounts();
  if (!state.run.selected && reusableAccounts.length) {
    state.run.selected = reusableAccounts[0].userAccount;
  }
  if (!reusableAccounts.some((account) => account.userAccount === state.run.selected)) {
    state.run.selected = reusableAccounts[0]?.userAccount || "";
  }

  elements.runModeFlow.checked = state.run.mode === "flow";
  elements.runModeSubmit.checked = state.run.mode === "submit";
  elements.runSubmitFields.classList.toggle("hidden", state.run.mode !== "submit");
  elements.btnRunConfirm.textContent = state.run.mode === "submit" ? "开始真实打卡" : "开始流程调测";

  elements.runAccount.innerHTML = reusableAccounts.length
    ? reusableAccounts
        .map(
          (account) =>
            `<option value="${escapeHtml(account.userAccount)}" ${account.userAccount === state.run.selected ? "selected" : ""}>${escapeHtml(
              `${account.userAccount} / ${account.realName || "未命名"}`,
            )}</option>`,
        )
        .join("")
    : '<option value="">当前没有可用于真实打卡的账号</option>';

  if (state.run.mode === "flow") {
    setBanner(elements.runBanner, "neutral", "流程调测会批量执行 dry-run，不会提交真实打卡。");
    elements.runPhotoStatus.innerHTML = "";
    elements.btnRunConfirm.disabled = false;
  } else if (!reusableAccounts.length) {
    setBanner(elements.runBanner, "warning", "当前没有可复用 token 的账号，无法执行真实打卡。");
    elements.runPhotoStatus.innerHTML = line("请先为至少一个账号获取 token。", "detail-line-danger");
    elements.btnRunConfirm.disabled = true;
  } else {
    const account = reusableAccounts.find((item) => item.userAccount === state.run.selected) || reusableAccounts[0];
    state.run.selected = account.userAccount;
    setBanner(elements.runBanner, "warning", "真实打卡会调用生产提交接口，并自动使用表格中的照片路径。");
    elements.runPhotoStatus.innerHTML = [
      line(`<strong>照片状态</strong><br /><span>${escapeHtml(getPhotoStatusText(account))}</span>`, account.photo?.exists ? "detail-line-success" : "detail-line-danger"),
      line(`<strong>照片路径</strong><br /><span>${escapeHtml(account.photoPath || "未配置")}</span>`),
      line(`<strong>账号状态</strong><br /><span>${escapeHtml(getSessionStatusText(account))}</span>`),
    ].join("");
    elements.btnRunConfirm.disabled = !account.photo?.exists;
  }

  renderRunResult(state.run.result);
}

function closeRunModal() {
  state.run = { open: false, mode: "flow", selected: "", result: null };
  renderRunModal();
}

function renderClearTokensModal() {
  const open = !!state.clear.open;
  elements.clearModal.classList.toggle("hidden", !open);
  elements.clearModal.setAttribute("aria-hidden", String(!open));
  syncModalState();
  if (!open) return;

  const registry = state.accounts || {};
  elements.clearSummary.innerHTML = [
    line(
      `<strong>影响范围</strong><br /><span>共 ${escapeHtml(registry.totalCount || 0)} 个账号，其中可复用 token ${escapeHtml(
        registry.reusableCount || 0,
      )} 个，无 token ${escapeHtml(registry.missingTokenCount || 0)} 个。</span>`,
      "detail-line-danger",
    ),
    line("<strong>确认提示</strong><br /><span>这个操作会清空所有账号的本地 token 缓存，并同时清掉当前主会话。</span>"),
  ].join("");
}

function openClearTokensModal() {
  state.clear.open = true;
  renderClearTokensModal();
}

function closeClearTokensModal() {
  state.clear.open = false;
  renderClearTokensModal();
}
async function api(path, options = {}) {
  const init = { cache: "no-store", ...options };
  const headers = new Headers(init.headers || {});
  if (init.body && !(init.body instanceof FormData) && typeof init.body !== "string") {
    headers.set("Content-Type", "application/json");
    init.body = JSON.stringify(init.body);
  }
  init.headers = headers;

  const response = await fetch(path, init);
  const text = await response.text();
  let payload = {};
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { raw: text };
    }
  }
  if (!response.ok) {
    throw new Error(payload.error || payload.message || response.statusText || "请求失败");
  }
  return payload;
}

async function loadConfig({ showOutput = false } = {}) {
  const payload = await api("/api/config");
  state.config = payload;
  if (elements.configApi) elements.configApi.textContent = payload.baseApiUrl || "-";
  if (showOutput) setOutput(payload);
  return payload;
}

async function loadCaptcha({ showOutput = false } = {}) {
  setLoading(elements.btnForceCaptcha, true, "刷新中...");
  setLoading(elements.btnCaptcha, true);
  try {
    const payload = await api("/api/captcha");
    state.requestId = payload.requestId || "";
    if (payload.imageDataUrl) elements.captchaImage.src = payload.imageDataUrl;
    if (showOutput) setOutput(payload);
    return payload;
  } finally {
    setLoading(elements.btnForceCaptcha, false);
    setLoading(elements.btnCaptcha, false);
  }
}

async function loadSession({ validate = false, refreshCaptcha = true, showOutput = false } = {}) {
  const suffix = validate ? "?validate=1" : "";
  const payload = await api(`/api/session${suffix}`);
  renderSession(payload);
  if ((!payload.cached || !payload.reusable) && refreshCaptcha) {
    try {
      await loadCaptcha();
    } catch (error) {
      setBanner(elements.sessionBanner, "error", `验证码获取失败：${getErrorMessage(error)}`);
    }
  }
  if (showOutput) setOutput(payload);
  return payload;
}

async function loadAccounts({ showOutput = false } = {}) {
  const payload = await api("/api/accounts");
  renderAccounts(payload);
  if (state.auth.open && state.auth.account) {
    const updated = payload.accounts.find((item) => item.userAccount === state.auth.account.userAccount);
    if (updated) {
      state.auth.account = updated;
      renderAuthModal();
    }
  }
  if (state.run.open) renderRunModal();
  if (showOutput) setOutput(payload);
  return payload;
}

async function loadPolling({ showOutput = false } = {}) {
  const payload = await api("/api/clock-polling/status");
  renderPolling(payload);
  if (showOutput) setOutput(payload);
  return payload;
}

async function loadNotify({ showOutput = false } = {}) {
  const payload = await api("/api/notify-config");
  renderNotify(payload);
  if (showOutput) setOutput(payload);
  return payload;
}

async function loadAutostart({ showOutput = false } = {}) {
  const payload = await api("/api/autostart");
  renderAutostart(payload);
  if (showOutput) setOutput(payload);
  return payload;
}

async function loadAuthCaptcha(userAccount, { showOutput = false } = {}) {
  if (!userAccount) throw new Error("缺少账号");
  setLoading(elements.btnAuthCaptcha, true);
  setLoading(elements.btnAuthRefresh, true, "刷新中...");
  setBanner(elements.authBanner, "neutral", "正在准备验证码...");
  try {
    const payload = await api(`/api/accounts/captcha?userAccount=${encodeURIComponent(userAccount)}`);
    state.auth.requestId = payload.requestId || "";
    if (payload.imageDataUrl) elements.authCaptchaImage.src = payload.imageDataUrl;
    setBanner(elements.authBanner, "neutral", "请输入验证码后刷新该账号 token。");
    if (showOutput) setOutput(payload);
    return payload;
  } finally {
    setLoading(elements.btnAuthCaptcha, false);
    setLoading(elements.btnAuthRefresh, false);
  }
}

async function waitPollingFinished(previousStartedAt) {
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    await sleep(1500);
    const payload = await loadPolling();
    const lastStartedAt = payload?.lastRun?.startedAt || 0;
    if (!payload.running && lastStartedAt && lastStartedAt !== previousStartedAt) {
      return payload;
    }
  }
  throw new Error("等待轮询执行结果超时，请稍后手动刷新。");
}

async function login(event) {
  event.preventDefault();
  if (!elements.agreePolicy.checked) {
    setBanner(elements.sessionBanner, "warning", "请先勾选并同意《隐私政策》。");
    return;
  }

  const userAccount = elements.userAccount.value.trim();
  const password = elements.password.value.trim();
  const verificationCode = elements.verificationCode.value.trim();
  if (!userAccount || !password || !verificationCode || !state.requestId) {
    setBanner(elements.sessionBanner, "warning", "请完整填写账号、密码、验证码，并确保验证码已经加载。");
    return;
  }

  setLoading(elements.btnLogin, true, "登录中...");
  try {
    const payload = await api("/api/login", {
      method: "POST",
      body: { userAccount, password, verificationCode, requestId: state.requestId },
    });
    setOutput(payload);
    await loadSession({ refreshCaptcha: false });
    await loadAccounts();
    setBanner(elements.sessionBanner, "success", "登录成功，已刷新当前会话。");
    elements.verificationCode.value = "";
    state.requestId = "";
  } catch (error) {
    setBanner(elements.sessionBanner, "error", getErrorMessage(error));
    await loadCaptcha().catch(() => {});
  } finally {
    setLoading(elements.btnLogin, false);
  }
}

async function reuseSession() {
  setLoading(elements.btnReuse, true, "检查中...");
  try {
    const payload = await loadSession({ validate: true, refreshCaptcha: true, showOutput: true });
    if (payload.cached && payload.reusable) {
      setBanner(elements.sessionBanner, "success", "本地 token 仍然可复用。");
    }
  } catch (error) {
    setBanner(elements.sessionBanner, "error", getErrorMessage(error));
  } finally {
    setLoading(elements.btnReuse, false);
  }
}

async function logout() {
  setLoading(elements.btnLogout, true, "清理中...");
  try {
    const payload = await api("/api/logout", { method: "POST" });
    setOutput(payload);
    await loadSession({ refreshCaptcha: true });
    setBanner(elements.sessionBanner, "neutral", "当前主会话已清理。");
  } catch (error) {
    setBanner(elements.sessionBanner, "error", getErrorMessage(error));
  } finally {
    setLoading(elements.btnLogout, false);
  }
}

function updateImportMetaFromFile() {
  const file = elements.accountsFile.files?.[0];
  state.importMeta = file
    ? {
        name: file.name,
        size: file.size,
        type: file.type,
        lastModifiedText: file.lastModified ? new Date(file.lastModified).toLocaleString("zh-CN", { hour12: false }) : "-",
      }
    : null;
  renderImport();
}

async function importAccounts() {
  const file = elements.accountsFile.files?.[0];
  if (!file) {
    setBanner(elements.importBanner, "warning", "请先选择 xlsx 文件。");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  setLoading(elements.btnImportAccounts, true, "导入中...");
  try {
    const payload = await api("/api/accounts/import", { method: "POST", body: formData });
    state.importSummary = payload.importSummary || null;
    accountsListInitialized = false;
    renderImport();
    renderAccounts(payload.registry || { accounts: [] });
    await loadPolling();
    setOutput(payload);
  } catch (error) {
    setBanner(elements.importBanner, "error", getErrorMessage(error));
  } finally {
    setLoading(elements.btnImportAccounts, false);
  }
}

function findAccount(userAccount) {
  return (state.accounts?.accounts || []).find((account) => account.userAccount === userAccount) || null;
}

async function toggleAccount(userAccount, enabled) {
  const payload = await api("/api/accounts/toggle", { method: "POST", body: { userAccount, enabled } });
  renderAccounts(payload.registry);
  await loadPolling();
  setOutput(payload);
}

async function removeAccount(userAccount) {
  const ok = window.confirm(`确定删除账号 ${userAccount} 吗？`);
  if (!ok) return;
  const payload = await api("/api/accounts/remove", { method: "POST", body: { userAccount } });
  accountsListInitialized = false;
  await loadAccounts();
  await loadPolling();
  setOutput(payload);
}

async function openAuthModal(userAccount) {
  const account = findAccount(userAccount);
  if (!account) return;
  state.auth = { open: true, account, requestId: "" };
  elements.authPassword.value = "";
  elements.authCode.value = "";
  renderAuthModal();
  try {
    await loadAuthCaptcha(userAccount);
  } catch (error) {
    setBanner(elements.authBanner, "error", getErrorMessage(error));
  }
}

async function submitAccountAuth() {
  if (!state.auth.account) return;
  const verificationCode = elements.authCode.value.trim();
  if (!verificationCode || !state.auth.requestId) {
    setBanner(elements.authBanner, "warning", "请先获取验证码并填写。");
    return;
  }

  setLoading(elements.btnAuthSubmit, true, "获取中...");
  try {
    const payload = await api("/api/accounts/login", {
      method: "POST",
      body: {
        userAccount: state.auth.account.userAccount,
        password: elements.authPassword.value.trim(),
        verificationCode,
        requestId: state.auth.requestId,
      },
    });
    setOutput(payload);
    renderAccounts(payload.registry);
    await loadPolling();
    setBanner(elements.authBanner, "success", `${state.auth.account.userAccount} 的 token 已刷新。`);
    elements.authCode.value = "";
    state.auth.requestId = "";
    window.setTimeout(() => {
      closeAuthModal();
    }, 500);
  } catch (error) {
    setBanner(elements.authBanner, "error", getErrorMessage(error));
    await loadAuthCaptcha(state.auth.account.userAccount).catch(() => {});
  } finally {
    setLoading(elements.btnAuthSubmit, false);
  }
}

async function refreshAllAccounts() {
  setLoading(elements.btnRefreshAccounts, true, "刷新中...");
  try {
    const payload = await loadAccounts({ showOutput: true });
    await loadPolling();
    return payload;
  } finally {
    setLoading(elements.btnRefreshAccounts, false);
  }
}

async function startPolling() {
  setLoading(elements.btnStartPolling, true, "开启中...");
  try {
    const payload = await api("/api/clock-polling/start", { method: "POST" });
    renderPolling(payload);
    setOutput(payload);
  } catch (error) {
    setBanner(elements.pollingBanner, "error", getErrorMessage(error));
  } finally {
    setLoading(elements.btnStartPolling, false);
  }
}

async function stopPolling() {
  setLoading(elements.btnStopPolling, true, "关闭中...");
  try {
    const payload = await api("/api/clock-polling/stop", { method: "POST" });
    renderPolling(payload);
    setOutput(payload);
  } catch (error) {
    setBanner(elements.pollingBanner, "error", getErrorMessage(error));
  } finally {
    setLoading(elements.btnStopPolling, false);
  }
}

async function toggleWeekendPolling() {
  setLoading(elements.btnToggleWeekendPolling, true, "保存中...");
  try {
    const payload = await api("/api/clock-polling/weekends", {
      method: "POST",
      body: { allowWeekends: !state.polling?.allowWeekends },
    });
    renderPolling(payload);
    setOutput(payload);
  } catch (error) {
    setBanner(elements.pollingBanner, "error", getErrorMessage(error));
  } finally {
    setLoading(elements.btnToggleWeekendPolling, false);
  }
}

async function savePollingMode() {
  const executionMode = elements.pollingExecutionModeSubmit.checked ? "submit" : "dry-run";
  setLoading(elements.btnSavePollingMode, true, "保存中...");
  try {
    const payload = await api("/api/clock-polling/mode", { method: "POST", body: { executionMode } });
    renderPolling(payload);
    setOutput(payload);
  } catch (error) {
    setBanner(elements.pollingBanner, "error", getErrorMessage(error));
  } finally {
    setLoading(elements.btnSavePollingMode, false);
  }
}

async function savePollingTimes() {
  const timeOne = elements.pollingTimeOne.value;
  const timeTwo = elements.pollingTimeTwo.value;
  if (!timeOne || !timeTwo) {
    setBanner(elements.pollingBanner, "warning", "请先填写两个打卡时间。");
    return;
  }

  setLoading(elements.btnSavePollingTimes, true, "保存中...");
  try {
    const payload = await api("/api/clock-polling/times", {
      method: "POST",
      body: {
        times: [timeOne, timeTwo],
        randomDelayEnabled: !!elements.pollingRandomDelayEnabled.checked,
      },
    });
    renderPolling(payload);
    setOutput(payload);
  } catch (error) {
    setBanner(elements.pollingBanner, "error", getErrorMessage(error));
  } finally {
    setLoading(elements.btnSavePollingTimes, false);
  }
}
function openRunModal() {
  state.run = {
    open: true,
    mode: "flow",
    selected: getReusableAccounts()[0]?.userAccount || "",
    result: null,
  };
  renderRunModal();
}

async function runNow() {
  setLoading(elements.btnRunConfirm, true, "执行中...");
  try {
    if (state.run.mode === "flow") {
      const previousStartedAt = state.polling?.activeRun?.startedAt || state.polling?.lastRun?.startedAt || 0;
      const triggerPayload = await api("/api/clock-polling/test", { method: "POST" });
      renderPolling(triggerPayload);
      setBanner(elements.runBanner, "neutral", "流程调测已启动，正在等待执行完成...");
      const finalStatus = await waitPollingFinished(previousStartedAt);
      state.run.result = { kind: "flow", status: finalStatus };
      renderRunModal();
      await loadAccounts();
      await loadNotify();
      setOutput(finalStatus);
      return;
    }

    if (!state.run.selected) {
      setBanner(elements.runBanner, "warning", "请选择一个账号。");
      return;
    }

    const payload = await api("/api/clock-polling/submit", {
      method: "POST",
      body: { userAccount: state.run.selected },
    });
    state.run.result = payload;
    renderRunModal();
    await loadAccounts();
    await loadPolling();
    await loadNotify();
    setOutput(payload);
  } catch (error) {
    const message = getErrorMessage(error);
    setBanner(elements.runBanner, "error", message);
    state.run.result =
      state.run.mode === "flow"
        ? { kind: "flow", status: { lastRun: { ok: false, slotLabel: "手动测试 dry-run", summary: message, details: {}, executionModeLabel: "仅调测" } } }
        : { error: message, userAccount: state.run.selected, productionWritePerformed: false };
    renderRunModal();
  } finally {
    setLoading(elements.btnRunConfirm, false);
  }
}

async function clearAllTokens() {
  setLoading(elements.btnClearConfirm, true, "清空中...");
  try {
    const payload = await api("/api/accounts/clear-tokens", { method: "POST" });
    closeClearTokensModal();
    await loadSession({ refreshCaptcha: true });
    await loadAccounts();
    await loadPolling();
    setOutput(payload);
  } catch (error) {
    setBanner(elements.clearBanner, "error", getErrorMessage(error));
  } finally {
    setLoading(elements.btnClearConfirm, false);
  }
}

async function saveAutostart() {
  setLoading(elements.btnSaveAutostart, true, "保存中...");
  try {
    const payload = await api("/api/autostart", {
      method: "POST",
      body: {
        enabled: !!elements.autostartEnabled.checked,
      },
    });
    renderAutostart(payload);
    setOutput(payload);
  } catch (error) {
    setBanner(elements.autostartBanner, "error", getErrorMessage(error));
  } finally {
    setLoading(elements.btnSaveAutostart, false);
  }
}

async function saveNotify() {
  setLoading(elements.btnSaveNotify, true, "保存中...");
  try {
    const payload = await api("/api/notify-config", {
      method: "POST",
      body: {
        webhookUrl: elements.notifyWebhookUrl.value.trim(),
        enabled: !!elements.notifyEnabled.checked,
        notifyOnSubmit: !!elements.notifyOnSubmit.checked,
        notifyOnPolling: !!elements.notifyOnPolling.checked,
        mentionAllOnFailure: !!elements.notifyMentionAllOnFailure.checked,
      },
    });
    setOutput(payload);
    await loadNotify();
  } catch (error) {
    setBanner(elements.notifyBanner, "error", getErrorMessage(error));
  } finally {
    setLoading(elements.btnSaveNotify, false);
  }
}

async function testNotify() {
  setLoading(elements.btnTestNotify, true, "发送中...");
  try {
    const payload = await api("/api/notify-test", { method: "POST" });
    setOutput(payload);
    await loadNotify();
  } catch (error) {
    setBanner(elements.notifyBanner, "error", getErrorMessage(error));
  } finally {
    setLoading(elements.btnTestNotify, false);
  }
}

async function safeAutoRefresh() {
  try {
    await Promise.all([loadSession({ refreshCaptcha: false }), loadAccounts(), loadPolling(), loadNotify()]);
  } catch (error) {
    console.error(error);
  }
}

function handleAccountTableClick(event) {
  const actionNode = event.target.closest("[data-action]");
  if (!actionNode) return;
  const row = actionNode.closest("[data-user-account]");
  if (!row) return;
  const userAccount = row.dataset.userAccount;
  const account = findAccount(userAccount);
  if (!userAccount || !account) return;

  const action = actionNode.dataset.action;
  if (action === "show-account") {
    setOutput(account);
    return;
  }
  if (action === "open-login") {
    openAuthModal(userAccount).catch((error) => {
      setBanner(elements.importBanner, "error", getErrorMessage(error));
    });
    return;
  }
  if (action === "toggle") {
    toggleAccount(userAccount, !account.enabled).catch((error) => {
      setBanner(elements.importBanner, "error", getErrorMessage(error));
    });
    return;
  }
  if (action === "remove") {
    removeAccount(userAccount).catch((error) => {
      setBanner(elements.importBanner, "error", getErrorMessage(error));
    });
  }
}

function bind() {
  elements.loginForm.addEventListener("submit", login);
  elements.btnCaptcha.addEventListener("click", () => loadCaptcha({ showOutput: true }).catch((error) => setBanner(elements.sessionBanner, "error", getErrorMessage(error))));
  elements.btnForceCaptcha.addEventListener("click", () => loadCaptcha({ showOutput: true }).catch((error) => setBanner(elements.sessionBanner, "error", getErrorMessage(error))));
  elements.btnReuse.addEventListener("click", () => reuseSession().catch((error) => setBanner(elements.sessionBanner, "error", getErrorMessage(error))));
  elements.btnLogout.addEventListener("click", () => logout().catch((error) => setBanner(elements.sessionBanner, "error", getErrorMessage(error))));
  elements.btnRefreshSession.addEventListener("click", () => loadSession({ validate: true, refreshCaptcha: true, showOutput: true }).catch((error) => setBanner(elements.sessionBanner, "error", getErrorMessage(error))));

  elements.accountsFile.addEventListener("change", updateImportMetaFromFile);
  elements.btnImportAccounts.addEventListener("click", () => importAccounts().catch((error) => setBanner(elements.importBanner, "error", getErrorMessage(error))));
  elements.btnRefreshAccounts.addEventListener("click", () => refreshAllAccounts().catch((error) => setBanner(elements.importBanner, "error", getErrorMessage(error))));
  elements.accountsTable.addEventListener("click", handleAccountTableClick);
  elements.btnToggleAccountList.addEventListener("click", () => {
    accountsListExpanded = !accountsListExpanded;
    syncAccountList(state.accounts || { totalCount: 0 });
  });
  elements.btnClearAccountTokens.addEventListener("click", openClearTokensModal);

  elements.btnRefreshPolling.addEventListener("click", () => loadPolling({ showOutput: true }).catch((error) => setBanner(elements.pollingBanner, "error", getErrorMessage(error))));
  elements.btnStartPolling.addEventListener("click", () => startPolling().catch((error) => setBanner(elements.pollingBanner, "error", getErrorMessage(error))));
  elements.btnStopPolling.addEventListener("click", () => stopPolling().catch((error) => setBanner(elements.pollingBanner, "error", getErrorMessage(error))));
  elements.btnToggleWeekendPolling.addEventListener("click", () => toggleWeekendPolling().catch((error) => setBanner(elements.pollingBanner, "error", getErrorMessage(error))));
  elements.btnSavePollingMode.addEventListener("click", () => savePollingMode().catch((error) => setBanner(elements.pollingBanner, "error", getErrorMessage(error))));
  elements.btnSavePollingTimes.addEventListener("click", () => savePollingTimes().catch((error) => setBanner(elements.pollingBanner, "error", getErrorMessage(error))));
  elements.btnRunPollingTest.addEventListener("click", openRunModal);

  elements.btnRefreshAutostart.addEventListener("click", () => loadAutostart({ showOutput: true }).catch((error) => setBanner(elements.autostartBanner, "error", getErrorMessage(error))));
  elements.btnSaveAutostart.addEventListener("click", () => saveAutostart().catch((error) => setBanner(elements.autostartBanner, "error", getErrorMessage(error))));

  elements.btnRefreshNotify.addEventListener("click", () => loadNotify({ showOutput: true }).catch((error) => setBanner(elements.notifyBanner, "error", getErrorMessage(error))));
  elements.btnSaveNotify.addEventListener("click", () => saveNotify().catch((error) => setBanner(elements.notifyBanner, "error", getErrorMessage(error))));
  elements.btnTestNotify.addEventListener("click", () => testNotify().catch((error) => setBanner(elements.notifyBanner, "error", getErrorMessage(error))));

  elements.btnAuthClose.addEventListener("click", closeAuthModal);
  elements.btnAuthRefresh.addEventListener("click", () => {
    if (!state.auth.account) return;
    loadAuthCaptcha(state.auth.account.userAccount, { showOutput: true }).catch((error) => setBanner(elements.authBanner, "error", getErrorMessage(error)));
  });
  elements.btnAuthCaptcha.addEventListener("click", () => {
    if (!state.auth.account) return;
    loadAuthCaptcha(state.auth.account.userAccount, { showOutput: true }).catch((error) => setBanner(elements.authBanner, "error", getErrorMessage(error)));
  });
  elements.btnAuthSubmit.addEventListener("click", () => submitAccountAuth().catch((error) => setBanner(elements.authBanner, "error", getErrorMessage(error))));

  elements.runModeFlow.addEventListener("change", () => {
    state.run.mode = "flow";
    state.run.result = null;
    renderRunModal();
  });
  elements.runModeSubmit.addEventListener("change", () => {
    state.run.mode = "submit";
    state.run.result = null;
    renderRunModal();
  });
  elements.runAccount.addEventListener("change", (event) => {
    state.run.selected = event.target.value;
    state.run.result = null;
    renderRunModal();
  });
  elements.btnRunConfirm.addEventListener("click", () => runNow().catch((error) => setBanner(elements.runBanner, "error", getErrorMessage(error))));
  elements.btnRunCancel.addEventListener("click", closeRunModal);
  elements.btnRunClose.addEventListener("click", closeRunModal);

  elements.btnClearConfirm.addEventListener("click", () => clearAllTokens().catch((error) => setBanner(elements.clearBanner, "error", getErrorMessage(error))));
  elements.btnClearCancel.addEventListener("click", closeClearTokensModal);
  elements.btnClearClose.addEventListener("click", closeClearTokensModal);

  document.querySelectorAll(".modal-backdrop").forEach((node) =>
    node.addEventListener("click", (event) => {
      const action = event.currentTarget.dataset.action;
      if (action === "close-account-auth") closeAuthModal();
      if (action === "close-polling-run") closeRunModal();
      if (action === "close-clear-tokens") closeClearTokensModal();
    }),
  );

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (state.auth.open) closeAuthModal();
    if (state.run.open) closeRunModal();
    if (state.clear.open) closeClearTokensModal();
  });
}

async function boot() {
  setOutput("正在读取接口数据...");
  try {
    await loadConfig();
    await Promise.all([loadSession({ refreshCaptcha: true }), loadAccounts(), loadPolling(), loadAutostart(), loadNotify()]);
    setOutput({
      message: "前端已完成初始化。",
      loadedAt: new Date().toLocaleString("zh-CN", { hour12: false }),
      baseApiUrl: state.config?.baseApiUrl || "",
    });
  } catch (error) {
    setOutput({ error: getErrorMessage(error) });
    setBanner(elements.sessionBanner, "error", `页面初始化失败：${getErrorMessage(error)}`);
  }

  if (state.timer) window.clearInterval(state.timer);
  state.timer = window.setInterval(() => {
    safeAutoRefresh();
  }, 15000);
}

bind();
boot();
