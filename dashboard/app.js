const $ = (id) => document.getElementById(id);
function initializeMenuDensity() {
  const button = $("menuDensityToggle");
  if (!button) return;
  const apply = (wide) => {
    document.documentElement.classList.toggle("menu-wide", wide);
    button.setAttribute("aria-pressed", String(wide));
    button.setAttribute("aria-label", wide ? "Use thin menu" : "Use wide menu");
    button.title = wide ? "Use thin menu" : "Use wide menu";
    button.textContent = wide ? "⇤" : "☰";
  };
  let wide = localStorage.getItem("leadfinder.menuDensity") === "wide";
  apply(wide);
  button.addEventListener("click", () => {
    wide = !wide;
    localStorage.setItem("leadfinder.menuDensity", wide ? "wide" : "thin");
    apply(wide);
  });
}
initializeMenuDensity();
function initializeDesktopShell() {
  const desktop = window.leadFinderWindow;
  if (!desktop) return;
  document.documentElement.classList.add("electron-app");
  const actions = {
    windowBack: "back",
    windowForward: "forward",
    windowReload: "reload",
    windowMinimize: "minimize",
    windowMaximize: "maximize",
    windowClose: "close",
  };
  for (const [id, action] of Object.entries(actions)) {
    $(id).addEventListener("click", () => desktop.action(action));
  }
  desktop.onNavigation((state) => {
    $("windowBack").disabled = !state.canGoBack;
    $("windowForward").disabled = !state.canGoForward;
    $("windowMaximize").textContent = state.maximized ? "❐" : "□";
    $("windowMaximize").title = state.maximized ? "Restore" : "Maximize";
  });
}
initializeDesktopShell();
function renderMaintenance(state = {}) {
  if (!$("maintenanceStatus")) return;
  $("maintenanceStatus").textContent =
    state.message || "Ready to check GitHub releases.";
  const busy = ["checking", "downloading", "repairing"].includes(state.status);
  $("checkUpdates").disabled = busy;
  $("repairRuntime").disabled = busy;
  $("downloadUpdate").classList.toggle(
    "hidden",
    !state.updateAvailable || state.downloaded,
  );
  $("installUpdate").classList.toggle("hidden", !state.downloaded);
  const showProgress = ["downloading", "repairing"].includes(state.status);
  $("maintenanceProgress").classList.toggle("hidden", !showProgress);
  $("maintenanceProgress").value = Number(state.progress || 0);
}
async function loadMaintenance() {
  const desktop = window.leadFinderWindow;
  if (!desktop?.maintenanceStatus) {
    for (const id of ["checkUpdates", "repairRuntime"]) $(id).disabled = true;
    return;
  }
  renderMaintenance(await desktop.maintenanceStatus());
  desktop.onMaintenance(renderMaintenance);
}
let connectionPollTimer = null;
function connectionBadge(item) {
  if (item.connected && item.enabled) return "connected · enabled";
  if (item.connected) return "connected";
  if (item.configured) return "saved · test needed";
  return "not connected";
}
function connectionCard(item) {
  const status = connectionBadge(item);
  if (item.id === "google_sheets") {
    return `<article class="connection-card ${item.connected ? "is-connected" : ""}" data-provider="${item.id}">
      <h3>${escapeHtml(item.name)}</h3><span class="badge">${escapeHtml(status)}</span>
      <p>${escapeHtml(item.description)}</p><small>${escapeHtml(item.auth)}${item.secret_hint ? ` · ${escapeHtml(item.secret_hint)}` : ""}</small>
      <form data-connection-form="google_sheets">
        <label>Desktop OAuth client ID<input name="client_id" type="password" autocomplete="off" placeholder="Paste Google OAuth client ID" required></label>
        <label>Desktop OAuth client secret<input name="client_secret" type="password" autocomplete="off" placeholder="Paste Google OAuth client secret" required></label>
        <div class="button-row"><button class="secondary" type="submit">Save OAuth client</button>
        <button class="primary" type="button" data-connection-action="google-connect" ${item.configured ? "" : "disabled"}>Connect Google</button>
        <button class="secondary" type="button" data-connection-action="sheet-sync" ${item.connected ? "" : "disabled"}>Sync research library</button>
        <button class="ghost" type="button" data-connection-action="disconnect">Disconnect</button></div>
      </form>
      <p class="fine-print">Enable the Google Sheets API, then use a Google Cloud <b>Desktop app</b> OAuth client. Access is limited to files this app creates or opens. ${item.spreadsheet_id ? "A research spreadsheet is linked." : ""}</p>
    </article>`;
  }
  const automaticNote = item.automatic
    ? "Can join the All sources waterfall after verification and explicit enabling."
    : "Connection is saved now; provider-specific data calls remain explicit while Phase 2 adapters are added.";
  return `<article class="connection-card ${item.connected ? "is-connected" : ""}" data-provider="${item.id}">
    <h3>${escapeHtml(item.name)}</h3><span class="badge">${escapeHtml(status)}</span>
    <p>${escapeHtml(item.description)}</p><small>${escapeHtml(item.auth)}${item.secret_hint ? ` · ${escapeHtml(item.secret_hint)}` : ""}</small>
    <form data-connection-form="${item.id}"><label>API key or token<input name="api_key" type="password" autocomplete="off" placeholder="Paste credential" required></label>
      <div class="button-row"><button class="secondary" type="submit">Save credential</button><button class="secondary" type="button" data-connection-action="test" ${item.configured ? "" : "disabled"}>Test connection</button><button class="ghost" type="button" data-connection-action="disconnect">Disconnect</button></div>
      <label class="provider-enable"><input type="checkbox" data-connection-action="enabled" ${item.enabled ? "checked" : ""} ${item.connected && item.automatic ? "" : "disabled"}>Use in automatic waterfall</label>
    </form><p class="fine-print">${escapeHtml(automaticNote)}${item.message ? ` ${escapeHtml(item.message)}` : ""}</p>
  </article>`;
}
async function loadConnections() {
  if (!$("connectionCards")) return;
  try {
    const [data, catalog] = await Promise.all([
      api("/api/connections"),
      api("/api/connections/catalog"),
    ]);
    const connected = data.providers.filter((item) => item.connected).length;
    $("connectionSummary").textContent =
      `${connected} of ${data.providers.length} connected`;
    $("connectionCards").innerHTML = data.providers
      .map(connectionCard)
      .join("");
    $("sourceCatalog").innerHTML = catalog.sources
      .map(
        (item) =>
          `<div class="source-card"><h3>${escapeHtml(item.name)}</h3><span class="badge">${escapeHtml(item.status)}</span><p><b>${escapeHtml(item.country)}</b> · ${escapeHtml(item.access_class)}</p><p>${escapeHtml(item.connector_type.replaceAll("_", " "))} · ${escapeHtml(item.niches)}</p></div>`,
      )
      .join("");
    $("connectionStatus").textContent =
      `Credentials are stored in ${data.secrets_storage}; secret values are never returned to this page.`;
  } catch (err) {
    $("connectionStatus").textContent =
      `Connections unavailable: ${err.message}`;
  }
}
async function connectionPost(path, body) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
function pollGoogleConnection(popup) {
  clearInterval(connectionPollTimer);
  let attempts = 0;
  connectionPollTimer = setInterval(async () => {
    attempts += 1;
    try {
      const data = await api("/api/connections");
      const google = data.providers.find((item) => item.id === "google_sheets");
      if (google?.connected || popup?.closed || attempts > 120) {
        clearInterval(connectionPollTimer);
        connectionPollTimer = null;
        await loadConnections();
        if (google?.connected) toast("Google Sheets connected.");
      }
    } catch {}
  }, 1000);
}
const escapeHtml = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const safeUrl = (value) => {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
};
const link = (value, label) => {
  const url = safeUrl(value);
  return url
    ? `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(label || value)}</a>`
    : "—";
};
let job = null,
  jobId = localStorage.getItem("leadfinder.lastJob"),
  pollTimer = null,
  rows = [],
  visible = [],
  historyJobs = [],
  library = null,
  intelligenceOverview = null,
  intelligenceQueue = [],
  nichePacks = [],
  selectedReferences = new Set(),
  preparedReferenceIds = [];
let outreachTemplates = [],
  outreachCampaigns = [],
  outreachPollTimer = null,
  outreachTab = "campaigns",
  selectedCampaignId = null,
  selectedTemplateIds = new Set(),
  editingTemplateId = null,
  openCampaignPreviews = new Set(),
  campaignJob = null,
  campaignJobsLoaded = false,
  zohoConnected = false;
let verificationTask = null,
  verificationPollTimer = null;
let workflowTask = null,
  workflowPollTimer = null,
  workflowId = localStorage.getItem("leadfinder.workflowTask");
const openHistoryGroups = new Set();
const historyPreviewCache = new Map();
const historyPreviewPending = new Map();
let historyRevision = 0;
let aiConnection = null,
  aiBusy = false,
  aiBatchState = null,
  aiBatchPolling = false,
  aiProposal = null,
  aiTeachingNiche = "",
  aiTeachingTimer = null,
  detailContext = null;
const aiReviewMessages = new Map();
const active = (s) => ["queued", "running", "waiting"].includes(s);
async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw Error(data.error || "Request failed");
  return data;
}
function aiReady() {
  return Boolean(aiConnection?.available && $("aiModel").value);
}
function syncAiControls() {
  $("aiModel").disabled = aiBusy || !aiConnection?.models?.length;
  $("aiRefresh").disabled = aiBusy;
  $("aiPlanButton").disabled = aiBusy || !aiReady();
  const review = $("aiReviewButton");
  if (review)
    review.disabled =
      aiBusy ||
      !aiReady() ||
      !job ||
      active(job.status) ||
      !detailContext ||
      detailContext.rowIndex < 0;
  const compiler = $("aiCompileButton");
  if (compiler) compiler.disabled = !review || review.disabled;
  if ($("aiBatchCompile"))
    $("aiBatchCompile").disabled =
      aiBatchPolling || !aiReady() || !job || active(job.status);
  const use = $("aiUsePhrases");
  if (use)
    use.disabled =
      !aiProposal ||
      aiProposal.niche !== $("niche").value.trim() ||
      aiProposal.location !== $("location").value.trim();
}
async function loadAiStatus() {
  $("aiRefresh").disabled = true;
  $("aiStatus").textContent = "Checking your installed local models…";
  try {
    const status = await aiApi("/api/ai/status");
    const models = Array.isArray(status.models) ? status.models : [];
    aiConnection = { ...status, models };
    const previous =
      $("aiModel").value || localStorage.getItem("leadfinder.aiModel");
    $("aiModel").innerHTML = models.length
      ? models
          .map((model) => {
            const name = typeof model === "string" ? model : model.name;
            const size = model.parameter_size
              ? ` · ${model.parameter_size}`
              : "";
            return `<option value="${escapeHtml(name)}">${escapeHtml(name + size)}</option>`;
          })
          .join("")
      : '<option value="">No model available</option>';
    const names = models.map((m) => (typeof m === "string" ? m : m.name));
    if (names.includes(previous)) $("aiModel").value = previous;
    else if (names.includes(status.default_model))
      $("aiModel").value = status.default_model;
    $("aiStatus").textContent =
      status.message ||
      (status.available && models.length
        ? "Your local model is available. It runs only when you ask."
        : "Local AI is offline. Start your local model service, then check the connection. Scraping still works.");
    syncCampaignModels();
    syncAiChip();
  } catch (err) {
    aiConnection = null;
    $("aiModel").innerHTML = '<option value="">Local AI unavailable</option>';
    $("aiStatus").textContent =
      "Local AI is unavailable: " +
      err.message +
      ". Scraping still works: search and verification remain available, but AI phrase expansion and evidence interpretation are unavailable, so niche coverage may be less precise.";
    syncCampaignModels();
    syncAiChip();
  } finally {
    syncAiControls();
  }
}
async function loadAiTeaching() {
  const niche = $("niche").value.trim();
  if (niche.length < 2) {
    aiTeachingNiche = "";
    $("aiTeachTerms").value = "";
    $("aiTeachAvoid").value = "";
    $("aiTeachNotes").value = "";
    $("aiTeachStatus").textContent =
      "Enter a service to load or add teaching examples.";
    return;
  }
  const requested = niche;
  aiTeachingNiche = requested;
  try {
    const data = await aiApi(
      "/api/intelligence/ai-teaching?niche=" + encodeURIComponent(requested),
    );
    if (aiTeachingNiche !== requested || $("niche").value.trim() !== requested)
      return;
    $("aiTeachTerms").value = (data.terms || []).join("\n");
    $("aiTeachAvoid").value = (data.avoid || []).join("\n");
    $("aiTeachNotes").value = data.notes || "";
    const curated = (data.curated_terms || []).length;
    $("aiTeachStatus").textContent =
      `${(data.terms || []).length} saved phrase${(data.terms || []).length === 1 ? "" : "s"} · ${curated} curated example${curated === 1 ? "" : "s"}${data.updated_at ? ` · updated ${String(data.updated_at).slice(0, 10)}` : ""}`;
  } catch (err) {
    if (aiTeachingNiche === requested)
      $("aiTeachStatus").textContent =
        "Teaching memory is unavailable: " + err.message;
  }
}
function listLines(value) {
  return String(value || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}
function syncAiTeachFields() {
  const niche = $("niche").value.trim();
  if (niche !== aiTeachingNiche) {
    clearTimeout(aiTeachingTimer);
    aiTeachingTimer = setTimeout(loadAiTeaching, 450);
  }
}
async function saveAiTeaching() {
  const niche = $("niche").value.trim();
  if (niche.length < 2) {
    $("aiTeachStatus").textContent = "Enter a service first.";
    return;
  }
  const button = $("aiTeachSave");
  button.disabled = true;
  $("aiTeachStatus").textContent = "Saving teaching memory…";
  try {
    const data = await api("/api/intelligence/ai-teaching", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        niche,
        terms: listLines($("aiTeachTerms").value),
        avoid: listLines($("aiTeachAvoid").value),
        notes: $("aiTeachNotes").value,
      }),
    });
    aiTeachingNiche = niche;
    $("aiTeachStatus").textContent =
      `Saved. Future phrase and intelligence prompts for ${data.niche} will use this guidance.`;
  } catch (err) {
    $("aiTeachStatus").textContent = err.message;
  } finally {
    button.disabled = false;
  }
}
function syncCampaignModels() {
  const select = $("campaignAiModel");
  if (!select) return;
  const models = (aiConnection?.models || []).map((model) =>
    typeof model === "string" ? { name: model } : model,
  );
  const names = models.map((model) => model.name);
  const previous = select.value || localStorage.getItem("leadfinder.aiModel");
  select.innerHTML = models.length
    ? models
        .map(
          (model) =>
            `<option value="${escapeHtml(model.name)}">${escapeHtml(model.name + (model.parameter_size ? ` · ${model.parameter_size}` : ""))}</option>`,
        )
        .join("")
    : '<option value="">Local AI unavailable</option>';
  if (names.includes(previous)) select.value = previous;
  else if (names.includes(aiConnection?.default_model))
    select.value = aiConnection.default_model;
  select.disabled = !models.length;
  syncCampaignPrepare();
}
function aiMessage(id, message, isError = false) {
  const element = $(id);
  if (!element) return;
  element.textContent = message;
  element.classList.toggle("is-error", isError);
}
async function aiApi(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  try {
    return await api(path, { ...options, signal: controller.signal });
  } catch (err) {
    if (err.name === "AbortError")
      throw Error(
        "The local AI service is not responding. Check its connection and try again.",
      );
    throw err;
  } finally {
    clearTimeout(timeout);
  }
}
async function runAiTask(body, onProgress) {
  const task = await aiApi("/api/ai/assist", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!task.id) throw Error("The AI service did not return a task ID.");
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline) {
    const state = await aiApi("/api/ai/tasks/" + encodeURIComponent(task.id));
    onProgress(state.message || `Local AI ${state.status || "working"}…`);
    if (state.status === "complete") return state.result || {};
    if (["failed", "cancelled"].includes(state.status))
      throw Error(state.error || state.message || "The local AI task failed.");
    await new Promise((resolve) => setTimeout(resolve, 1100));
  }
  throw Error(
    "The local model is taking longer than two minutes. It may finish in the background. Your search data is unchanged; reopen the lead later to check for a saved review.",
  );
}

function batchScopeCount() {
  if (!job) return 0;
  const scope = $("aiBatchScope").value;
  if (scope === "all") return rows.length;
  return rows.filter(
    (row) =>
      parseObject(row.verification).status === "complete" &&
      (scope !== "qualified" || row.match_status !== "candidate"),
  ).length;
}
function renderAiBatch(state = aiBatchState) {
  const count = batchScopeCount();
  $("aiBatchCompile").textContent =
    $("aiBatchScope").value === "all"
      ? `Compile all ${count} leads`
      : $("aiBatchScope").value === "qualified"
        ? `Compile ${count} qualified leads`
        : `Compile ${count} verified leads`;
  $("aiBatchProgress").value = Number(state?.progress || 0);
  if (state) {
    $("aiBatchStatus").textContent =
      state.message ||
      `${state.status || "working"} · ${state.completed || 0}/${state.total || count}`;
  } else {
    $("aiBatchStatus").textContent = !job
      ? "Open a finished search first."
      : active(job.status)
        ? "Wait for the search to finish."
        : `${count} lead${count === 1 ? "" : "s"} selected. Existing valid compilations with unchanged evidence will be skipped.`;
  }
  syncAiControls();
}
async function pollAiBatch(taskId, taskJobId) {
  aiBatchPolling = true;
  try {
    while (true) {
      const state = await aiApi(`/api/ai/tasks/${encodeURIComponent(taskId)}`);
      aiBatchState = state;
      renderAiBatch(state);
      if (!["queued", "running"].includes(state.status)) break;
      await new Promise((resolve) => setTimeout(resolve, 1400));
    }
    if (aiBatchState.status === "complete") {
      localStorage.removeItem("leadfinder.aiBatchTask");
      if (job?.id === taskJobId) {
        job = await api(`/api/jobs/${encodeURIComponent(taskJobId)}`);
        renderJob();
      }
    }
  } catch (err) {
    $("aiBatchStatus").textContent =
      `Batch status unavailable: ${err.message}. Saved completed leads are retained.`;
  } finally {
    aiBatchPolling = false;
    syncAiControls();
  }
}
async function startAiBatch() {
  if (!job || active(job.status) || aiBatchPolling || !aiReady()) return;
  const count = batchScopeCount();
  if (!count) {
    $("aiBatchStatus").textContent = "No leads match this compilation scope.";
    return;
  }
  aiBatchPolling = true;
  renderAiBatch({
    status: "queued",
    message: `Queueing ${count} leads…`,
    progress: 0,
  });
  try {
    const created = await aiApi("/api/ai/assist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        task: "compile_batch",
        model: $("aiModel").value,
        job_id: job.id,
        scope: $("aiBatchScope").value,
      }),
    });
    localStorage.setItem(
      "leadfinder.aiBatchTask",
      JSON.stringify({ id: created.id, job_id: job.id }),
    );
    await pollAiBatch(created.id, job.id);
  } catch (err) {
    aiBatchPolling = false;
    $("aiBatchStatus").textContent = err.message;
    syncAiControls();
  }
}
$("aiBatchCompile").addEventListener("click", startAiBatch);
$("aiBatchScope").addEventListener("change", () => renderAiBatch());
function renderAiProposal() {
  const output = $("aiPlanOutput");
  if (!aiProposal) {
    output.classList.add("hidden");
    return;
  }
  const result = aiProposal.result;
  const notes = Array.isArray(result.notes)
    ? result.notes.join(" ")
    : result.notes || "";
  output.classList.remove("hidden");
  output.innerHTML = `<h3>AI search tags · not applied to this search${result.saved_to_niche_pack ? " · saved to niche pack" : ""}</h3><p>AI-generated suggestions for ${escapeHtml(aiProposal.niche)} in ${escapeHtml(aiProposal.location)}. ${result.saved_to_niche_pack ? "Future searches for this niche can include them automatically; review them below and add them to the visible search form if you want to inspect the exact plan now." : "Review them for relevance."}</p><div class="chips">${aiProposal.phrases.map((phrase) => `<span class="chip">${escapeHtml(phrase)}</span>`).join("")}</div>${notes ? `<p>${escapeHtml(notes)}</p>` : ""}<p class="muted">Model: ${escapeHtml(result.model || aiProposal.model)}${result.generated_at ? ` · ${escapeHtml(result.generated_at)}` : ""}${(result.compiled_terms_used || []).length ? ` · learned from ${result.compiled_terms_used.length} compiled term${result.compiled_terms_used.length === 1 ? "" : "s"}` : ""}</p><div class="actions"><button id="aiUsePhrases" class="secondary" type="button">Use these phrases</button><button id="aiRejectPhrases" class="ghost" type="button">Not relevant</button></div><p id="aiApplyStatus" class="ai-task-status" role="status"></p>`;
  $("aiUsePhrases").addEventListener("click", async () => {
    if (
      aiProposal.niche !== $("niche").value.trim() ||
      aiProposal.location !== $("location").value.trim()
    ) {
      aiMessage(
        "aiApplyStatus",
        "Your service or location changed. Request new suggestions for this search.",
        true,
      );
      return;
    }
    const existing = $("phrases")
      .value.split(/\r?\n/)
      .map((p) => p.trim());
    const seen = new Set();
    const combined = [...existing, ...aiProposal.phrases]
      .filter(Boolean)
      .filter((phrase) => {
        const key = phrase.toLowerCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .join("\n");
    if (combined.length > 1000) {
      aiMessage(
        "aiApplyStatus",
        "These terms would exceed the 1,000-character search-phrase limit. Shorten the additional phrases first.",
        true,
      );
      return;
    }
    $("phrases").value = combined;
    $("phrases").closest("details").open = true;
    await updatePlan();
    let remembered = true;
    try {
      await api("/api/intelligence/ai-terms", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          niche: aiProposal.niche,
          phrases: aiProposal.phrases,
          model: result.model || aiProposal.model,
          accepted: true,
        }),
      });
    } catch (err) {
      remembered = false;
      aiMessage(
        "aiApplyStatus",
        "Added to Additional phrases, but teaching memory could not be updated: " +
          err.message,
        true,
      );
    }
    if (remembered)
      aiMessage(
        "aiApplyStatus",
        "Added to Additional phrases and remembered for this service. Review the strategy, then run your search when ready.",
      );
  });
  $("aiRejectPhrases").addEventListener("click", async () => {
    if (!aiProposal) return;
    $("aiRejectPhrases").disabled = true;
    try {
      await api("/api/intelligence/ai-terms", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          niche: aiProposal.niche,
          phrases: aiProposal.phrases,
          model: result.model || aiProposal.model,
          accepted: false,
        }),
      });
      aiMessage(
        "aiApplyStatus",
        "Noted. Future suggestions for this service will avoid those phrases.",
      );
    } catch (err) {
      aiMessage("aiApplyStatus", err.message, true);
    } finally {
      $("aiRejectPhrases").disabled = false;
    }
  });
  syncAiControls();
}
$("aiRefresh").addEventListener("click", loadAiStatus);
$("aiTeachSave").addEventListener("click", saveAiTeaching);
$("aiModel").addEventListener("change", () => {
  localStorage.setItem("leadfinder.aiModel", $("aiModel").value);
  if ($("campaignAiModel")) $("campaignAiModel").value = $("aiModel").value;
  syncAiControls();
  syncCampaignPrepare();
});
for (const id of ["niche", "location"])
  $(id).addEventListener("input", syncAiControls);
$("niche").addEventListener("input", syncAiTeachFields);
$("aiPlanButton").addEventListener("click", async () => {
  const niche = $("niche").value.trim();
  const location = $("location").value.trim();
  if (niche.length < 2 || !location) {
    aiMessage("aiPlanStatus", "Enter a service and location first.", true);
    return;
  }
  aiBusy = true;
  aiProposal = null;
  renderAiProposal();
  syncAiControls();
  const model = $("aiModel").value;
  aiMessage("aiPlanStatus", "Preparing local AI suggestions…");
  try {
    const result = await runAiTask(
      { task: "plan", model, niche, location },
      (message) => aiMessage("aiPlanStatus", message),
    );
    const phrases = Array.isArray(result.phrases)
      ? result.phrases.filter((p) => typeof p === "string" && p.trim())
      : [];
    if (!phrases.length)
      throw Error(
        "The model did not produce usable search phrases. Try again or enter your own.",
      );
    aiProposal = { niche, location, model, result, phrases };
    renderAiProposal();
    aiMessage(
      "aiPlanStatus",
      "Suggestions ready. Nothing has been applied or searched.",
    );
  } catch (err) {
    aiMessage("aiPlanStatus", err.message, true);
  } finally {
    aiBusy = false;
    syncAiControls();
  }
});
function route() {
  const hash = location.hash.slice(1) || "discover";
  const view =
    hash === "history"
      ? "history"
      : hash === "library"
        ? "library"
        : hash === "outreach"
          ? "outreach"
          : hash === "sources"
            ? "sources"
            : hash === "registries"
              ? "registries"
              : "discover";
  [
    "discover",
    "history",
    "sources",
    "registries",
    "library",
    "outreach",
  ].forEach((id) => $(id + "View").classList.toggle("hidden", id !== view));
  document
    .querySelectorAll("nav a")
    .forEach((a) => a.classList.toggle("active", a.hash === "#" + view));
  $("pageTitle").textContent = {
    discover: "Discover businesses",
    history: "Search history",
    sources: "Data sources",
    registries: "Business registries",
    library: "Your research library",
    outreach: "Outreach campaigns",
  }[view];
  $("resultSection").classList.toggle(
    "hidden",
    !job ||
      ["sources", "registries", "library", "history", "outreach"].includes(
        view,
      ),
  );
  if (view === "history") loadHistory();
  if (view === "library") loadLibrary();
  if (view === "outreach") loadOutreach();
  if (view === "sources") loadConnections();
  if (view === "registries") loadRegistries();
  if (hash === "results")
    $("resultSection").scrollIntoView({ behavior: "smooth" });
  if (hash === "diagnostics") {
    tab("diagnostics");
    $("resultSection").scrollIntoView({ behavior: "smooth" });
  }
}

let registryLoaded = false;
async function loadRegistries(force = false) {
  if (registryLoaded && !force) return;
  const params = new URLSearchParams({
    country: $("registryCountry")?.value || "",
    niche: $("registryNiche")?.value || "",
    query: $("registryQuery")?.value || "",
  });
  try {
    const data = await api(`/api/registries?${params}`);
    if (!registryLoaded) {
      $("registryCountry").innerHTML =
        '<option value="">All supported countries</option>' +
        data.countries
          .map((value) => `<option>${escapeHtml(value)}</option>`)
          .join("");
      $("registryNiche").innerHTML =
        '<option value="">All niches</option>' +
        data.niches
          .map((value) => `<option>${escapeHtml(value)}</option>`)
          .join("");
    }
    $("registryCards").innerHTML = data.directories.length
      ? data.directories
          .map(
            (item) =>
              `<article class="source-card registry-card"><h2>${escapeHtml(item.name)}</h2><span class="badge">${escapeHtml(item.country)}</span><p><b>${escapeHtml(item.authority)}</b></p><div class="registry-meta"><span class="badge candidate">${escapeHtml(item.access)}</span><span class="badge">${escapeHtml(item.mode.replaceAll("_", " "))}</span></div><p>${escapeHtml(item.search_hint)}</p><small>${escapeHtml(item.niches.join(" · "))}</small><p>${link(item.url, "Open official directory ↗")}</p></article>`,
          )
          .join("")
      : '<div class="empty-state"><b>No matching official directory</b><p>Try a broader country, niche or capability.</p></div>';
    $("registryNotice").textContent =
      `${data.directories.length} reviewed directory route${data.directories.length === 1 ? "" : "s"}. ${data.notice}`;
    registryLoaded = true;
  } catch (error) {
    $("registryNotice").textContent = error.message;
  }
}
$("registrySearch").addEventListener("click", () => loadRegistries(true));
$("registryQuery").addEventListener("keydown", (event) => {
  if (event.key === "Enter") loadRegistries(true);
});
window.addEventListener("hashchange", route);
async function updatePlan() {
  if ($("niche").value.trim().length < 2) {
    $("phraseChips").innerHTML = "";
    $("planNote").textContent =
      "Enter any business type or service to build a niche-specific plan.";
    $("researchStages").innerHTML = "";
    $("coverageSummary").textContent = "";
    $("strategyPreview").innerHTML = "";
    $("profileHelp").textContent =
      "General mode works for any niche. Local AI can suggest specialist terms after you enter one.";
    return;
  }
  try {
    const query = new URLSearchParams({
      niche: $("niche").value,
      location: $("location").value,
      country: $("country").value,
      source: $("source").value,
      target: $("target").value,
      coverage: $("coverage").value,
      depth: $("depth").value,
      query_budget: $("queryBudget").value,
      phrases: $("phrases").value,
      browser: String($("browser").checked),
      research_profile: $("researchProfile").value,
    });
    const data = await api("/api/plan?" + query);
    $("phraseChips").innerHTML = data.phrases
      .map((p) => `<span class="chip">${escapeHtml(p)}</span>`)
      .join("");
    const rejected = Array.isArray(data.rejected_phrases)
      ? data.rejected_phrases
      : [];
    $("planNote").textContent =
      data.note +
      (rejected.length
        ? ` Rejected ${rejected.length} weak or mismatched term(s): ${rejected.map((item) => `${item.phrase} (${item.reason})`).join("; ")}.`
        : "");
    renderStrategy(data.strategy);
    $("profileHelp").textContent =
      $("researchProfile").value === "hood_automation"
        ? "Your Tedt five-factor method: pain 25%, fit 20%, access 20%, capacity proxy 20%, underserved 15%. Missing evidence is unscored—not assumed."
        : "General mode adapts search, qualification, verification, and local AI to the niche you enter. The hood profile is never applied automatically.";
  } catch (err) {
    $("profileHelp").textContent = err.message;
  }
}
let debounce;
for (const id of [
  "niche",
  "location",
  "country",
  "target",
  "coverage",
  "depth",
  "queryBudget",
  "phrases",
  "source",
  "browser",
  "researchProfile",
]) {
  $(id).addEventListener(
    ["niche", "location", "phrases", "queryBudget"].includes(id)
      ? "input"
      : "change",
    () => {
      if (id === "country") syncCountryCoverage();
      if (id === "coverage")
        $("queryBudget").value =
          $("coverage").value === "usa"
            ? 120
            : $("coverage").value === "metro"
              ? 48
              : 24;
      clearTimeout(debounce);
      debounce = setTimeout(updatePlan, 350);
    },
  );
}
function syncCountryCoverage() {
  const isUnitedStates = $("country").value === "US";
  for (const value of ["states", "usa"]) {
    const option = $("coverage").querySelector(`option[value="${value}"]`);
    option.disabled = !isUnitedStates;
  }
  if (!isUnitedStates && ["states", "usa"].includes($("coverage").value))
    $("coverage").value = "exact";
  const examples = {
    US: "Dallas, Texas",
    SG: "Singapore",
    MY: "Kuala Lumpur, Malaysia",
    AU: "Sydney, New South Wales, Australia",
    manual: "City, region, country",
  };
  $("location").placeholder = examples[$("country").value] || examples.manual;
}
function renderStrategy(s) {
  if (!s) return;
  $("researchStages").innerHTML = s.stages
    .map(
      (stage, i) =>
        `<div class="research-stage"><span class="step">${i + 1}</span><div><b>${escapeHtml(stage.name)}</b><small>${escapeHtml(stage.purpose)}</small></div></div>`,
    )
    .join("");
  $("coverageSummary").textContent =
    `${s.planned_queries} scheduled queries · ${s.scheduled_locations.length} scheduled locations · ${s.unsearched_locations.length} locations outside this budget. ${s.coverage_note}`;
  $("strategyPreview").innerHTML = strategyMarkup(s);
}
function strategyMarkup(s, events = []) {
  if (!s) return "<p>Research plan was not recorded for this earlier run.</p>";
  const attempted = new Set(
    events.map((e) => e.details?.query).filter(Boolean),
  );
  const platforms = s.platforms
    .map(
      (p) =>
        `<div class="evidence"><b>${escapeHtml(p.name)}</b>${link(p.url)}<small>${escapeHtml(p.use)}</small></div>`,
    )
    .join("");
  const queries = s.queries
    .map((q) => {
      const status = events.length
        ? `<small>${attempted.has(q.query) ? "Attempted — inspect timeline for outcome" : "Not attempted"}</small>`
        : "";
      return `<div class="evidence"><span class="badge">${escapeHtml(q.channel)} · ${escapeHtml(q.intent.replaceAll("_", " "))}</span><p>${escapeHtml(q.query)}</p>${status}</div>`;
    })
    .join("");
  const unsearched = s.unsearched_locations.length
    ? `<details><summary>${s.unsearched_locations.length} locations not searched within this budget</summary><p>${escapeHtml(s.unsearched_locations.join("; "))}</p></details>`
    : "";
  const discovered = s.discovered_sources?.length
    ? "<h3>New platform candidates · not yet verified</h3>" +
      s.discovered_sources
        .map(
          (p) =>
            `<div class="evidence">${link(p.url, p.name)}<small>${escapeHtml(p.excerpt)}</small></div>`,
        )
        .join("")
    : "";
  return `<p class="muted">${escapeHtml(s.method)}</p>${s.research_profile ? `<p><b>Research profile:</b> ${escapeHtml(s.research_profile.name || s.research_profile.title || s.research_profile.id)}</p>` : ""}<h3>Documented platforms for this niche</h3>${platforms}<h3>City coverage</h3><p>${escapeHtml(s.scheduled_locations.join("; ")) || "No web/Maps queries scheduled"}</p>${unsearched}<h3>Query schedule</h3><div class="query-list" tabindex="0" role="region" aria-label="Scheduled research queries">${queries}</div>${discovered}`;
}
$("searchForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("formError").textContent = "";
  $("runButton").disabled = true;
  try {
    const data = await api("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        niche: $("niche").value,
        location: $("location").value,
        country: $("country").value,
        limit: Number($("limit").value),
        source: $("source").value,
        browser: $("browser").checked,
        enrich: $("enrich").checked,
        phrases: $("phrases").value,
        urls: $("urls").value,
        target: $("target").value,
        coverage: $("coverage").value,
        depth: $("depth").value,
        query_budget: Number($("queryBudget").value),
        prefer_independent: $("preferIndependent").checked,
        research_profile: $("researchProfile").value,
        reference_ids: preparedReferenceIds,
      }),
    });
    jobId = data.id;
    localStorage.setItem("leadfinder.lastJob", jobId);
    workflowTask = null;
    clearTimeout(workflowPollTimer);
    if ($("linkedWorkflow").checked) {
      const linked = await api("/api/workflows", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: jobId,
          model: $("aiModel").value || "",
        }),
      });
      workflowId = linked.id;
      localStorage.setItem("leadfinder.workflowTask", workflowId);
      pollWorkflow(workflowId);
    } else {
      workflowId = null;
      localStorage.removeItem("leadfinder.workflowTask");
      renderWorkflow();
    }
    clearTimeout(pollTimer);
    await poll();
  } catch (err) {
    $("formError").textContent = err.message;
    $("runButton").disabled = false;
  }
});
async function poll() {
  try {
    job = await api("/api/jobs/" + jobId);
    renderJob();
    if (active(job.status)) pollTimer = setTimeout(poll, 1300);
    else loadHistory();
  } catch (err) {
    $("formError").textContent = err.message;
    $("runButton").disabled = false;
  }
}
function renderWorkflow() {
  const card = $("workflowCard");
  const matchesCurrentJob =
    workflowTask && (!job || workflowTask.job_id === job.id);
  card.classList.toggle("hidden", !matchesCurrentJob);
  if (!matchesCurrentJob) return;
  $("workflowStatus").textContent =
    workflowTask.message || "Linked workflow is preparing.";
  $("workflowProgress").value = Number(workflowTask.progress) || 0;
  const order = [
    "discovery",
    "verification",
    "organization",
    "compilation",
    "outreach",
  ];
  $("workflowStages").innerHTML = order
    .map((name, index) => {
      const stage = workflowTask.stages?.[name] || {
        label: name,
        status: "pending",
        message: "Waiting",
      };
      return `<article class="workflow-stage ${escapeHtml(stage.status || "pending")}"><span class="eyebrow">${String(index + 1).padStart(2, "0")} · ${escapeHtml((stage.status || "pending").replaceAll("_", " "))}</span><b>${escapeHtml(stage.label || name)}</b><small>${escapeHtml(stage.message || "Waiting")}</small></article>`;
    })
    .join("");
  const running = active(workflowTask.status);
  $("cancelWorkflow").classList.toggle("hidden", !running);
  $("cancelWorkflow").disabled = false;
}
async function pollWorkflow(id) {
  clearTimeout(workflowPollTimer);
  try {
    workflowTask = await api(`/api/workflows/${encodeURIComponent(id)}`);
    if (jobId === workflowTask.job_id) {
      job = await api("/api/jobs/" + jobId);
      renderJob();
    }
    renderWorkflow();
    if (active(workflowTask.status)) {
      workflowPollTimer = setTimeout(() => pollWorkflow(id), 1400);
    } else {
      localStorage.removeItem("leadfinder.workflowTask");
      workflowId = null;
      library = null;
      campaignJobsLoaded = false;
      await loadHistory();
      const newer = await api(
        `/api/workflows/current?job_id=${encodeURIComponent(workflowTask.job_id)}`,
      ).catch(() => ({}));
      if (newer.id && newer.id !== id && active(newer.status)) {
        workflowId = newer.id;
        localStorage.setItem("leadfinder.workflowTask", workflowId);
        pollWorkflow(workflowId);
      }
    }
  } catch (err) {
    $("workflowStatus").textContent = err.message;
  }
}
async function discoverWorkflowForJob() {
  if (!jobId || workflowId) return false;
  try {
    const found = await api(
      `/api/workflows/current?job_id=${encodeURIComponent(jobId)}`,
    );
    if (!found.id) return false;
    workflowId = found.id;
    workflowTask = found;
    localStorage.setItem("leadfinder.workflowTask", workflowId);
    return true;
  } catch {}
  return false;
}
$("cancelWorkflow").addEventListener("click", async () => {
  if (!workflowTask || !active(workflowTask.status)) return;
  $("cancelWorkflow").disabled = true;
  await api(`/api/workflows/${workflowTask.id}/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  $("workflowStatus").textContent =
    "Stopping the active stage; completed work remains saved.";
});
function renderJob() {
  rows = job.rows || [];
  $("runButton").disabled = active(job.status);
  $("liveStatus").textContent = job.message;
  $("runCard").innerHTML =
    `<div class="run-heading"><div><span class="eyebrow">${escapeHtml(job.status.toUpperCase())}</span><h2>${escapeHtml(job.message)}</h2></div>${active(job.status) ? '<button class="danger" id="cancelSearch">Stop search</button>' : ""}</div><progress value="${job.progress || 0}" max="100" aria-label="Search progress"></progress><div class="run-status">${rows.length} collected · ${Math.round(job.elapsed || 0)} seconds elapsed · Results save automatically</div><p>${escapeHtml(job.status === "waiting" ? "Check the dedicated Chrome window. The search is waiting for your action." : job.diagnosis || "Inspect the business list or open diagnostics for source-by-source progress.")}</p><div class="chips">${Object.entries(
      job.providers || {},
    )
      .map(
        ([name, p]) =>
          `<span class="chip">${escapeHtml(name)} · ${escapeHtml(p.status)} · ${p.count || 0}</span>`,
      )
      .join("")}</div>`;
  $("cancelSearch")?.addEventListener("click", async () => {
    await api(`/api/jobs/${job.id}/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    $("cancelSearch").disabled = true;
    $("cancelSearch").textContent = "Stopping…";
  });
  $("resultSection").classList.toggle(
    "hidden",
    ["#library", "#sources", "#history", "#outreach"].includes(location.hash),
  );
  $("resultHeading").textContent =
    job.count + " businesses · " + job.params.niche;
  const stats = job.stats || {};
  $("stats").innerHTML = [
    ["Published emails", stats.emails ?? rows.filter((r) => r.email).length],
    ["Phone numbers", stats.phones ?? rows.filter((r) => r.phone).length],
    ["Websites", stats.websites ?? rows.filter((r) => r.website).length],
    [
      "Service matches",
      stats.matches ??
        rows.filter((r) => r.match_status !== "candidate").length,
    ],
  ]
    .map(
      ([label, count]) =>
        `<div class="stat"><strong>${count}</strong><span>${label}</span></div>`,
    )
    .join("");
  const diagnosis = [job.diagnosis, ...(job.warnings || [])]
    .filter(Boolean)
    .join(" ");
  $("diagnosis").textContent = diagnosis;
  $("diagnosis").classList.toggle("hidden", !diagnosis);
  renderAiBatch();
  for (const kind of ["csv", "json", "log"])
    $(kind + "Link").href = `/api/download/${job.id}/${kind}`;
  $("qualificationStats").innerHTML = [
    [
      "Solo",
      stats.individuals ??
        rows.filter((r) => r.operator_type === "solo_provider").length,
    ],
    [
      "Independent",
      stats.independents ??
        rows.filter((r) =>
          ["solo_provider", "independent_business"].includes(r.operator_type),
        ).length,
    ],
    [
      "Seller profiles",
      stats.profiles ?? rows.filter((r) => r.profile_url).length,
    ],
  ]
    .map(([label, n]) => `<span class="chip">${label}: ${n}</span>`)
    .join("");
  renderRows();
  renderVerification();
  renderDiagnostics();
  renderWorkflow();
  syncAiControls();
}
function renderRows() {
  const query = $("filter").value.toLowerCase(),
    filter = $("contactFilter").value;
  visible = rows
    .filter((r) =>
      Object.values(r).some((v) => String(v).toLowerCase().includes(query)),
    )
    .filter(
      (r) =>
        filter === "all" ||
        (filter === "email" && r.email) ||
        (filter === "recommendedEmail" && recommendedEmail(r)) ||
        (filter === "phone" && r.phone) ||
        (filter === "noWebsite" && !r.website) ||
        (filter === "matched" && r.match_status !== "candidate"),
    )
    .filter((r) => {
      const selected = $("operatorFilter").value;
      return (
        selected === "all" ||
        (selected === "independent" &&
          ["solo_provider", "independent_business"].includes(
            r.operator_type,
          )) ||
        (selected === "unknown" &&
          (!r.operator_type || r.operator_type === "unknown")) ||
        r.operator_type === selected
      );
    })
    .filter((r) => {
      const selected = $("evidenceFilter").value;
      return (
        selected === "all" ||
        (selected === "profile" && r.profile_url) ||
        (selected === "first_party_page" && r.source_strength === selected) ||
        (selected === "weak" &&
          (!r.source_strength ||
            r.source_strength === "search_snippet" ||
            r.operator_confidence === "snippet_only"))
      );
    })
    .filter((r) => {
      const selected = $("opportunityFilter").value;
      return (
        selected === "all" ||
        (selected === "named"
          ? Boolean(r.decision_maker)
          : parseList(r.workflow_signals).some((s) => s.kind === selected))
      );
    });
  const matchRank = { service_match: 0, category_match: 1, candidate: 2 };
  const locationRank = {
    address_mentions_search_city: 0,
    place_mentioned_on_page: 1,
    query_only: 2,
    address_city_needs_review: 3,
  };
  visible.sort((a, b) =>
    $("sort").value === "name"
      ? a.name.localeCompare(b.name)
      : $("sort").value === "relevance"
        ? (matchRank[a.match_status] ?? 2) - (matchRank[b.match_status] ?? 2) ||
          (locationRank[a.location_evidence] ?? 2) -
            (locationRank[b.location_evidence] ?? 2) ||
          Number(b.score) - Number(a.score)
        : Number(b.score) - Number(a.score),
  );
  const ranks = {
    solo_provider: 0,
    independent_business: 1,
    unknown: 2,
    agency: 3,
    chain_or_franchise: 4,
  };
  if ($("qualificationSort").value === "independent")
    visible.sort(
      (a, b) => (ranks[a.operator_type] ?? 2) - (ranks[b.operator_type] ?? 2),
    );
  if ($("qualificationSort").value === "evidence")
    visible.sort((a, b) => (b.evidence_score || 0) - (a.evidence_score || 0));
  if ($("qualificationSort").value === "opportunity")
    visible.sort(
      (a, b) => (b.opportunity_score || 0) - (a.opportunity_score || 0),
    );
  $("leadRows").innerHTML = visible.length
    ? visible
        .map(
          (r, index) =>
            `<tr><td><b>${escapeHtml(r.name)}</b><small>${escapeHtml(r.address || r.city)}</small><small>${escapeHtml(r.sources || r.source)}</small><span class="badge ${!r.operator_type || r.operator_type === "unknown" ? "candidate" : ""}">${escapeHtml((r.operator_type || "not assessed").replaceAll("_", " "))}</span><small>${escapeHtml((r.operator_confidence || "").replaceAll("_", " "))}</small>${r.decision_maker ? `<small>Published role: ${escapeHtml(r.decision_maker)}</small>` : ""}</td><td>${escapeHtml(r.phone) || "—"}<br>${escapeHtml(r.email) || "—"}${emailQualityBadge(r)}${r.profile_url ? `<small>${link(r.profile_url, "View public seller profile ↗")}</small>` : ""}</td><td>${link(r.website, r.website ? new URL(safeUrl(r.website) || "https://invalid.local").hostname : "—")}</td><td><span class="badge">${Number(r.score) || 0}/100</span><small>Evidence: ${Number(r.evidence_score) || 0}/100</small>${r.research_profile === "hood_automation" ? `<small>Opportunity: ${Number(r.opportunity_score || 0)} supported pts</small>` : ""}</td><td><span class="badge ${r.match_status === "candidate" ? "candidate" : ""}">${escapeHtml(r.match_status === "candidate" ? "Needs review" : r.match_status === "category_match" ? "Category match" : "Service match")}</span><small>${escapeHtml(r.contact_status?.replaceAll("_", " "))}</small><small>${parseList(r.quality_flags).length} quality flags</small></td><td><button class="secondary detail-button" data-index="${index}" aria-label="View details for ${escapeHtml(r.name)}">Details</button></td></tr>`,
        )
        .join("")
    : '<tr><td colspan="6">' +
      (active(job?.status)
        ? "Collecting businesses. See Run diagnostics for progress."
        : "No businesses match these filters. Check run diagnostics for coverage details.") +
      "</td></tr>";
  $("visibleCount").textContent =
    `Showing ${visible.length} of ${rows.length} businesses. Quality measures available contact fields, not mailbox verification.`;
  document
    .querySelectorAll(".detail-button")
    .forEach((b) =>
      b.addEventListener("click", () =>
        details(visible[Number(b.dataset.index)]),
      ),
    );
}
function recommendedEmail(row) {
  const quality = parseObject(row.email_quality);
  if (!Array.isArray(quality.recommended)) return Boolean(row.email);
  return quality.recommended.some(
    (item) =>
      item.email?.toLowerCase() === String(row.email || "").toLowerCase(),
  );
}
function emailQualityBadge(row) {
  const quality = parseObject(row.email_quality);
  const preferred = Array.isArray(quality.recommended)
    ? quality.recommended.find(
        (item) =>
          item.email?.toLowerCase() === String(row.email || "").toLowerCase(),
      )
    : null;
  if (!preferred) {
    const excluded = Array.isArray(quality.excluded)
      ? quality.excluded[0]
      : null;
    return excluded
      ? `<small class="email-quality excluded">${escapeHtml(excluded.type.replaceAll("_", " "))} · excluded from outreach</small>`
      : "";
  }
  return `<small class="email-quality recommended">✓ ${escapeHtml(preferred.type.replaceAll("_", " "))} · recommended</small>`;
}
function intelligenceSection(title, subtitle, body, open = false, badge = "") {
  return `<details class="intel-accordion" ${open ? "open" : ""}><summary><span class="intel-summary-copy"><h3>${escapeHtml(title)}</h3><small>${escapeHtml(subtitle)}</small></span>${badge ? `<span class="intel-summary-badge">${escapeHtml(badge)}</span>` : ""}<span class="intel-chevron" aria-hidden="true">⌄</span></summary><div class="intel-accordion-body">${body}</div></details>`;
}
function intelligenceSubsection(title, body, open = false) {
  return `<details class="intel-subsection" ${open ? "open" : ""}><summary><h4>${escapeHtml(title)}</h4><span aria-hidden="true">+</span></summary><div>${body}</div></details>`;
}
function details(r, context = {}) {
  if (!r) return;
  const rowIndex = Number.isInteger(context.rowIndex)
    ? context.rowIndex
    : rows.indexOf(r);
  detailContext = { jobId: context.jobId || job?.id, rowIndex };
  $("detailTitle").textContent = r.name;
  let evidence = [];
  try {
    evidence = JSON.parse(r.evidence || "[]");
  } catch {}
  const snapshot = `<div class="lead-snapshot"><div class="lead-snapshot-copy"><span class="eyebrow">LEAD INTELLIGENCE RECORD</span><h3>${escapeHtml(r.name || "Unnamed business")}</h3><p>${escapeHtml(r.match_reason || "Evidence is organized below for review.")}</p></div><div class="lead-score"><strong>${Number(r.score) || 0}</strong><span>quality</span></div></div><div class="detail-grid compact">${[
    ["Address", r.address || r.city],
    ["Phones", r.phones || r.phone],
    ["Emails", r.emails || r.email],
    ["Contact check", r.contact_status],
    ["Last checked", r.checked_at],
    ["Match", String(r.match_status || "not assessed").replaceAll("_", " ")],
  ]
    .map(
      ([name, value]) =>
        `<div><strong>${name}</strong>${escapeHtml(value) || "—"}</div>`,
    )
    .join("")}</div>`;
  const contactBody = `<div class="detail-grid">${[
    ["Primary email", r.email],
    ["Primary phone", r.phone],
    ["Contact status", r.contact_status],
    [
      "Decision-maker",
      [r.decision_maker, r.decision_maker_role].filter(Boolean).join(" · "),
    ],
  ]
    .map(
      ([name, value]) =>
        `<div><strong>${name}</strong>${escapeHtml(value) || "—"}</div>`,
    )
    .join("")}</div><div class="intel-link-grid">${[
    r.website,
    r.facebook,
    r.instagram,
    r.linkedin,
  ]
    .filter(Boolean)
    .map((x) => link(x))
    .join("")}</div>${emailQualityBadge(r)}`;
  const sourceBody = `<div class="intel-link-grid">${link(r.source_url, "Open primary public source ↗")}${link(r.website, "Open business website ↗")}</div>${evidence.length ? evidence.map((e) => `<div class="evidence"><b>${escapeHtml(e.field)}: ${escapeHtml(e.value)}</b><small>${escapeHtml(e.method)} · ${escapeHtml(e.observed_at)}</small>${link(e.url)}</div>`).join("") : "<p>No website evidence recorded. Listing contacts can be checked at the public source link above.</p>"}`;
  $("detailBody").innerHTML =
    `${snapshot}${intelligenceSection("Contact intelligence", "Published phone, email, decision-maker and profiles", contactBody, true, r.email ? "Email found" : "Needs contact")}${intelligenceSection("Contact evidence", `${evidence.length} retained source claim${evidence.length === 1 ? "" : "s"}`, sourceBody)}`;
  $("detailBody").insertAdjacentHTML("beforeend", aiReviewDetails(r));
  const operatorEvidence = parseList(r.operator_evidence)
    .map(
      (e) =>
        `<div class="evidence"><b>${escapeHtml(e.status)}</b><p>${escapeHtml(e.excerpt)}</p>${link(e.url)}</div>`,
    )
    .join("");
  const factEvidence =
    parseList(r.facts)
      .map(
        (e) =>
          `<div class="evidence"><b>${escapeHtml(e.field)} · ${escapeHtml(e.status)}</b><p>${escapeHtml(e.value)}</p>${link(e.url)}<small>${escapeHtml(e.basis)}</small></div>`,
      )
      .join("") || "<p>Not assessed in this earlier run.</p>";
  const assumptionEvidence =
    parseList(r.assumptions)
      .map((x) => `<p>• ${escapeHtml(x)}</p>`)
      .join("") || "<p>No unresolved assumption was recorded.</p>";
  const qualificationBody = `<div class="detail-grid"><div><strong>Operator type</strong>${escapeHtml((r.operator_type || "not assessed").replaceAll("_", " "))}</div><div><strong>Confidence</strong>${escapeHtml((r.operator_confidence || "unknown").replaceAll("_", " "))}</div><div><strong>Discovery query</strong>${escapeHtml(r.discovery_query) || "Not recorded"}</div><div><strong>Quality flags</strong>${escapeHtml(parseList(r.quality_flags).join(", ") || "None recorded")}</div></div>${operatorEvidence}${intelligenceSubsection("Observed facts and source claims", factEvidence, true)}${intelligenceSubsection("Assumptions and unresolved checks", assumptionEvidence, true)}`;
  $("detailBody").insertAdjacentHTML(
    "beforeend",
    intelligenceSection(
      "Qualification & evidence analysis",
      "Operator type, observed facts, assumptions and quality flags",
      qualificationBody,
      true,
    ),
  );
  $("detailBody").insertAdjacentHTML("beforeend", opportunityDetails(r));
  $("detailBody").insertAdjacentHTML("beforeend", verificationDetails(r));
  $("detailBody").insertAdjacentHTML("beforeend", socialDiscoveryDetails(r));
  $("detailBody").insertAdjacentHTML("beforeend", intelligenceDetails(r));
  const merged = parseList(r.duplicate_summary);
  $("detailBody").insertAdjacentHTML(
    "beforeend",
    intelligenceSection(
      "Merged duplicate sources",
      "Canonical record and retained merge trail",
      `${
        merged.length
          ? merged
              .map(
                (item) =>
                  `<div class="evidence"><b>${escapeHtml(item.name || "Matching record")}</b><p>${escapeHtml(item.address || item.city || "Location not recorded")}</p>${link(item.source_url || item.website, "Open retained source ↗")}<small>${escapeHtml(item.source || "source")} · consolidated into this canonical prospect</small></div>`,
              )
              .join("")
          : "<p>No duplicate source records were consolidated into this prospect.</p>"
      }`,
    ),
  );
  $("aiReviewButton").textContent = "Review with local AI";
  $("aiReviewButton")
    .closest(".ai-review")
    .querySelector(".notice")
    .append(" AI-generated and unverified until you approve it.");
  $("aiReviewButton").addEventListener("click", reviewLeadWithAi);
  $("aiCompileButton").addEventListener("click", compileLeadWithAi);
  if ($("recordOutcome"))
    $("recordOutcome").addEventListener("click", () => recordLeadOutcome(r));
  if (!$("leadDialog").open) $("leadDialog").showModal();
  syncAiControls();
  if (r.entity_id) loadEntityMemory(r.entity_id);
}
async function loadEntityMemory(entityId) {
  const host = document.createElement("details");
  host.id = "entityMemory";
  host.className = "intel-accordion";
  host.innerHTML =
    '<summary><span class="intel-summary-copy"><h3>Connected company history</h3><small>Loading locations, contacts, evidence and outcomes…</small></span><span class="intel-chevron" aria-hidden="true">⌄</span></summary><div class="intel-accordion-body"><p>Loading connected memory…</p></div>';
  $("detailBody").append(host);
  try {
    const memory = await api(
      `/api/intelligence/entities/${encodeURIComponent(entityId)}`,
    );
    if (!host.isConnected) return;
    host.innerHTML = `<summary><span class="intel-summary-copy"><h3>Connected company history</h3><small>First observed ${escapeHtml(
      String(memory.first_seen || "")
        .replace("T", " ")
        .slice(0, 16),
    )} · last observed ${escapeHtml(
      String(memory.last_seen || "")
        .replace("T", " ")
        .slice(0, 16),
    )}</small></span><span class="intel-summary-badge">${memory.evidence?.length || 0} claims</span><span class="intel-chevron" aria-hidden="true">⌄</span></summary><div class="intel-accordion-body"><div class="detail-grid"><div><strong>Locations</strong>${memory.locations?.length || 0}</div><div><strong>Contacts retained</strong>${memory.contacts?.length || 0}</div><div><strong>Evidence claims</strong>${memory.evidence?.length || 0}</div><div><strong>Outcomes</strong>${memory.outcomes?.length || 0}</div></div>${intelligenceSubsection(`Contact history · ${memory.contacts?.length || 0}`, (memory.contacts || []).map((contact) => `<div class="evidence"><b>${escapeHtml(contact.name || contact.email || contact.phone)}</b><p>${escapeHtml([contact.role, contact.email, contact.phone].filter(Boolean).join(" · "))}</p><small>${escapeHtml(contact.status)} · confidence ${Number(contact.confidence) || 0}/100</small></div>`).join("") || "<p>No retained contact history.</p>")}${intelligenceSubsection(`Known locations · ${memory.locations?.length || 0}`, (memory.locations || []).map((location) => `<div class="evidence"><b>${escapeHtml(location.address || location.city)}</b>${link(location.source_url, "Source ↗")}<small>Last observed ${escapeHtml(String(location.last_seen || "").slice(0, 10))}</small></div>`).join("") || "<p>No known location history.</p>")}${intelligenceSubsection(`Outreach outcomes · ${memory.outcomes?.length || 0}`, (memory.outcomes || []).map((outcome) => `<div class="evidence"><b>${escapeHtml(outcome.outcome.replaceAll("_", " "))}</b><p>${escapeHtml(outcome.note)}</p><small>${escapeHtml(outcome.created_at)}</small></div>`).join("") || "<p>No outreach outcomes recorded.</p>")}${intelligenceSubsection(`Evidence ledger · ${memory.evidence?.length || 0}`, (memory.evidence || []).map((item) => `<div class="evidence"><b>${escapeHtml(item.field)}: ${escapeHtml(item.value)}</b>${link(item.source_url, "Evidence source ↗")}<small>${escapeHtml(item.basis)} · ${escapeHtml(item.observed_at)}</small></div>`).join("") || "<p>No retained claims.</p>")}</div>`;
  } catch (err) {
    if (host.isConnected)
      host.innerHTML = `<summary><span class="intel-summary-copy"><h3>Connected company history</h3><small>Memory could not be loaded</small></span><span class="intel-chevron" aria-hidden="true">⌄</span></summary><div class="intel-accordion-body"><p class="notice">${escapeHtml(err.message)}</p></div>`;
  }
}
function intelligenceDetails(r) {
  const insight = parseObject(r.intelligence);
  const audit = parseObject(r.website_audit);
  const signals = parseList(r.opportunity_signals);
  if (!r.entity_id && !insight.entity_id)
    return intelligenceSection(
      "Lead intelligence memory",
      "Identity, audit, next action and outcome learning",
      "<p>This earlier prospect has not completed the intelligence compilation stage yet.</p>",
    );
  const overview = `<div class="detail-grid"><div><strong>Canonical company</strong>${escapeHtml(r.entity_id || insight.entity_id)}</div><div><strong>Operating location</strong>${escapeHtml(r.operating_entity_id || "not compiled")}</div><div><strong>Contact confidence</strong>${Number(r.contact_confidence ?? insight.contact_confidence) || 0}/100</div><div><strong>Next best action</strong>${escapeHtml(String(r.next_best_action || insight.next_best_action || "review").replaceAll("_", " "))}</div><div><strong>Public change</strong>${insight.change_detected ? "Detected since previous snapshot" : "No change detected"}</div></div><p>${escapeHtml(r.next_action_reason || insight.next_action_reason || "")}</p>`;
  const auditBody = `<div class="detail-grid">${[
    ["Status", audit.status],
    ["Contact form", audit.contact_form],
    ["Booking path", audit.booking_path],
    ["Mobile viewport", audit.mobile_viewport],
    ["Structured data", audit.structured_data],
    ["Analytics tags", audit.analytics],
  ]
    .map(
      ([label, value]) =>
        `<div><strong>${label}</strong>${escapeHtml(value === true ? "observed" : value === false ? "not observed" : value || "unknown")}</div>`,
    )
    .join("")}</div>`;
  const signalBody = signals.length
    ? signals
        .map(
          (signal) =>
            `<div class="evidence"><b>${escapeHtml(signal.label || signal.kind)}</b><p>${escapeHtml(signal.evidence)}</p><small>${escapeHtml(signal.strength || "candidate")} · observation, not a guaranteed buying signal</small></div>`,
        )
        .join("")
    : "<p>No supported opportunity signal was compiled.</p>";
  const outcomeBody = `<div class="outcome-row"><select id="leadOutcome"><option value="replied">Replied</option><option value="positive_reply">Positive reply</option><option value="referral">Referral</option><option value="out_of_office">Out of office</option><option value="meeting_booked">Meeting booked</option><option value="customer_won">Customer won</option><option value="not_interested">Not interested</option><option value="wrong_contact">Wrong contact</option><option value="hard_bounce">Hard bounce</option><option value="bounced">Bounced</option><option value="unsubscribed">Unsubscribed</option></select><button id="recordOutcome" class="secondary" type="button">Save outcome</button></div><p id="outcomeStatus" class="muted">The next-action queue and suppression rules update immediately.</p>`;
  return intelligenceSection(
    "Lead intelligence memory",
    "Identity, website audit, next action and outcome learning",
    `${overview}${intelligenceSubsection("Website opportunity audit", auditBody)}${intelligenceSubsection(`Opportunity and intent signals · ${signals.length}`, signalBody)}${intelligenceSubsection("Record an outreach outcome", outcomeBody)}`,
    false,
    `${Number(r.contact_confidence ?? insight.contact_confidence) || 0}% contact`,
  );
}
async function recordLeadOutcome(row) {
  const button = $("recordOutcome");
  button.disabled = true;
  try {
    await api("/api/intelligence/outcomes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        company_id: row.entity_id,
        email: row.email,
        outcome: $("leadOutcome").value,
        note: "Recorded from prospect details",
      }),
    });
    $("outcomeStatus").textContent =
      "Outcome saved. The work queue and outreach safety gate were updated.";
    intelligenceOverview = await api("/api/intelligence/overview");
    intelligenceQueue = await api("/api/intelligence/queue");
    renderIntelligence();
  } catch (err) {
    $("outcomeStatus").textContent = err.message;
  } finally {
    button.disabled = false;
  }
}
function verificationDetails(r) {
  const report = parseObject(r.verification);
  if (!report.status)
    return intelligenceSection(
      "Second-round verification",
      "Website, reviews, social, ads and email quality",
      "<p>Not run for this prospect yet. It will be queued by the linked workflow after discovery.</p>",
    );
  const website = report.website || {};
  const socials = Object.entries(report.socials || {}).filter(
    ([, value]) => value?.url,
  );
  const ads = report.ads || {};
  const tech = report.technographics || {};
  const fetchInfo = tech.fetch || {};
  const headerSignals = Object.entries(tech.headers || {}).map(
    ([name, value]) => `${name}: ${value}`,
  );
  const dnsSignals = tech.dns || {};
  const otherReviews = report.reviews?.other_sources || [];
  const marketSignals = report.market_signals?.candidates || [];
  const emailQuality = parseObject(r.email_quality);
  const overview = `<div class="detail-grid"><div><strong>Website check</strong>${escapeHtml((website.status || "unknown").replaceAll("_", " "))}</div><div><strong>Fetch tier</strong>${escapeHtml(String(fetchInfo.fetch_tier || "standard HTTP").replaceAll("_", " "))}</div><div><strong>Checked</strong>${escapeHtml(report.checked_at || "—")}</div><div><strong>Google rating</strong>${escapeHtml(report.reviews?.google_maps?.rating || "—")} · ${escapeHtml(report.reviews?.google_maps?.review_count || "0")} reviews</div><div><strong>Ads evidence</strong>${escapeHtml((ads.status || "not verified").replaceAll("_", " "))}</div><div><strong>SPF / DMARC</strong>${escapeHtml(`${(dnsSignals.spf || []).length ? "observed" : "not observed"} / ${(dnsSignals.dmarc || []).length ? "observed" : "not observed"}`)}</div></div>${website.error ? `<p class="notice">${escapeHtml(website.error)}</p>` : ""}${fetchInfo.waf_signature ? `<p class="notice">A browser security checkpoint was detected. The lead is retained for manual review; the app does not evade the checkpoint.</p>` : ""}`;
  const technographics = `<div class="detail-grid"><div><strong>Server / framework</strong>${escapeHtml(headerSignals.join(", ") || "not observed")}</div><div><strong>Cookies</strong>${escapeHtml((tech.cookie_names || []).join(", ") || "not observed")}</div><div><strong>Robots / sitemap</strong>${escapeHtml([tech.robots?.status || tech.robots, tech.sitemap?.status || tech.sitemap].filter(Boolean).join(" / ") || "not checked")}</div><div><strong>Fetch duration</strong>${Number(fetchInfo.elapsed_ms || 0) ? `${Number(fetchInfo.elapsed_ms)} ms` : "not recorded"}</div></div>`;
  const emails = `${[...(emailQuality.recommended || []), ...(emailQuality.excluded || [])].map((item) => `<div class="evidence"><b>${escapeHtml(item.email)}</b><span class="badge ${item.recommended ? "" : "candidate"}">${escapeHtml(item.recommended ? "outreach eligible" : "excluded")}</span><small>${escapeHtml(String(item.type || "unknown").replaceAll("_", " "))} · ${escapeHtml(String(item.deliverability || "not tested").replaceAll("_", " "))} · ${escapeHtml(String(item.basis || "unknown").replaceAll("_", " "))}</small></div>`).join("") || "<p>No published email was available to classify.</p>"}<p><b>Mail domain:</b> ${escapeHtml(String(report.email_domain?.status || "not checked").replaceAll("_", " "))}</p><p class="fine-print">${escapeHtml(report.email_domain?.note || emailQuality.note || "Mailbox deliverability was not tested.")} A mailbox becomes delivery-confirmed only after a real send outcome.</p>`;
  const profiles = socials.length
    ? socials
        .map(
          ([name, value]) =>
            `<div class="evidence"><b>${escapeHtml(name)}</b>${link(value.url)}<small>${escapeHtml((value.status || "listed").replaceAll("_", " "))}</small></div>`,
        )
        .join("")
    : "<p>No social profile link was found in saved public evidence.</p>";
  const advertising = `<p>${escapeHtml(ads.note || "Campaign status was not verified.")}</p>${(ads.tracking_signals || []).map((signal) => `<div class="evidence"><b>${escapeHtml(signal.signal.replaceAll("_", " "))}</b>${link(signal.source_url, "Observed page ↗")}<small>Website source pattern; not proof of an active campaign.</small></div>`).join("") || "<p>No supported website tracking signal was observed. This does not prove no ads.</p>"}<p>${link(ads.meta_ad_library, "Check Meta Ad Library ↗")} · ${link(ads.google_ads_transparency, "Check Google Ads Transparency Center ↗")}</p>`;
  const marketPresence = marketSignals.length
    ? marketSignals
        .map(
          (signal) =>
            `<div class="evidence"><b>${escapeHtml(String(signal.platform || "public platform").replace("www.", ""))} · ${escapeHtml(String(signal.kind || "candidate signal").replaceAll("_", " "))}</b><p>${escapeHtml(signal.title || signal.snippet || "Public result")}</p>${link(signal.url, "Review source ↗")}<small>${escapeHtml((signal.matched_name_terms || []).join(", ") || "name needs confirmation")} · search-result evidence, not a confirmed company claim</small></div>`,
        )
        .join("")
    : "<p>No matching public hiring, startup, product, Clutch, or GoodFirms signal was retained.</p>";
  const reviews = otherReviews.length
    ? otherReviews
        .map(
          (source) =>
            `<div class="evidence"><b>${escapeHtml(source.title || source.source)}</b><p>${escapeHtml(source.snippet)}</p>${link(source.url, "Open result ↗")}<small>Search-result snippet · unverified</small></div>`,
        )
        .join("")
    : "<p>No additional Yelp, BBB, Facebook, Angi, or Houzz result was retained.</p>";
  return intelligenceSection(
    "Second-round verification",
    "Website, reviews, social, ads, market activity and email quality",
    `${overview}${intelligenceSubsection("Technographic evidence", technographics)}${intelligenceSubsection("Email organization", emails, true)}${intelligenceSubsection(`Published social profiles · ${socials.length}`, profiles)}${intelligenceSubsection("Advertising signals", advertising)}${intelligenceSubsection(`Hiring, startup & marketplace signals · ${marketSignals.length}`, marketPresence)}${intelligenceSubsection(`Other public review sources · ${otherReviews.length}`, reviews)}`,
    false,
    report.status.replaceAll("_", " "),
  );
}
function socialDiscoveryDetails(r) {
  const discovery = {
    ...parseObject(parseObject(r.verification).social_discovery),
  };
  discovery.error =
    discovery.error ||
    discovery.browser_checkpoint ||
    (discovery.fallback_error
      ? `Fallback note: ${discovery.fallback_error}`
      : "");
  discovery.query = [discovery.query, ...(discovery.targeted_queries || [])]
    .filter(Boolean)
    .join(" · ");
  const candidates = Array.isArray(discovery.candidates)
    ? discovery.candidates
    : [];
  if (!discovery.status) return "";
  const body = `<p><b>${escapeHtml(String(discovery.status).replaceAll("_", " "))}</b> · ${candidates.length} candidate${candidates.length === 1 ? "" : "s"}</p>${discovery.error ? `<p class="notice">${escapeHtml(discovery.error)}</p>` : ""}${intelligenceSubsection("Exact query and candidate evidence", `<p>${escapeHtml(discovery.query || "Query unavailable")}</p>${link(discovery.search_url, "Open the saved Google search ↗")}${candidates.map((item) => `<div class="evidence"><b>${escapeHtml(String(item.kind || "source").replaceAll("_", " "))} · ${Math.round(Number(item.confidence || 0) * 100)}% candidate match</b><p>${escapeHtml(item.title || item.excerpt || "No result title")}</p>${link(item.url, "Review candidate ↗")}<small>${escapeHtml(item.confirmation_state || "candidate needs review")} · ${escapeHtml(item.source || "google chrome result")}</small></div>`).join("") || "<p>No candidate result was retained.</p>"}`)}`;
  return intelligenceSection(
    "Chrome web social discovery",
    "Targeted public-profile search and candidate comparison",
    body,
    false,
    `${candidates.length} found`,
  );
}
function parseObject(value) {
  try {
    const data = typeof value === "string" ? JSON.parse(value || "{}") : value;
    return data && typeof data === "object" && !Array.isArray(data) ? data : {};
  } catch {
    return {};
  }
}
function aiReviewDetails(r) {
  const analysis = parseObject(r.ai_analysis);
  const draft = parseObject(r.ai_draft);
  const compiler = parseObject(r.ai_compiler_output);
  const compilerMeta = parseObject(r.ai_compiler_metadata);
  const reasons = Array.isArray(analysis.reasons) ? analysis.reasons : [];
  const questions = Array.isArray(analysis.questions) ? analysis.questions : [];
  const message = aiReviewMessages.get(
    `${detailContext.jobId}:${detailContext.rowIndex}`,
  );
  const metadata = (value) =>
    `<p class="muted">${escapeHtml(value.model || "Local model")}${value.generated_at ? ` · ${escapeHtml(value.generated_at)}` : ""}${value.status ? ` · ${escapeHtml(value.status.replaceAll("_", " "))}` : ""}</p>`;
  const controls = `<p class="notice">The compiler rejects claims without an immutable evidence ID and literal source excerpt. Advisory outreach drafts still require your review.</p><div class="actions"><button id="aiReviewButton" class="secondary" type="button" ${detailContext.rowIndex < 0 ? "disabled" : ""}>Review + draft</button><button id="aiCompileButton" class="secondary" type="button" ${detailContext.rowIndex < 0 ? "disabled" : ""}>Compile strict intelligence</button></div><p class="ai-explanation">Only this saved lead’s retained evidence is provided. ${active(job?.status) ? "Wait for this search to finish before requesting AI work." : "No email or browser action is available to the model."}</p><p id="aiReviewStatus" class="ai-task-status ${message?.error ? "is-error" : ""}" role="status">${escapeHtml(message?.text || (!aiReady() ? "Local AI is unavailable. Check its connection in the search panel; your saved data remains usable." : ""))}</p>`;
  const compilerBody = compiler.canonical_company_id
    ? `<p class="muted">${escapeHtml(compilerMeta.model || "Local model")} · ${escapeHtml(compilerMeta.validation || "validated")}</p><div class="detail-grid"><div><strong>Canonical company</strong>${escapeHtml(compiler.canonical_company_id)}</div><div><strong>Contact state</strong>${escapeHtml(String(compiler.contact_readiness?.deliverability_state || "unknown").replaceAll("_", " "))}</div><div><strong>Outreach eligible</strong>${compiler.contact_readiness?.eligible_for_outreach ? "Yes" : "No"}</div><div><strong>Next action</strong>${escapeHtml(String(compiler.next_best_action?.queue_state || "manual review").replaceAll("_", " "))}</div><div><strong>Material change</strong>${compiler.semantic_change_summary?.is_material_change ? "Yes" : "No"}</div></div><p>${escapeHtml(compiler.next_best_action?.rationale || "")}</p>`
    : "<p>No strict AI compilation saved yet.</p>";
  const interpretationBody = analysis.status
    ? `${metadata(analysis)}<p><b>Interpretation:</b> ${escapeHtml(analysis.summary || "No summary returned.")}</p>${analysis.fit ? `<p><b>Suggested fit:</b> ${escapeHtml(analysis.fit)}</p>` : ""}${analysis.disclaimer ? `<p class="muted">${escapeHtml(analysis.disclaimer)}</p>` : ""}`
    : "<p>No advisory AI review recorded for this lead.</p>";
  const evidenceBody = reasons.length
    ? reasons
        .map(
          (reason) =>
            `<div class="evidence">${reason.quote ? `<p>“${escapeHtml(reason.quote)}”</p>` : ""}${reason.note ? `<p>${escapeHtml(reason.note)}</p>` : ""}${link(reason.url, "Check cited source ↗")}<small>${escapeHtml(reason.source_id || "")}</small></div>`,
        )
        .join("")
    : "<p>No supporting source quotations returned.</p>";
  const questionsBody = questions.length
    ? `<ul>${questions.map((question) => `<li>${escapeHtml(question)}</li>`).join("")}</ul>`
    : "<p>No unresolved model questions were saved.</p>";
  const draftBody = draft.status
    ? `${metadata(draft)}${draft.status === "needs_offer" ? "<p>Add your real offer in the search panel, then request a review again to prepare a draft. No offer is invented for you.</p>" : ""}${draft.subject ? `<p><b>Subject:</b> ${escapeHtml(draft.subject)}</p>` : ""}${draft.body ? `<div class="ai-draft-body">${escapeHtml(draft.body)}</div>` : "<p>No usable outreach draft recorded.</p>"}${draft.disclaimer ? `<p class="muted">${escapeHtml(draft.disclaimer)}</p>` : ""}`
    : "<p>No outreach draft has been prepared.</p>";
  const body = `${controls}${intelligenceSubsection("Validated strict compiler output", compilerBody, true)}${intelligenceSubsection("AI interpretation", interpretationBody)}${intelligenceSubsection(`Cited evidence · ${reasons.length}`, evidenceBody)}${intelligenceSubsection(`Unresolved questions · ${questions.length}`, questionsBody)}${intelligenceSubsection("Outreach draft · not sent", draftBody)}`;
  return `<details class="intel-accordion ai-review" open aria-labelledby="aiReviewHeading"><summary><span class="intel-summary-copy"><b id="aiReviewHeading">Local AI intelligence</b><small>Validated compilation, interpretation, citations and draft</small></span><span class="intel-summary-badge">${compiler.canonical_company_id ? "Compiled" : "Not compiled"}</span><span class="intel-chevron" aria-hidden="true">⌄</span></summary><div class="intel-accordion-body">${body}</div></details>`;
}
async function compileLeadWithAi() {
  if (!detailContext || aiBusy || !aiReady() || active(job?.status)) return;
  const target = { ...detailContext };
  const key = `${target.jobId}:${target.rowIndex}`;
  const report = (text, error = false) => {
    aiReviewMessages.set(key, { text, error });
    if (
      detailContext?.jobId === target.jobId &&
      detailContext?.rowIndex === target.rowIndex
    )
      aiMessage("aiReviewStatus", text, error);
  };
  aiBusy = true;
  syncAiControls();
  report("Validating immutable evidence with the local compiler…");
  try {
    await runAiTask(
      {
        task: "compile",
        model: $("aiModel").value,
        job_id: target.jobId,
        row_index: target.rowIndex,
      },
      report,
    );
    const saved = await api("/api/jobs/" + encodeURIComponent(target.jobId));
    historyPreviewCache.delete(target.jobId);
    report(
      "Strict compiler output saved; every retained signal passed citation validation.",
    );
    if (job?.id === target.jobId) {
      job = saved;
      renderJob();
      details(rows[target.rowIndex]);
    } else details(saved.rows?.[target.rowIndex], target);
  } catch (err) {
    report(err.message, true);
  } finally {
    aiBusy = false;
    syncAiControls();
  }
}
async function reviewLeadWithAi() {
  if (!detailContext || aiBusy || !aiReady() || active(job?.status)) return;
  const target = { ...detailContext };
  if (!target.jobId || target.rowIndex < 0) return;
  const key = `${target.jobId}:${target.rowIndex}`;
  const report = (text, error = false) => {
    aiReviewMessages.set(key, { text, error });
    if (
      detailContext?.jobId === target.jobId &&
      detailContext?.rowIndex === target.rowIndex
    )
      aiMessage("aiReviewStatus", text, error);
  };
  aiBusy = true;
  syncAiControls();
  report("Preparing this lead’s evidence for your local model…");
  try {
    await runAiTask(
      {
        task: "review",
        model: $("aiModel").value,
        job_id: target.jobId,
        row_index: target.rowIndex,
        offer: $("aiOffer").value.trim(),
      },
      (message) => report(message),
    );
    const saved = await api("/api/jobs/" + encodeURIComponent(target.jobId));
    historyPreviewCache.delete(target.jobId);
    report(
      "Review saved. Check its evidence and draft below. Nothing was sent.",
    );
    if (job?.id === target.jobId) {
      job = saved;
      renderJob();
      if (
        $("leadDialog").open &&
        detailContext?.jobId === target.jobId &&
        detailContext?.rowIndex === target.rowIndex
      )
        details(rows[target.rowIndex]);
    } else if (
      $("leadDialog").open &&
      detailContext?.jobId === target.jobId &&
      detailContext?.rowIndex === target.rowIndex
    ) {
      details(saved.rows?.[target.rowIndex], target);
    }
  } catch (err) {
    report(err.message, true);
  } finally {
    aiBusy = false;
    syncAiControls();
  }
}
function opportunityDetails(r) {
  let o = {};
  try {
    o = JSON.parse(r.opportunity || "{}");
  } catch {}
  const dimensions = Array.isArray(o.dimensions)
    ? o.dimensions
    : Object.entries(o.dimensions || {}).map(([key, d]) => ({ key, ...d }));
  const body = `<p>Decision-maker: ${escapeHtml(r.decision_maker || "Unknown")} ${escapeHtml(r.decision_maker_role || "")}</p>${r.reference_id ? `<p class="notice">Rechecked from a historical library entry dated ${escapeHtml(r.reference_as_of)}. Old contact details and scores were not copied into this result.</p>` : ""}<p>${o.status && o.status !== "not_requested" ? `${Number(o.supported_points || 0)}/100 supported opportunity points · ${Number(o.coverage || 0)}% of dimensions have evidence. Unknown dimensions receive no awarded points; this is not a conversion or budget prediction.` : "Offer scoring not requested or not assessed in this earlier run."}</p>${dimensions.length ? `<div class="table-wrap"><table><thead><tr><th>DIMENSION</th><th>WEIGHT</th><th>SUPPORTED SCORE</th><th>REASON</th></tr></thead><tbody>${dimensions.map((d) => `<tr><td>${escapeHtml(d.label || d.name || d.key)}</td><td>${Number(d.weight)}%</td><td>${d.value === null || d.value === undefined ? "Unknown" : `${Number(d.value)}/10`}</td><td>${escapeHtml(d.reason)}</td></tr>`).join("")}</tbody></table></div>` : ""}${intelligenceSubsection(
    "Published workflow signals",
    parseList(r.workflow_signals)
      .map(
        (s) =>
          `<div class="evidence"><b>${escapeHtml(s.kind.replaceAll("_", " "))} · published page claim</b><p>${escapeHtml(s.excerpt || s.value)}</p>${link(s.url)}</div>`,
      )
      .join("") ||
      "<p>No supported signals recorded. No visible tool does not mean no software, and a report does not prove manual work.</p>",
    true,
  )}${(o.assumptions || []).map((x) => `<p>Unresolved: ${escapeHtml(x)}</p>`).join("")}`;
  return intelligenceSection(
    "Workflow & offer research",
    "Decision-maker, opportunity dimensions and published workflow signals",
    body,
    true,
    `${Number(o.supported_points || 0)}/100`,
  );
}
function parseList(value) {
  try {
    return JSON.parse(value || "[]");
  } catch {
    return [];
  }
}
$("closeDialog").addEventListener("click", () => $("leadDialog").close());
function renderDiagnostics() {
  const root = job.root_cause_analysis;
  $("rootCauseSummary").innerHTML = root
    ? `<h3>Underlying-cause analysis</h3><p class="notice">${escapeHtml(root.conclusion)}</p><div class="chips"><span class="chip">Requested maximum: ${Number(root.requested_maximum || 0)}</span><span class="chip">Unique results: ${Number(root.unique_results || 0)}</span><span class="chip">Shortfall: ${Number(root.shortfall || 0)}</span><span class="chip">Maps queries attempted: ${Number(root.maps?.attempted_queries || 0)}</span><span class="chip">Merged duplicates: ${Number(root.deduplication?.merged_count || 0)}</span></div>${
        root.website_failure_summary
          ? `<h3>Website failure categories</h3><div class="chips">${Object.entries(
              root.website_failure_summary,
            )
              .map(
                ([kind, count]) =>
                  `<span class="chip">${escapeHtml(kind.replaceAll("_", " "))}: ${Number(count)}</span>`,
              )
              .join("")}</div>`
          : ""
      }${(root.causes || []).map((cause) => `<div class="evidence"><span class="badge">${escapeHtml(cause.kind.replaceAll("_", " "))}</span><b>${escapeHtml(cause.impact)}</b><small>${escapeHtml(cause.evidence)}</small>${cause.query ? `<small>Query: ${escapeHtml(cause.query)}</small>` : ""}</div>`).join("")}${root.deduplication?.merge_ledger?.length ? `<details><summary>Exact duplicate merge ledger</summary><pre>${escapeHtml(JSON.stringify(root.deduplication.merge_ledger, null, 2))}</pre></details>` : ""}<details><summary>Interpretation limits</summary>${(root.limits || []).map((x) => `<p>${escapeHtml(x)}</p>`).join("")}</details>`
    : `<h3>Underlying-cause analysis</h3><p>This earlier run does not contain the new cause report.</p>`;
  $("savedStrategy").innerHTML =
    "<details><summary>Five-stage strategy, platform research & executed queries</summary>" +
    strategyMarkup(job.strategy, job.events) +
    "</details>";
  $("qualitySummary").innerHTML = job.quality_report
    ? `<h3>Quality controller report</h3><div class="chips">${Object.entries(
        job.quality_report.missing_or_weak || {},
      )
        .map(
          ([flag, n]) =>
            `<span class="chip">${escapeHtml(flag.replaceAll("_", " "))}: ${n}</span>`,
        )
        .join(
          "",
        )}</div><p>${job.quality_report.possible_duplicates?.length || 0} possible duplicate pairs retained for review. ${job.quality_report.shared_operator_signals?.length || 0} shared-operator signals (review only, not proven common ownership).</p>${(job.quality_report.shared_operator_signals || []).map((s) => `<div class="evidence"><b>${escapeHtml(s.names.join(" / "))}</b><small>${escapeHtml(s.reason)}</small>${s.urls.map((x) => link(x)).join("")}</div>`).join("")}`
    : "<p>Qualification report was not recorded in this earlier run.</p>";
  $("providerCards").innerHTML = Object.entries(job.providers || {})
    .map(
      ([name, p]) =>
        `<div class="provider"><strong>${escapeHtml(name)}</strong><span class="badge">${escapeHtml(p.status)}</span><p>${p.count || 0} records · ${p.seconds || 0}s</p>${p.error ? `<p>${escapeHtml(p.error)}</p>` : ""}</div>`,
    )
    .join("");
  $("timeline").innerHTML = (job.events || [])
    .map(
      (e) =>
        `<div class="timeline-event ${e.level === "error" ? "error" : ""}"><div class="meta">${escapeHtml(new Date(e.time).toLocaleTimeString())} · ${escapeHtml(e.provider)} · ${escapeHtml(e.level)}</div><b>${escapeHtml(e.message)}</b>${Object.keys(e.details).length ? `<details><summary>Query / response details</summary><pre>${escapeHtml(JSON.stringify(e.details, null, 2))}</pre></details>` : ""}</div>`,
    )
    .join("");
}
function tab(mode) {
  $("tablePanel").classList.toggle("hidden", mode !== "results");
  $("verificationPanel").classList.toggle("hidden", mode !== "verification");
  $("diagnosticsPanel").classList.toggle("hidden", mode !== "diagnostics");
  $("resultsTab").setAttribute("aria-selected", String(mode === "results"));
  $("verificationTab").setAttribute(
    "aria-selected",
    String(mode === "verification"),
  );
  $("diagnosticsTab").setAttribute(
    "aria-selected",
    String(mode === "diagnostics"),
  );
}
$("resultsTab").addEventListener("click", () => tab("results"));
$("verificationTab").addEventListener("click", () => tab("verification"));
$("diagnosticsTab").addEventListener("click", () => tab("diagnostics"));

async function loadBrowserProfile() {
  try {
    const status = await api("/api/browser/status");
    const label = status.running
      ? "Open and reusable"
      : status.profile_exists
        ? "Saved profile ready; browser currently closed"
        : "Ready for first-time sign-in";
    const facebook =
      status.services?.facebook === false ? " Facebook is excluded." : "";
    const checkpoint = status.search_checkpoint || {};
    const checkpointText = checkpoint.paused
      ? ` Browser web search is paused until you resume it: ${checkpoint.reason}`
      : " Automated Google/Bing web search is disabled; verification uses the public-search fallback.";
    $("browserProfileStatus").textContent =
      `${label}. Your session stays in ${status.profile_path}.${facebook}${checkpointText}`;
    $("openFacebookProfile").disabled = status.services?.facebook === false;
    $("openFacebookProfile").textContent =
      status.services?.facebook === false
        ? "Facebook disabled"
        : "Open Facebook login";
    $("resumeBrowserSearch").disabled = !checkpoint.paused;
  } catch (err) {
    $("browserProfileStatus").textContent = err.message;
  }
}

async function openBrowserProfile(service) {
  const buttons = [
    "openFacebookProfile",
    "openLinkedInProfile",
    "openMapsProfile",
    "openAllProfiles",
  ];
  buttons.forEach((id) => ($(id).disabled = true));
  $("browserProfileStatus").textContent =
    "Opening your dedicated Chrome profile…";
  try {
    const status = await api("/api/browser/open", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ service }),
    });
    $("browserProfileStatus").textContent =
      status.message +
      " Complete any login or security check in Chrome yourself.";
  } catch (err) {
    $("browserProfileStatus").textContent = err.message;
  } finally {
    buttons.forEach((id) => ($(id).disabled = false));
  }
}
$("openFacebookProfile").addEventListener("click", () =>
  openBrowserProfile("facebook"),
);
$("openLinkedInProfile").addEventListener("click", () =>
  openBrowserProfile("linkedin"),
);
$("openMapsProfile").addEventListener("click", () =>
  openBrowserProfile("maps"),
);
$("openAllProfiles").addEventListener("click", () => openBrowserProfile("all"));
$("resumeBrowserSearch").addEventListener("click", async () => {
  $("resumeBrowserSearch").disabled = true;
  try {
    await api("/api/browser/open", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ service: "maps" }),
    });
    await api("/api/browser/clear-search-checkpoint", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    $("browserProfileStatus").textContent =
      "Google Maps opened and the saved pause was cleared. If a challenge appears, complete it in Chrome; the app will pause again instead of retrying.";
  } catch (err) {
    $("browserProfileStatus").textContent = err.message;
  } finally {
    await loadBrowserProfile();
  }
});

function renderVerification() {
  const reports = rows
    .map((row) => ({ row, report: parseObject(row.verification) }))
    .filter((item) => item.report.status)
    .sort((a, b) => {
      const match = (value) =>
        value === "service_match" ? 0 : value === "category_match" ? 1 : 2;
      return (
        match(a.row.match_status) - match(b.row.match_status) ||
        a.row.name.localeCompare(b.row.name)
      );
    });
  const summary = verificationTask?.summary || {};
  $("verificationStats").innerHTML = [
    ["Verified", summary.verified ?? reports.length],
    [
      "Websites reachable",
      summary.websites_reachable ??
        reports.filter((x) => x.report.website?.status === "reachable").length,
    ],
    [
      "Social profiles",
      summary.social_profiles_listed ??
        reports.filter((x) =>
          Object.values(x.report.socials || {}).some((v) => v.url),
        ).length,
    ],
    [
      "Ad tracking signals",
      summary.ad_tracking_signals ??
        reports.filter((x) => x.report.ads?.tracking_signals?.length).length,
    ],
    [
      "Extra review sources",
      summary.review_sources_found ??
        reports.filter((x) => x.report.reviews?.other_sources?.length).length,
    ],
    [
      "Duplicates consolidated",
      summary.duplicates_consolidated ??
        job?.organization?.duplicates_consolidated ??
        0,
    ],
    [
      "Recommended emails",
      summary.recommended_email_records ??
        job?.organization?.recommended_email_records ??
        0,
    ],
    ["Contacts restored", summary.contacts_restored_from_memory ?? 0],
    [
      "Chrome social candidates",
      summary.chrome_social_candidates ??
        reports.reduce(
          (total, item) =>
            total + (item.report.social_discovery?.candidates?.length || 0),
          0,
        ),
    ],
    [
      "Browser checkpoints",
      summary.chrome_manual_checkpoints ??
        reports.filter((item) =>
          String(item.report.social_discovery?.status || "").startsWith(
            "manual_checkpoint",
          ),
        ).length,
    ],
  ]
    .map(
      ([label, value]) =>
        `<span class="chip">${label}: ${Number(value) || 0}</span>`,
    )
    .join("");
  $("verificationList").innerHTML = reports.length
    ? reports
        .map(({ row, report }) => {
          const originalIndex = rows.indexOf(row);
          const socialCount = Object.values(report.socials || {}).filter(
            (value) => value.url,
          ).length;
          const reviewCount = report.reviews?.google_maps?.review_count || 0;
          const tracking = report.ads?.tracking_signals?.length || 0;
          return `<article class="verification-item"><div><b>${escapeHtml(row.name)}</b><small>${escapeHtml(row.address || row.city)}</small><span class="badge ${row.match_status === "candidate" ? "candidate" : ""}">${escapeHtml((row.match_status || "candidate").replaceAll("_", " "))}</span></div><div><strong>Email</strong><span>${recommendedEmail(row) ? "Recommended" : row.email ? "Excluded / review" : "Not found"}</span></div><div><strong>Website</strong><span>${escapeHtml((report.website?.status || "unknown").replaceAll("_", " "))}</span></div><div><strong>Social</strong><span>${socialCount} published link${socialCount === 1 ? "" : "s"}</span></div><div><strong>Ads</strong><span>${tracking ? `${tracking} tracking signal${tracking === 1 ? "" : "s"}` : "Campaign not verified"}</span></div><div><strong>Reviews</strong><span>${escapeHtml(report.reviews?.google_maps?.rating || "—")} · ${escapeHtml(reviewCount)}</span></div><button class="secondary verification-detail" data-index="${originalIndex}">Details + local AI</button></article>`;
        })
        .join("")
    : "<p>No second-round reports are saved for this search yet.</p>";
  document
    .querySelectorAll(".verification-detail")
    .forEach((button) =>
      button.addEventListener("click", () =>
        details(rows[Number(button.dataset.index)]),
      ),
    );
  const running =
    verificationTask && ["queued", "running"].includes(verificationTask.status);
  $("startVerification").disabled = !job || active(job.status) || running;
  $("verificationScope").disabled = running;
  $("verificationProgress").value = verificationTask?.progress || 0;
  const selectedScope = $("verificationScope").value;
  const unfinished = (row) => {
    const report = parseObject(row.verification);
    const discoveryStatus = String(report.social_discovery?.status || "");
    return (
      report.status !== "complete" ||
      !discoveryStatus ||
      ["cancelled", "failed", "not_run"].includes(discoveryStatus)
    );
  };
  const selectedCount =
    selectedScope === "all"
      ? rows.length
      : selectedScope === "unfinished"
        ? rows.filter(unfinished).length
        : rows.filter((row) => row.match_status !== "candidate").length;
  $("startVerification").textContent =
    `Verify ${selectedCount} of ${rows.length} leads`;
  $("verificationStatus").textContent =
    verificationTask?.message ||
    (reports.length
      ? `${reports.length} saved verification reports. The selected rerun will verify ${selectedCount} of ${rows.length} retained leads.`
      : `Ready to verify ${selectedCount} of ${rows.length} retained leads.`);
}

async function pollVerification(taskId) {
  try {
    verificationTask = await api(
      `/api/verification/tasks/${encodeURIComponent(taskId)}`,
    );
    renderVerification();
    if (["queued", "running"].includes(verificationTask.status)) {
      verificationPollTimer = setTimeout(() => pollVerification(taskId), 1200);
      return;
    }
    job = await api(`/api/jobs/${encodeURIComponent(job.id)}`);
    rows = job.rows || [];
    campaignJobsLoaded = false;
    library = null;
    renderJob();
  } catch (err) {
    $("verificationStatus").textContent = err.message;
    $("startVerification").disabled = false;
  }
}

$("startVerification").addEventListener("click", async () => {
  if (!job || active(job.status)) return;
  clearTimeout(verificationPollTimer);
  $("startVerification").disabled = true;
  $("verificationStatus").textContent = "Preparing second-round verification…";
  try {
    const created = await api("/api/verification/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_id: job.id,
        scope: $("verificationScope").value,
      }),
    });
    await pollVerification(created.id);
  } catch (err) {
    $("verificationStatus").textContent = err.message;
    $("startVerification").disabled = false;
  }
});
$("verificationScope").addEventListener("change", renderVerification);
for (const id of [
  "filter",
  "contactFilter",
  "sort",
  "operatorFilter",
  "evidenceFilter",
  "qualificationSort",
  "opportunityFilter",
])
  $(id).addEventListener(id === "filter" ? "input" : "change", renderRows);
$("filteredCsv").addEventListener("click", () => {
  const columns = [
    "name",
    "phone",
    "email",
    "website",
    "address",
    "city",
    "score",
    "match_status",
    "source_url",
    "profile_url",
    "operator_type",
    "operator_confidence",
    "operator_evidence",
    "evidence_score",
    "source_strength",
    "facts",
    "assumptions",
    "quality_flags",
    "discovery_query",
    "decision_maker",
    "decision_maker_role",
    "research_profile",
    "workflow_signals",
    "opportunity_score",
    "opportunity",
    "reference_id",
    "reference_as_of",
    "ai_analysis",
    "ai_draft",
  ];
  const cell = (v) =>
    '"' +
    String(v ?? "")
      .replace(/^[\s]*[=+@-]/, (x) => "'" + x)
      .replaceAll('"', '""') +
    '"';
  const csv =
    "\ufeff" +
    [
      columns.map(cell).join(","),
      ...visible.map((r) => columns.map((k) => cell(r[k])).join(",")),
    ].join("\r\n");
  const url = URL.createObjectURL(
    new Blob([csv], { type: "text/csv;charset=utf-8;" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = "filtered-leads.csv";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
async function loadHistory() {
  const revision = ++historyRevision;
  try {
    const saved = await api("/api/jobs");
    if (revision !== historyRevision) return;
    historyJobs = saved;
    const groups = new Map();
    for (const run of historyJobs) {
      const name = String(run.params?.niche || "Untitled research")
        .trim()
        .replace(/\s+/g, " ");
      const key = name.toLocaleLowerCase();
      if (!groups.has(key)) groups.set(key, { name, runs: [] });
      groups.get(key).runs.push(run);
    }
    $("historyBadge").textContent = groups.size;
    $("historyBadge").title =
      `${groups.size} research groups · ${historyJobs.length} saved runs`;
    $("historyList").innerHTML = historyJobs.length
      ? Array.from(groups, ([key, group]) => {
          const total = group.runs.reduce(
            (n, r) => n + (Number(r.count) || 0),
            0,
          );
          const locations = Array.from(
            new Set(group.runs.map((r) => r.params?.location).filter(Boolean)),
          );
          return `<details class="history-group" data-group="${escapeHtml(key)}" ${openHistoryGroups.has(key) ? "open" : ""}><summary><span class="history-group-title">${escapeHtml(group.name)}</span><span class="history-group-meta">${group.runs.length} saved ${group.runs.length === 1 ? "run" : "runs"} · ${total} results across runs</span><span class="history-group-places">${escapeHtml(locations.slice(0, 3).join(" · "))}${locations.length > 3 ? ` · +${locations.length - 3} more` : ""}</span></summary><div class="history-runs">${group.runs.map((j) => `<article class="history-item" data-history-id="${escapeHtml(j.id)}"><div class="history-run-heading"><div><h2>${escapeHtml(j.params?.location || "Location not recorded")}</h2><p>${escapeHtml(new Date(j.created_at).toLocaleString())} · ${escapeHtml((j.params?.source || "source not recorded").replaceAll("_", " "))}</p><span class="badge">${escapeHtml(j.status)} · ${Number(j.count) || 0} businesses</span></div><button class="secondary history-open" data-id="${escapeHtml(j.id)}">Open search →</button></div><div class="history-preview" data-preview-id="${escapeHtml(j.id)}" aria-live="polite"><p>Expand this research group to see what was scraped.</p></div></article>`).join("")}<p class="fine-print">Results across runs can overlap. Each saved run and its original evidence stay separate.</p></div></details>`;
        }).join("")
      : '<div class="card search-card"><h2>No searches yet.</h2><p>Your first search will appear here automatically.</p></div>';
    $("historyList")
      .querySelectorAll(".history-group")
      .forEach((detail) => {
        const load = () => {
          if (detail.open) {
            openHistoryGroups.add(detail.dataset.group);
            loadHistoryPreviews(detail);
          } else openHistoryGroups.delete(detail.dataset.group);
        };
        detail.addEventListener("toggle", load);
        if (detail.open) load();
      });
    document.querySelectorAll(".history-open").forEach((b) =>
      b.addEventListener("click", async () => {
        clearTimeout(pollTimer);
        jobId = b.dataset.id;
        localStorage.setItem("leadfinder.lastJob", jobId);
        await poll();
        location.hash = "results";
      }),
    );
  } catch (err) {
    if (revision === historyRevision)
      $("historyList").innerHTML =
        `<p class="notice" role="alert">Could not load search history: ${escapeHtml(err.message)}. Reopen History to retry.</p>`;
  }
}
function historyPreviewMarkup(saved) {
  const records = Array.isArray(saved.rows) ? saved.rows : [];
  if (!records.length)
    return `<p class="notice">${escapeHtml(saved.diagnosis || saved.message || "No businesses were collected in this run.")}</p>`;
  const list = (rows) =>
    `<ul class="history-businesses">${rows.map((r) => `<li><div><b>${escapeHtml(r.name || "Unnamed business")}</b><small>${escapeHtml(r.address || r.city || "Location not recorded")}</small></div><div class="history-business-contacts"><span>${escapeHtml(r.phone) || "Phone not found"}</span><span>${escapeHtml(r.email) || "Email not found"}</span></div><div class="history-business-links">${r.website ? link(r.website, "Website ↗") : ""}${r.source_url ? link(r.source_url, "Source ↗") : ""}${r.profile_url && r.profile_url !== r.source_url ? link(r.profile_url, "Seller profile ↗") : ""}</div></li>`).join("")}</ul>`;
  const remaining =
    records.length > 5
      ? `<details class="history-more"><summary>Show remaining ${records.length - 5} businesses</summary>${list(records.slice(5))}</details>`
      : "";
  return `<p class="history-preview-note">Scraped businesses · Showing ${Math.min(records.length, 5)} of ${records.length}. Open search for filters, exports and diagnostics.</p>${list(records.slice(0, 5))}${remaining}`;
}
async function loadHistoryPreviews(detail) {
  const queue = Array.from(detail.querySelectorAll(".history-preview"));
  async function worker() {
    while (queue.length && detail.isConnected && detail.open) {
      const container = queue.shift();
      const id = container.dataset.previewId;
      const run = historyJobs.find((j) => j.id === id);
      if (!run) continue;
      const signature = `${id}:${run.status}:${run.count}`;
      let cached = historyPreviewCache.get(signature);
      try {
        if (!cached || active(run.status)) {
          container.innerHTML = "<p>Loading scraped businesses…</p>";
          if (!historyPreviewPending.has(signature)) {
            const request = api("/api/jobs/" + encodeURIComponent(id))
              .then((saved) => {
                const markup = historyPreviewMarkup(saved);
                if (!active(saved.status))
                  historyPreviewCache.set(signature, markup);
                return markup;
              })
              .finally(() => historyPreviewPending.delete(signature));
            historyPreviewPending.set(signature, request);
          }
          cached = await historyPreviewPending.get(signature);
        }
        if (container.isConnected) container.innerHTML = cached;
      } catch (err) {
        if (container.isConnected)
          container.innerHTML = `<p class="notice" role="alert">Could not load this run: ${escapeHtml(err.message)}. Collapse and expand the group to retry.</p>`;
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(3, queue.length) }, worker));
}
async function loadLibrary() {
  try {
    [library, intelligenceOverview, intelligenceQueue, nichePacks] =
      await Promise.all([
        api("/api/library"),
        api("/api/intelligence/overview"),
        api("/api/intelligence/queue"),
        api("/api/intelligence/niche-packs"),
      ]);
    $("librarySummary").textContent =
      `${library.collections?.length || 0} compiled research collection${library.collections?.length === 1 ? "" : "s"} · ${library.compiled_record_count || 0} organized current prospects · ${library.record_count || 0} historical references retained separately.`;
    renderLibrary();
    renderIntelligence();
    renderNichePacks();
  } catch (err) {
    $("librarySummary").textContent = err.message;
  }
}
function renderIntelligence() {
  if (!$("intelligenceStats")) return;
  const overview = intelligenceOverview || {};
  $("intelligenceStats").innerHTML = [
    ["Canonical companies", overview.companies],
    ["Contacts remembered", overview.contacts],
    ["Evidence claims", overview.evidence_claims],
    ["Changes detected", overview.changes_detected],
    ["Niche packs", overview.niche_packs],
    ["Campaign experiments", overview.experiments],
    ["Positive outcomes", overview.performance?.positive_outcomes],
    ["Websites monitored", overview.watcher?.scheduled],
  ]
    .map(
      ([label, value]) =>
        `<span class="chip">${label}: ${Number(value) || 0}</span>`,
    )
    .join("");
  const items = (intelligenceQueue || [])
    .filter((item) => item.status === "open")
    .slice(0, 12);
  if ($("nextActionCount")) {
    const total = (intelligenceQueue || []).filter(
      (item) => item.status === "open",
    ).length;
    $("nextActionCount").textContent =
      `${total} prioritized action${total === 1 ? "" : "s"} · expand only when needed`;
  }
  $("intelligenceQueue").innerHTML = items.length
    ? items
        .map(
          (item, index) =>
            `<article class="intelligence-action"><div><b>${escapeHtml(item.name)}</b><small>${escapeHtml([item.city, item.niche].filter(Boolean).join(" · "))}</small></div><span class="badge ${item.action === "ready_for_outreach" ? "" : "candidate"}">${escapeHtml(item.action.replaceAll("_", " "))}</span><p>${escapeHtml(item.reason)}</p><div class="intelligence-actions"><button class="ghost small intelligence-detail" type="button" data-index="${index}" aria-label="View intelligence details for ${escapeHtml(item.name)}">Details</button>${item.lead?.website || item.lead?.linkedin ? `<button class="ghost small intelligence-browser" type="button" data-index="${index}">Open review</button>` : ""}${item.action === "manual_browser_review" ? `<button class="ghost small intelligence-complete" type="button" data-index="${index}">Mark reviewed</button>` : ""}</div></article>`,
        )
        .join("")
    : "<p>Complete a verification round to create the first next-action queue.</p>";
  document.querySelectorAll(".intelligence-detail").forEach((button) =>
    button.addEventListener("click", () => {
      const item = items[Number(button.dataset.index)];
      details(item?.lead, { jobId: "", rowIndex: -1 });
    }),
  );
  document.querySelectorAll(".intelligence-browser").forEach((button) =>
    button.addEventListener("click", async () => {
      const item = items[Number(button.dataset.index)];
      button.disabled = true;
      try {
        await api("/api/browser/open-url", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            company_id: item.company_id,
            url: item.lead.linkedin || item.lead.website,
          }),
        });
        toast("Opened in your persistent research browser.");
      } catch (err) {
        toast(err.message, "error");
      } finally {
        button.disabled = false;
      }
    }),
  );
  document.querySelectorAll(".intelligence-complete").forEach((button) =>
    button.addEventListener("click", async () => {
      const item = items[Number(button.dataset.index)];
      button.disabled = true;
      try {
        await api("/api/intelligence/browser-checkpoints", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            company_id: item.company_id,
            service: item.lead.linkedin ? "linkedin" : "website",
            url:
              item.lead.linkedin || item.lead.website || item.lead.source_url,
            status: "complete",
            detail: "Marked reviewed by the user from the next-action queue.",
          }),
        });
        intelligenceQueue = await api("/api/intelligence/queue");
        renderIntelligence();
        toast("Review checkpoint saved and next action recalculated.");
      } catch (err) {
        toast(err.message, "error");
        button.disabled = false;
      }
    }),
  );
}
function listField(value) {
  return String(value || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}
function renderNichePacks() {
  const select = $("nichePackSelect");
  if (!select) return;
  const current = select.value;
  select.innerHTML = nichePacks
    .map(
      (pack, index) =>
        `<option value="${index}">${escapeHtml(pack.name)}</option>`,
    )
    .join("");
  if (current && Number(current) < nichePacks.length) select.value = current;
  showNichePack();
}
function showNichePack() {
  const pack = nichePacks[Number($("nichePackSelect").value)] || nichePacks[0];
  if (!pack) return;
  $("nichePackName").value = pack.name || "";
  $("nichePackSynonyms").value = (pack.synonyms || []).join("\n");
  $("nichePackExclusions").value = (pack.exclusions || []).join("\n");
  $("nichePackRoles").value = (pack.decision_maker_roles || []).join("\n");
  $("nichePackSignals").value = (pack.opportunity_signals || []).join("\n");
  $("nichePackMethods").value = (pack.search_methods || []).join("\n");
  $("nichePackTechnologies").value = (pack.technology_signals || []).join("\n");
  $("nichePackReviewSignals").value = (pack.review_signals || []).join("\n");
  $("nichePackStatus").textContent =
    `${pack.generated_by === "user_approved" ? "User-approved" : "Local deterministic"} pack · ${(pack.search_methods || []).length} research methods · ${(pack.technology_signals || []).length} technology signals · ${(pack.review_signals || []).length} review signals.`;
}
$("nichePackSelect").addEventListener("change", showNichePack);
$("nichePackForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const selected = nichePacks[Number($("nichePackSelect").value)] || {};
  try {
    await api("/api/intelligence/niche-packs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...selected,
        name: $("nichePackName").value,
        synonyms: listField($("nichePackSynonyms").value),
        exclusions: listField($("nichePackExclusions").value),
        decision_maker_roles: listField($("nichePackRoles").value),
        opportunity_signals: listField($("nichePackSignals").value),
        search_methods: listField($("nichePackMethods").value),
        technology_signals: listField($("nichePackTechnologies").value),
        review_signals: listField($("nichePackReviewSignals").value),
      }),
    });
    nichePacks = await api("/api/intelligence/niche-packs");
    renderNichePacks();
    $("nichePackStatus").textContent =
      "Niche pack saved. New searches and local-AI planning will use these methods and terminology.";
  } catch (err) {
    $("nichePackStatus").textContent = err.message;
  }
});
function renderLibrary() {
  const query = $("libraryFilter").value.toLowerCase();
  const collections = (library?.collections || [])
    .map((collection) => {
      const collectionMatch = [
        collection.title,
        collection.niche,
        collection.location,
      ]
        .join(" ")
        .toLowerCase()
        .includes(query);
      return {
        ...collection,
        visibleRows: (collection.rows || []).filter(
          (row) =>
            collectionMatch ||
            JSON.stringify(row).toLowerCase().includes(query),
        ),
      };
    })
    .filter((collection) => collection.visibleRows.length);
  const records = (library?.records || []).filter((r) =>
    JSON.stringify(r).toLowerCase().includes(query),
  );
  const sort = $("librarySort").value;
  records.sort((a, b) =>
    sort === "name"
      ? a.name.localeCompare(b.name)
      : sort === "score"
        ? Number(b.historical_score ?? -1) - Number(a.historical_score ?? -1) ||
          a.name.localeCompare(b.name)
        : sort === "recheck"
          ? Number(Boolean(b.warnings?.length)) -
              Number(Boolean(a.warnings?.length)) ||
            a.name.localeCompare(b.name)
          : [a.city, a.state, a.name]
              .join(" ")
              .localeCompare([b.city, b.state, b.name].join(" ")),
  );
  const card = (r) =>
    `<article class="reference-item"><div class="reference-heading"><div class="check-row"><input type="checkbox" class="reference-select" id="ref-${escapeHtml(r.id)}" data-id="${escapeHtml(r.id)}" ${selectedReferences.has(r.id) ? "checked" : ""}/><label for="ref-${escapeHtml(r.id)}">${escapeHtml(r.name)}<small>${escapeHtml([r.city, r.state].filter(Boolean).join(", "))}</small></label></div><span class="badge candidate">Historical · not reverified</span></div><p>${link(r.website)}<br>${escapeHtml(r.phone) || "Phone unknown"} · ${escapeHtml(r.email) || "Email unknown"}</p><p>Decision-maker (historical): ${escapeHtml(r.decision_maker || "Unknown")}${r.historical_score !== null && r.historical_score !== undefined ? ` · Original manual score: ${Number(r.historical_score)}/10` : ""}</p>${r.warnings?.length ? `<p class="notice">${r.warnings.map(escapeHtml).join(" · ")}</p>` : ""}<details><summary>Original research & provenance</summary><p><b>Workflow:</b> ${escapeHtml(r.workflow || "Unknown")}</p><p><b>Tools:</b> ${escapeHtml(r.software || "Unknown")}</p><p>${escapeHtml(r.original_notes)}</p><p>Historical campaign status: ${escapeHtml(r.original_status || "Not recorded")}</p><p class="muted">Original notes may contain inference. They are preserved, not promoted to verified current facts.</p>${link(r.source_url, "Original cited website")}${(r.provenance || []).map((p) => `<div class="evidence"><small>${escapeHtml(p.source_file || p.file || p.path || "Source CSV")}</small><pre>${escapeHtml(JSON.stringify(p, null, 2))}</pre></div>`).join("")}</details></article>`;
  const compiledCard = (r, collection, rowIndex) =>
    `<article class="reference-item compiled-item"><div class="reference-heading"><div><b>${escapeHtml(r.name || "Unnamed business")}</b><small>${escapeHtml(r.address || r.city || "Location not recorded")}</small></div><div><span class="badge">${Number(r.score) || 0}/100</span>${emailQualityBadge(r)}</div></div><p>${escapeHtml(r.phone) || "Phone unknown"} · ${escapeHtml(r.email) || "Email unknown"}<br>${link(r.website, "Website ↗")} ${link(r.source_url, "Primary source ↗")}</p><p><b>${escapeHtml((r.operator_type || "not assessed").replaceAll("_", " "))}</b> · ${escapeHtml((r.match_status || "not assessed").replaceAll("_", " "))} · ${parseList(r.duplicate_summary).length} duplicate source${parseList(r.duplicate_summary).length === 1 ? "" : "s"} merged</p>${r.next_best_action ? `<p><span class="badge candidate">Next: ${escapeHtml(r.next_best_action.replaceAll("_", " "))}</span> · Contact confidence ${Number(r.contact_confidence) || 0}/100</p>` : ""}<button class="secondary library-detail" type="button" data-job="${escapeHtml(collection.job_id)}" data-row="${rowIndex}" aria-label="View research details for ${escapeHtml(r.name || "prospect")}">Details</button></article>`;
  const compiledMarkup = collections.length
    ? `<section class="library-section"><div class="library-section-heading"><div><span class="eyebrow">COMPILED RESEARCH</span><h2>Finished, verified collections</h2></div><p>Canonical prospects with evidence, duplicate lineage, email quality, reviews, social profiles, ads signals and AI notes kept together.</p></div>${collections
        .map((collection) => {
          const organization = collection.organization || {};
          return `<details class="library-group compiled-collection"><summary><span><b>${escapeHtml(collection.title)}</b><small>${escapeHtml(
            String(collection.created_at || "")
              .replace("T", " ")
              .slice(0, 16),
          )}</small></span><span>${collection.visibleRows.length} organized prospect${collection.visibleRows.length === 1 ? "" : "s"} · ${Number(organization.duplicates_consolidated) || 0} duplicates merged · ${Number(organization.recommended_email_records) || 0} recommended emails</span></summary><div class="compiled-collection-actions"><button class="ghost small library-open-run" type="button" data-job="${escapeHtml(collection.job_id)}">Open full run & diagnostics</button><span class="muted">Email AI: ${escapeHtml(String(organization.ai_status || "not used").replaceAll("_", " "))}</span></div><div class="compiled-rows">${collection.visibleRows.map((r) => compiledCard(r, collection, (collection.rows || []).indexOf(r))).join("")}</div></details>`;
        })
        .join("")}</section>`
    : `<section class="library-section"><div class="library-section-heading"><div><span class="eyebrow">COMPILED RESEARCH</span><h2>No compiled collections yet</h2></div><p>Finish a search and its verification round. The organized result will appear here automatically.</p></div></section>`;
  const group = $("libraryGroup").value;
  let historicalMarkup = "";
  if (group === "none") {
    historicalMarkup =
      records.map(card).join("") ||
      "<p>No historical references match this filter.</p>";
  } else {
    const grouped = new Map();
    for (const record of records) {
      const key =
        group === "state"
          ? record.state || "State not recorded"
          : [record.city, record.state].filter(Boolean).join(", ") ||
            "City not recorded";
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(record);
    }
    historicalMarkup =
      [...grouped.entries()]
        .map(
          ([label, items]) =>
            `<details class="library-group" ${query ? "open" : ""}><summary>${escapeHtml(label)} · ${items.length} prospect${items.length === 1 ? "" : "s"}</summary><div>${items.map(card).join("")}</div></details>`,
        )
        .join("") || "<p>No historical references match this filter.</p>";
  }
  $("libraryList").innerHTML =
    `${compiledMarkup}<section class="library-section historical-library"><div class="library-section-heading"><div><span class="eyebrow">HISTORICAL IMPORT</span><h2>Original reference research</h2></div><p>Preserved with source provenance and kept separate from current compiled results.</p></div>${historicalMarkup}</section>`;
  document.querySelectorAll(".library-detail").forEach((button) =>
    button.addEventListener("click", () => {
      const collection = (library?.collections || []).find(
        (item) => item.job_id === button.dataset.job,
      );
      const rowIndex = Number(button.dataset.row);
      details(collection?.rows?.[rowIndex], {
        jobId: button.dataset.job,
        rowIndex,
      });
    }),
  );
  document.querySelectorAll(".library-open-run").forEach((button) =>
    button.addEventListener("click", async () => {
      clearTimeout(pollTimer);
      jobId = button.dataset.job;
      localStorage.setItem("leadfinder.lastJob", jobId);
      await poll();
      location.hash = "results";
    }),
  );
  document.querySelectorAll(".reference-select").forEach((input) =>
    input.addEventListener("change", () => {
      input.checked
        ? selectedReferences.add(input.dataset.id)
        : selectedReferences.delete(input.dataset.id);
      $("libraryAction").textContent =
        `${selectedReferences.size} websites selected.`;
    }),
  );
}
$("libraryFilter").addEventListener("input", renderLibrary);
$("libraryGroup").addEventListener("change", renderLibrary);
$("librarySort").addEventListener("change", renderLibrary);
$("urls").addEventListener("input", () => {
  preparedReferenceIds = [];
});
$("prepareRecheck").addEventListener("click", () => {
  const chosen = (library?.records || []).filter(
    (r) => selectedReferences.has(r.id) && safeUrl(r.website),
  );
  if (!chosen.length || chosen.length > 100) {
    $("libraryAction").textContent =
      "Select between 1 and 100 websites to recheck.";
    return;
  }
  preparedReferenceIds = chosen.map((r) => r.id);
  $("urls").value = chosen.map((r) => r.website).join("\n");
  $("urls").closest("details").open = true;
  $("niche").value = "Hood Cleaning";
  $("location").value = Array.from(
    new Set(chosen.map((r) => [r.city, r.state].filter(Boolean).join(", "))),
  )
    .slice(0, 5)
    .join("\n");
  $("source").value = "websites";
  $("researchProfile").value = "hood_automation";
  $("coverage").value = "exact";
  $("limit").value = chosen.length;
  $("enrich").checked = true;
  $("formError").textContent = "";
  location.hash = "discover";
  $("profileHelp").textContent =
    `${chosen.length} historical websites prepared. Each retains its original city; only new page evidence will enter the fresh result. Click Find businesses when ready.`;
  updatePlan();
  $("searchForm").scrollIntoView({ behavior: "smooth" });
});
const CAMPAIGN_STATUS_LABELS = {
  draft: "Ready for review",
  drafting: "AI drafting",
  running: "Sending",
  paused: "Paused",
  complete: "Complete",
};
const MESSAGE_STATUS_LABELS = {
  draft: "Draft",
  queued: "Queued",
  drafting: "Drafting",
  draft_failed: "Needs attention",
  sent: "Sent",
  failed: "Failed",
};
const TEMPLATE_VARIABLES = [
  "business_name",
  "niche",
  "city",
  "website",
  "ai_summary",
  "unsubscribe",
];

function toast(message, kind = "ok") {
  const node = document.createElement("div");
  node.className = `toast toast-${kind}`;
  node.setAttribute("role", "status");
  node.textContent = message;
  document.body.append(node);
  setTimeout(() => node.classList.add("toast-out"), 3200);
  setTimeout(() => node.remove(), 3900);
}

function campaignTemplateNames(campaign) {
  const names = Array.isArray(campaign.template_names)
    ? campaign.template_names
    : campaign.template_name
      ? [campaign.template_name]
      : [];
  return names.filter(Boolean);
}
function campaignSourceName(campaign) {
  if (campaign.mode === "ai") return `Local AI · ${campaign.ai_model}`;
  const names = campaignTemplateNames(campaign);
  if (names.length > 1) return `${names.length} templates`;
  return names[0] || "Template";
}
function campaignStatusLabel(status) {
  return CAMPAIGN_STATUS_LABELS[status] || status;
}
function campaignTitle(campaign) {
  const source = campaignSourceName(campaign);
  const niche = campaign.niche || "Campaign";
  return niche && niche !== source ? `${niche} · ${source}` : source;
}
function campaignCreated(campaign) {
  return String(campaign.created_at || "")
    .replace("T", " ")
    .slice(0, 16);
}
function campaignMatchesFilter(campaign, term) {
  if (!term) return true;
  const haystack = [
    campaign.niche,
    campaignSourceName(campaign),
    campaignStatusLabel(campaign.status),
    campaignCreated(campaign),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(term);
}
function campaignProgress(campaign) {
  const total = Number(campaign.total || 0);
  const done = Number(campaign.sent || 0) + Number(campaign.failed || 0);
  return total ? Math.round((done / total) * 100) : 0;
}

/* ---------- Campaign board ---------- */

function renderCampaignList() {
  const list = $("campaignList");
  const term = $("campaignFilter").value.trim().toLowerCase();
  const items = outreachCampaigns.filter((item) =>
    campaignMatchesFilter(item, term),
  );
  if (!outreachCampaigns.length) {
    list.innerHTML = `<div class="empty-state"><span class="empty-icon">✉</span><b>No campaigns yet</b><p>Create one from your open search, or duplicate an angle across several templates.</p><button class="secondary" type="button" data-empty="compose">Compose a campaign</button></div>`;
    return;
  }
  if (!items.length) {
    list.innerHTML =
      '<div class="empty-state"><b>No campaign matches that filter</b><p>Try a niche, template name or status.</p></div>';
    return;
  }
  list.innerHTML = items
    .map((item) => {
      const selected = item.id === selectedCampaignId;
      const total = Number(item.total || 0);
      const sent = Number(item.sent || 0);
      const ready = Number(item.ready || 0);
      const attention =
        Number(item.failed || 0) + Number(item.draft_failed || 0);
      const live = ["running", "drafting"].includes(item.status);
      return `<button class="campaign-row${selected ? " is-selected" : ""}" type="button" role="option" aria-selected="${selected}" data-id="${escapeHtml(item.id)}">
        <span class="campaign-row-head">
          <span class="campaign-row-title">${live ? '<span class="live-dot" aria-hidden="true"></span>' : ""}${escapeHtml(campaignTitle(item))}</span>
          <span class="badge campaign-badge status-${escapeHtml(item.status)}">${escapeHtml(campaignStatusLabel(item.status))}</span>
        </span>
        <span class="campaign-row-meta">${escapeHtml(campaignCreated(item))} · ${total} recipient${total === 1 ? "" : "s"}</span>
        <progress value="${sent}" max="${Math.max(total, 1)}" aria-label="${sent} of ${total} messages handled"></progress>
        <span class="campaign-row-foot">
          <span><b>${sent}</b> sent</span>
          <span><b>${ready}</b> ready</span>
          <span class="${attention ? "is-attention" : ""}"><b>${attention}</b> attention</span>
          <span>${campaignProgress(item)}%</span>
        </span>
      </button>`;
    })
    .join("");
}

function renderCampaignDetail(campaign, connected) {
  const detail = $("campaignDetail");
  if (!campaign) {
    detail.innerHTML = `<div class="empty-state tall"><span class="empty-icon">◎</span><b>Nothing selected</b><p>Your campaigns will appear on the left. Select one to review every message before it sends.</p></div>`;
    return;
  }
  const status = campaign.status;
  const total = Number(campaign.total || 0);
  const sent = Number(campaign.sent || 0);
  const ready = Number(campaign.ready || 0);
  const failed = Number(campaign.failed || 0);
  const draftFailed = Number(campaign.draft_failed || 0);
  const drafting = Number(campaign.drafting || 0);
  const drafted = Math.min(Number(campaign.ai_drafted || 0), total);
  const dismissed = Math.max(0, total - drafted - drafting);
  const progress = total ? Math.round((drafted / total) * 100) : 0;
  const experimentVariants = Object.entries(
    campaign.experiment_results?.variants || {},
  );
  const actions = [];
  if (["draft", "paused"].includes(status) && ready > 0 && !drafting) {
    actions.push(
      `<button class="primary campaign-action" type="button" data-action="start" ${connected ? "" : "disabled"}>${connected ? `Approve &amp; send ${ready}` : "Connect Zoho to send"}</button>`,
    );
  }
  if (status === "running") {
    actions.push(
      '<button class="danger campaign-action" type="button" data-action="pause">Pause sending</button>',
    );
  }
  if (status === "drafting") {
    actions.push(
      '<button class="danger campaign-action" type="button" data-action="pause">Pause drafting</button>',
    );
  }
  if (["draft", "paused"].includes(status) && (drafting || draftFailed)) {
    actions.push(
      `<button class="secondary campaign-action" type="button" data-action="draft">${drafting ? "Continue AI drafting" : "Retry failed drafts"}</button>`,
    );
  }
  const templates = campaignTemplateNames(campaign);
  const messages = campaign.messages
    .map((message) => {
      const label = MESSAGE_STATUS_LABELS[message.status] || message.status;
      const source = campaign.message_sources?.[String(message.id)];
      return `<div class="campaign-message msg-${escapeHtml(message.status)}">
        <div class="campaign-to">
          <div><b>${escapeHtml(message.lead_name || "Lead")}</b><span>${escapeHtml(message.recipient)}</span></div>
          <span class="msg-badge">${escapeHtml(label)}</span>
        </div>
        ${source ? `<span class="msg-source">${escapeHtml(source)}</span>` : ""}
        ${message.subject ? `<p class="campaign-subject">${escapeHtml(message.subject)}</p>` : ""}
        ${message.body ? `<pre>${escapeHtml(message.body)}</pre>` : ""}
        ${message.error ? `<p class="campaign-error">${escapeHtml(message.error)}</p>` : ""}
      </div>`;
    })
    .join("");
  detail.innerHTML = `
    <article class="campaign-panel">
      <div class="campaign-head">
        <div><h3>${escapeHtml(campaignTitle(campaign))}</h3><p class="campaign-meta">${escapeHtml(campaignCreated(campaign))} · ${escapeHtml(campaign.niche || "No niche")}</p></div>
        <span class="badge campaign-badge status-${escapeHtml(status)}">${escapeHtml(campaignStatusLabel(status))}</span>
      </div>
      ${
        templates.length
          ? `<div class="campaign-tags">${templates.map((name) => `<span class="tag">${escapeHtml(name)}</span>`).join("")}</div>`
          : ""
      }
      <div class="campaign-metrics">
        <div><b>${total}</b><span>recipients</span></div>
        <div><b>${sent}</b><span>sent</span></div>
        <div><b>${ready}</b><span>ready</span></div>
        <div><b>${failed + draftFailed}</b><span>attention</span></div>
      </div>
      ${
        campaign.mode === "ai"
          ? `<div class="campaign-progress"><div class="campaign-progress-head"><span>${drafted} of ${total} drafted with ${escapeHtml(campaign.ai_model)}</span><span>${progress}%</span></div><progress value="${drafted}" max="${Math.max(total, 1)}" aria-label="AI drafting progress"></progress></div>`
          : ""
      }
      <p class="campaign-summary">${escapeHtml(campaign.message || "")}</p>
      <p class="fine-print left">Safety gate: suppression, prior outcomes and active duplicate recipients are checked again before sending. ${campaign.experiment?.variants > 1 ? `${Number(campaign.experiment.variants)} variants use stable assignment so results remain measurable.` : "This campaign uses one message approach."}</p>
      ${
        experimentVariants.length
          ? `<div class="campaign-tags" aria-label="Observed experiment results">${experimentVariants
              .map(([variant, result]) => {
                const outcomes = Object.entries(result.outcomes || {})
                  .map(
                    ([name, count]) => `${name.replaceAll("_", " ")}: ${count}`,
                  )
                  .join(" · ");
                return `<span class="tag"><b>Variant ${escapeHtml(variant)}</b> · ${Number(result.assigned || 0)} assigned${outcomes ? ` · ${escapeHtml(outcomes)}` : " · no outcome yet"}</span>`;
              })
              .join("")}</div>`
          : ""
      }
      ${(campaign.preflight_excluded || []).length ? `<details class="campaign-messages"><summary>${campaign.preflight_excluded.length} recipient${campaign.preflight_excluded.length === 1 ? "" : "s"} excluded by preflight</summary>${campaign.preflight_excluded.map((item) => `<div class="campaign-message"><b>${escapeHtml(item.name || item.email)}</b><p>${escapeHtml((item.issues || []).join(" · "))}</p></div>`).join("")}</details>` : ""}
      ${dismissed > 0 && !ready ? `<p class="campaign-summary muted-summary">${dismissed} message${dismissed === 1 ? "" : "s"} are no longer queued.</p>` : ""}
      <details class="campaign-messages" ${openCampaignPreviews.has(campaign.id) ? "open" : ""}><summary>Preview ${total} designated message${total === 1 ? "" : "s"}</summary>${messages || '<p class="campaign-empty">No messages yet.</p>'}</details>
      <div class="actions campaign-actions">${actions.join("")}</div>
      <p id="campaignActionStatus" class="ai-task-status is-error" role="status"></p>
    </article>`;
}

function renderCampaigns(connected) {
  $("campaignCount").textContent = outreachCampaigns.length;
  renderCampaignList();
  const current = outreachCampaigns.find(
    (item) => item.id === selectedCampaignId,
  );
  if (!current && outreachCampaigns.length) {
    selectedCampaignId = (
      outreachCampaigns.find((item) =>
        ["running", "drafting", "draft", "paused"].includes(item.status),
      ) || outreachCampaigns[0]
    ).id;
  }
  renderCampaignDetail(
    outreachCampaigns.find((item) => item.id === selectedCampaignId),
    connected,
  );
}

/* ---------- Outreach tabs ---------- */

function setOutreachTab(name, focus = false) {
  const tabs = {
    campaigns: { tab: "campaignsTab", panel: "campaignsPanel" },
    compose: { tab: "composeTab", panel: "composePanel" },
    templates: { tab: "templatesTab", panel: "templatesPanel" },
  };
  Object.entries(tabs).forEach(([key, value]) => {
    const selected = key === name;
    $(value.tab).setAttribute("aria-selected", String(selected));
    $(value.tab).classList.toggle("is-active", selected);
    $(value.panel).classList.toggle("hidden", !selected);
  });
  outreachTab = name;
  if (name === "compose") {
    if (!campaignJobsLoaded) loadCampaignJobOptions();
    syncCampaignPrepare();
  }
  if (name === "templates") renderTemplateList();
  if (focus) $(tabs[name].tab).focus();
}
["campaigns", "compose", "templates"].forEach((name) => {
  $(`${name}Tab`).addEventListener("click", () => setOutreachTab(name));
});
$("navNewCampaign").addEventListener("click", () => {
  location.hash = "outreach";
  setOutreachTab("compose");
  $("composeTab").focus();
});

/* ---------- Campaign list interactions ---------- */

$("campaignList").addEventListener("click", (event) => {
  const empty = event.target.closest("button[data-empty]");
  if (empty) {
    setOutreachTab("compose");
    return;
  }
  const row = event.target.closest(".campaign-row");
  if (!row) return;
  selectedCampaignId = row.dataset.id;
  renderCampaignList();
  renderCampaignDetail(
    outreachCampaigns.find((item) => item.id === selectedCampaignId),
    zohoConnected,
  );
});
$("campaignList").addEventListener("keydown", (event) => {
  if (!["ArrowDown", "ArrowUp"].includes(event.key)) return;
  const rows = [...$("campaignList").querySelectorAll(".campaign-row")];
  const index = rows.indexOf(document.activeElement);
  if (index < 0) return;
  event.preventDefault();
  const next = rows[index + (event.key === "ArrowDown" ? 1 : -1)];
  next?.focus();
});
$("campaignFilter").addEventListener("input", renderCampaignList);
$("refreshCampaigns").addEventListener("click", () => loadOutreach());

$("campaignDetail").addEventListener(
  "toggle",
  (event) => {
    if (!event.target.classList.contains("campaign-messages")) return;
    if (!selectedCampaignId) return;
    if (event.target.open) openCampaignPreviews.add(selectedCampaignId);
    else openCampaignPreviews.delete(selectedCampaignId);
  },
  true,
);
$("campaignDetail").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const campaign = outreachCampaigns.find(
    (item) => item.id === selectedCampaignId,
  );
  if (!campaign) return;
  const action = button.dataset.action;
  const status = $("campaignActionStatus");
  if (action === "start") {
    const running = outreachCampaigns.filter(
      (item) => item.status === "running",
    ).length;
    const extra = running
      ? ` ${running} other campaign${running === 1 ? " is" : "s are"} already sending.`
      : "";
    if (
      !confirm(
        `Send ${campaign.ready} reviewed one-to-one messages from “${campaignTitle(campaign)}” through Zoho now?${extra}`,
      )
    )
      return;
  }
  button.disabled = true;
  if (status) status.textContent = "";
  try {
    const path = `/api/outreach/campaigns/${campaign.id}/${action === "draft" ? "draft" : action}`;
    await api(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmation: true }),
    });
    toast(
      action === "start"
        ? "Sending approved. Messages are paced automatically."
        : action === "pause"
          ? "Pause requested — it takes effect after the current message."
          : "Local AI is drafting. Watch the progress in the campaign.",
    );
    await loadOutreach();
  } catch (err) {
    if (status) status.textContent = err.message;
    toast(err.message, "error");
    button.disabled = false;
  }
});

/* ---------- Composer ---------- */

function selectedSource() {
  const checked = document.querySelector(
    'input[name="campaignSource"]:checked',
  );
  return checked ? checked.value : "template";
}
function eligibleLeadCount() {
  if (!campaignJob || !Array.isArray(campaignJob.rows)) return 0;
  const scope = $("campaignScope").value;
  return campaignJob.rows.filter(
    (row) =>
      /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(String(row.email || "").trim()) &&
      recommendedEmail(row) &&
      (scope === "all" || row.match_status !== "candidate"),
  ).length;
}
function campaignLimit() {
  const value = Number($("campaignMaximum").value);
  return Math.max(1, Math.min(20, Number.isFinite(value) ? value : 1));
}
function syncCampaignSource() {
  const useAi = selectedSource() === "ai";
  $("templateSourceBlock").classList.toggle("hidden", useAi);
  $("aiSourceBlock").classList.toggle("hidden", !useAi);
  $("campaignPrepareStatus").textContent = "";
  syncCampaignPrepare();
}
function syncCampaignPrepare() {
  const useAi = selectedSource() === "ai";
  const available = eligibleLeadCount();
  const take = Math.min(campaignLimit(), available);
  const busy = !campaignJob || active(campaignJob.status);
  const missingTemplates = !useAi && selectedTemplateIds.size === 0;
  const missingAi =
    useAi &&
    (!$("campaignAiModel").value || !$("campaignAiOffer").value.trim());
  $("prepareCampaign").disabled =
    busy || take === 0 || missingTemplates || missingAi;
  $("templateSelectedCount").textContent =
    `${selectedTemplateIds.size} selected`;
  renderTemplatePreview();
  const target = $("campaignRecipientPreview");
  if (!campaignJob) {
    target.textContent =
      "Choose an organized Research Library collection to pick recipients.";
  } else if (!available) {
    target.textContent =
      "This research collection has no eligible email recipients for the chosen scope.";
  } else {
    target.innerHTML = `<b>${take}</b> of <b>${available}</b> eligible lead${available === 1 ? "" : "s"} with email in <b>${escapeHtml(campaignJob.params?.niche || "this search")}</b> will be included.`;
  }
}
async function loadCampaignJobOptions(preferredId = null) {
  const select = $("campaignJob");
  try {
    const researchLibrary = await api("/api/library");
    const saved = (researchLibrary.collections || []).filter(
      (item) => Number(item.record_count) > 0,
    );
    if (!saved.length) {
      select.innerHTML =
        '<option value="">No compiled research collections yet</option>';
      select.disabled = true;
      campaignJob = null;
      $("campaignJobHint").textContent =
        "Finish a search and its verification round first. Its organized prospects will then appear in the Research Library.";
      syncCampaignPrepare();
      campaignJobsLoaded = true;
      return;
    }
    select.disabled = false;
    select.innerHTML = saved
      .map((item) => {
        return `<option value="${escapeHtml(item.job_id)}">${escapeHtml(item.niche || "Research")} · ${escapeHtml(item.location || "Anywhere")} · ${Number(item.record_count) || 0} organized prospects · ${escapeHtml(String(item.created_at || "").slice(0, 10))}</option>`;
      })
      .join("");
    const wanted =
      preferredId ||
      (job && saved.some((item) => item.job_id === job.id) ? job.id : "") ||
      (campaignJob && saved.some((item) => item.job_id === campaignJob.id)
        ? campaignJob.id
        : "") ||
      saved[0].job_id;
    select.value = wanted;
    campaignJobsLoaded = true;
    await selectCampaignJob(wanted);
  } catch (err) {
    select.innerHTML = `<option value="">${escapeHtml(err.message)}</option>`;
    select.disabled = true;
  }
}
async function selectCampaignJob(id) {
  if (!id) {
    campaignJob = null;
    syncCampaignPrepare();
    return;
  }
  const hint = $("campaignJobHint");
  hint.textContent = "Loading organized prospects from the Research Library…";
  try {
    const loaded = await api(`/api/jobs/${encodeURIComponent(id)}`);
    campaignJob = loaded;
    const rows = Array.isArray(loaded.rows) ? loaded.rows : [];
    const withEmail = rows.filter(
      (row) =>
        /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(String(row.email || "").trim()) &&
        recommendedEmail(row),
    ).length;
    const organization = loaded.organization || {};
    hint.textContent = `${rows.length} organized prospect${rows.length === 1 ? "" : "s"} in this research collection — ${withEmail} with recommended email · ${Number(organization.duplicates_consolidated) || 0} duplicate records consolidated. Scope and maximum below decide who is included.`;
  } catch (err) {
    campaignJob = null;
    hint.textContent = err.message;
  }
  syncCampaignPrepare();
}
function renderTemplatePreview() {
  const box = $("campaignTemplatePreview");
  const chosen = outreachTemplates.filter((item) =>
    selectedTemplateIds.has(item.id),
  );
  if (!chosen.length) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  box.classList.remove("hidden");
  box.innerHTML = `<span class="preview-label">Rotation preview</span>${chosen
    .slice(0, 3)
    .map(
      (item, index) =>
        `<div class="preview-row"><span class="preview-index">${index + 1}</span><div><b>${escapeHtml(item.name)}</b><span>${escapeHtml(item.subject)}</span></div></div>`,
    )
    .join(
      "",
    )}${chosen.length > 3 ? `<p class="fine-print left">+ ${chosen.length - 3} more template${chosen.length - 3 === 1 ? "" : "s"}</p>` : ""}`;
}
function renderTemplatePicker() {
  const picker = $("campaignTemplates");
  const term = $("templateSearch").value.trim().toLowerCase();
  const visible = outreachTemplates.filter(
    (item) =>
      !term || `${item.name} ${item.niche}`.toLowerCase().includes(term),
  );
  if (!outreachTemplates.length) {
    picker.innerHTML = `<div class="empty-state"><b>No templates yet</b><p>Create your first reusable message in the Templates tab.</p><button class="secondary" type="button" data-goto="templates">Open templates</button></div>`;
    return;
  }
  if (!visible.length) {
    picker.innerHTML =
      '<div class="empty-state"><b>No template matches that filter</b></div>';
    return;
  }
  picker.innerHTML = visible
    .map((item) => {
      const checked = selectedTemplateIds.has(item.id);
      return `<label class="template-option${checked ? " is-checked" : ""}">
        <input type="checkbox" value="${escapeHtml(item.id)}" ${checked ? "checked" : ""} />
        <span class="template-option-body">
          <span class="template-option-head"><b>${escapeHtml(item.name)}</b><span class="tag">${escapeHtml(item.niche)}</span></span>
          <span class="template-option-subject">${escapeHtml(item.subject)}</span>
        </span>
        <span class="template-option-tick" aria-hidden="true">✓</span>
      </label>`;
    })
    .join("");
}
$("campaignTemplates").addEventListener("change", (event) => {
  const input = event.target.closest('input[type="checkbox"]');
  if (!input) return;
  input.checked
    ? selectedTemplateIds.add(input.value)
    : selectedTemplateIds.delete(input.value);
  input
    .closest(".template-option")
    ?.classList.toggle("is-checked", input.checked);
  syncCampaignPrepare();
});
$("campaignTemplates").addEventListener("click", (event) => {
  const goto = event.target.closest("button[data-goto]");
  if (goto) setOutreachTab(goto.dataset.goto);
});
$("templateSearch").addEventListener("input", renderTemplatePicker);
$("templateSelectAll").addEventListener("click", () => {
  outreachTemplates.forEach((item) => selectedTemplateIds.add(item.id));
  renderTemplatePicker();
  syncCampaignPrepare();
});
$("templateSelectNone").addEventListener("click", () => {
  selectedTemplateIds.clear();
  renderTemplatePicker();
  syncCampaignPrepare();
});
$("templateManage").addEventListener("click", () =>
  setOutreachTab("templates"),
);
document
  .querySelectorAll('input[name="campaignSource"]')
  .forEach((input) => input.addEventListener("change", syncCampaignSource));
["campaignScope", "campaignMaximum"].forEach((id) =>
  $(id).addEventListener("input", syncCampaignPrepare),
);
$("campaignJob").addEventListener("change", (event) =>
  selectCampaignJob(event.target.value),
);
$("campaignAiOffer").addEventListener("input", syncCampaignPrepare);
$("campaignAiModel").addEventListener("change", () => {
  localStorage.setItem("leadfinder.aiModel", $("campaignAiModel").value);
  if ($("aiModel")) $("aiModel").value = $("campaignAiModel").value;
  syncCampaignPrepare();
});

/* ---------- Templates ---------- */

function renderTemplateList() {
  const list = $("templateList");
  $("templateCount").textContent = outreachTemplates.length;
  if (!outreachTemplates.length) {
    list.innerHTML = `<div class="empty-state"><b>No templates yet</b><p>Write one on the right and it will be available for every campaign.</p></div>`;
    return;
  }
  list.innerHTML = outreachTemplates
    .map(
      (item) => `<article class="template-item">
        <div class="template-item-head"><b>${escapeHtml(item.name)}</b><span class="tag">${escapeHtml(item.niche)}</span></div>
        <p class="template-item-subject">${escapeHtml(item.subject)}</p>
        <p class="template-item-body">${escapeHtml(
          String(item.body || "")
            .replace(/\s+/g, " ")
            .slice(0, 140),
        )}${String(item.body || "").length > 140 ? "…" : ""}</p>
        <div class="template-item-actions">
          <button class="ghost small" type="button" data-edit="${escapeHtml(item.id)}">Edit</button>
          <button class="ghost small" type="button" data-use="${escapeHtml(item.id)}">Use in campaign</button>
        </div>
      </article>`,
    )
    .join("");
}
$("templateList").addEventListener("click", (event) => {
  const edit = event.target.closest("button[data-edit]");
  const use = event.target.closest("button[data-use]");
  if (edit) {
    const template = outreachTemplates.find(
      (item) => item.id === edit.dataset.edit,
    );
    if (!template) return;
    editingTemplateId = template.id;
    $("templateFormTitle").textContent = "Edit template";
    $("templateName").value = template.name;
    $("templateNiche").value = template.niche;
    $("templateSubject").value = template.subject;
    $("templateBody").value = template.body;
    $("templateStatus").textContent =
      `Editing “${template.name}”. Saving keeps its original creation date.`;
    $("templateName").focus();
  }
  if (use) {
    selectedTemplateIds.add(use.dataset.use);
    setOutreachTab("compose");
    renderTemplatePicker();
    syncCampaignPrepare();
    toast("Template added to the new campaign.");
  }
});
function resetTemplateForm() {
  editingTemplateId = null;
  $("templateFormTitle").textContent = "New template";
  $("templateForm").reset();
  $("templateStatus").textContent = "";
}
$("templateReset").addEventListener("click", resetTemplateForm);
$("templateForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const payload = {
      name: $("templateName").value,
      niche: $("templateNiche").value,
      subject: $("templateSubject").value,
      body: $("templateBody").value,
    };
    if (editingTemplateId) payload.id = editingTemplateId;
    const saved = await api("/api/outreach/templates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    selectedTemplateIds.add(saved.id);
    toast(editingTemplateId ? "Template updated." : "Template saved.");
    resetTemplateForm();
    await loadOutreach();
    renderTemplatePicker();
    syncCampaignPrepare();
  } catch (err) {
    $("templateStatus").textContent = err.message;
  }
});

/* ---------- Create campaign ---------- */

$("prepareCampaign").addEventListener("click", async () => {
  if (!campaignJob || active(campaignJob.status)) {
    $("campaignPrepareStatus").textContent =
      "Choose a finished saved search first.";
    return;
  }
  const mode = selectedSource();
  const payload = {
    job_id: campaignJob.id,
    scope: $("campaignScope").value,
    maximum: campaignLimit(),
    mode,
  };
  if (mode === "ai") {
    if (!$("campaignAiModel").value || !$("campaignAiOffer").value.trim()) {
      $("campaignPrepareStatus").textContent =
        "Choose an installed local model and describe your offer first.";
      return;
    }
    payload.ai_model = $("campaignAiModel").value;
    payload.offer = $("campaignAiOffer").value.trim();
  } else {
    if (!selectedTemplateIds.size) {
      $("campaignPrepareStatus").textContent =
        "Select at least one template for this campaign.";
      return;
    }
    payload.template_ids = [...selectedTemplateIds];
  }
  const button = $("prepareCampaign");
  button.disabled = true;
  try {
    const created = await api("/api/outreach/campaigns", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    $("campaignPrepareStatus").textContent =
      mode === "ai"
        ? "Campaign created. Your local model is drafting every message; review all of them before approving."
        : "Campaign created. Review every message, then approve when ready.";
    selectedCampaignId = created.id;
    await loadOutreach();
    setOutreachTab("campaigns");
    toast(
      mode === "ai"
        ? "Campaign created — local AI is drafting."
        : "Campaign created — ready for review.",
    );
    $("campaignDetail").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    $("campaignPrepareStatus").textContent = err.message;
    toast(err.message, "error");
  } finally {
    syncCampaignPrepare();
  }
});

/* ---------- Outreach data loading ---------- */

function syncOutreachStatus(status) {
  const connected = Boolean(status?.connected);
  zohoConnected = connected;
  $("zohoStatus").textContent = connected
    ? `Zoho connected as ${status.from_address}`
    : `${status?.message || "Zoho is not connected"} Missing: ${(status?.missing || []).join(", ") || "none"}.`;
  $("zohoStatus").className = `status-chip ${connected ? "is-ok" : "is-warn"}`;
  $("headerZoho").textContent = connected
    ? "Zoho · connected"
    : "Zoho · setup needed";
  $("headerZoho").className = `header-chip ${connected ? "is-ok" : "is-warn"}`;
  if (!connected) $("zohoConnectCard").open = true;
}
function syncRunningChip(connected) {
  const running = outreachCampaigns.filter((item) => item.status === "running");
  const drafting = outreachCampaigns.filter(
    (item) => item.status === "drafting",
  ).length;
  const ready = outreachCampaigns.filter(
    (item) => item.status === "draft" && Number(item.ready) > 0,
  ).length;
  const parts = [];
  if (running.length)
    parts.push(
      `${running.length} sending${drafting ? ` · ${drafting} drafting` : ""}`,
    );
  else if (drafting) parts.push(`${drafting} drafting`);
  else if (ready) parts.push(`${ready} awaiting approval`);
  else parts.push("No campaign is sending");
  $("runningChip").textContent = parts[0];
  $("runningChip").className =
    `status-chip ${running.length ? "is-live" : drafting ? "is-warn" : ready ? "is-info" : "is-idle"}`;
  $("outreachBadge").textContent = running.length + drafting;
  $("outreachBadge").classList.toggle(
    "hidden",
    running.length + drafting === 0,
  );
}
function syncAiChip() {
  const available = Boolean(aiConnection?.available);
  $("aiStatusChip").textContent = available
    ? `Local AI · ${aiConnection.models?.length || 0} model${aiConnection.models?.length === 1 ? "" : "s"} ready`
    : "Local AI · offline";
  $("aiStatusChip").className =
    `status-chip ${available ? "is-ok" : "is-idle"}`;
  $("headerAi").textContent = available
    ? "Local AI · ready"
    : "Local AI · offline";
  $("headerAi").className = `header-chip ${available ? "is-ok" : "is-idle"}`;
}

async function loadOutreach() {
  clearTimeout(outreachPollTimer);
  try {
    const [status, templates, campaigns] = await Promise.all([
      api("/api/outreach/status"),
      api("/api/outreach/templates"),
      api("/api/outreach/campaigns"),
    ]);
    outreachTemplates = templates;
    outreachCampaigns = campaigns;
    const known = new Set(templates.map((item) => item.id));
    [...selectedTemplateIds].forEach((id) => {
      if (!known.has(id)) selectedTemplateIds.delete(id);
    });
    syncOutreachStatus(status);
    syncRunningChip(status.connected);
    syncAiChip();
    $("zohoDc").value = status.dc || "com";
    if (status.client_saved) {
      $("zohoClientId").placeholder = "Saved securely · enter only to replace";
      $("zohoClientSecret").placeholder =
        "Saved securely · enter only to replace";
      $("zohoConnectForm").querySelector("button[type=submit]").textContent =
        status.connected ? "Reconnect Zoho" : "Open Zoho approval";
      $("zohoClientId").required = false;
      $("zohoClientSecret").required = false;
    } else {
      $("zohoClientId").required = true;
      $("zohoClientSecret").required = true;
      $("zohoClientId").placeholder = "";
      $("zohoClientSecret").placeholder = "";
      $("zohoConnectForm").querySelector("button[type=submit]").textContent =
        "Save and open Zoho approval";
    }
    renderTemplatePicker();
    renderTemplateList();
    renderCampaigns(status.connected);
    syncCampaignPrepare();
    if (
      campaigns.some((item) => ["running", "drafting"].includes(item.status))
    ) {
      outreachPollTimer = setTimeout(loadOutreach, 3000);
    }
  } catch (err) {
    $("zohoStatus").textContent = err.message;
    toast(err.message, "error");
  }
}

$("zohoSetupButton").addEventListener("click", () => {
  const card = $("zohoConnectCard");
  card.open = !card.open;
  $("zohoSetupButton").setAttribute("aria-expanded", String(card.open));
  if (card.open) card.scrollIntoView({ behavior: "smooth", block: "nearest" });
});
$("zohoConnectCard").addEventListener("toggle", () => {
  $("zohoSetupButton").setAttribute(
    "aria-expanded",
    String($("zohoConnectCard").open),
  );
});

/* ---------- Zoho connection ---------- */

$("zohoConnectForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const clientId = $("zohoClientId").value.trim();
    const clientSecret = $("zohoClientSecret").value.trim();
    if (clientId || clientSecret) {
      await api("/api/outreach/zoho/client", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_id: clientId,
          client_secret: clientSecret,
          dc: $("zohoDc").value,
        }),
      });
    }
    const popup = window.open(
      "/api/outreach/zoho/connect",
      "zoho-oauth",
      "popup,width=620,height=760",
    );
    if (!popup)
      throw Error("Allow popups for this local dashboard, then try again.");
    $("zohoConnectStatus").textContent =
      "Complete Zoho approval in the popup. This page will detect the connection.";
    const deadline = Date.now() + 10 * 60 * 1000;
    const watch = setInterval(async () => {
      try {
        const status = await api("/api/outreach/status");
        if (status.connected) {
          clearInterval(watch);
          popup.close();
          $("zohoConnectStatus").textContent =
            `Connected as ${status.from_address}.`;
          await loadOutreach();
          toast("Zoho Mail is connected.");
        } else if (Date.now() > deadline || popup.closed) clearInterval(watch);
      } catch {}
    }, 1500);
  } catch (err) {
    $("zohoConnectStatus").textContent = err.message;
  }
});
$("zohoDisconnect").addEventListener("click", async () => {
  if (
    !confirm(
      "Disconnect Zoho from this local dashboard? Saved campaigns will remain, but sending will stop.",
    )
  )
    return;
  await api("/api/outreach/zoho/disconnect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  $("zohoConnectStatus").textContent =
    "Zoho disconnected. Campaign drafts and history were retained.";
  await loadOutreach();
  toast("Zoho disconnected.", "error");
});

async function init() {
  loadAiStatus();
  syncCampaignSource();
  setOutreachTab("campaigns");
  syncCountryCoverage();
  await loadBrowserProfile();
  await loadMaintenance();
  await loadConnections();
  await updatePlan();
  await loadHistory();
  try {
    const status = await api("/api/health");
    if (status.preferences?.chrome_integration === false) {
      $("browser").checked = false;
      const note = $("browser").closest(".check-row")?.querySelector("small");
      if (note && !note.dataset.installerPreference) {
        note.append(
          " Disabled during installation; you can enable it for any search.",
        );
        note.dataset.installerPreference = "shown";
      }
    }
    $("sourceCards").innerHTML = status.sources
      .map(
        (s) =>
          `<div class="source-card"><h2>${escapeHtml(s.name)}</h2><span class="badge">${escapeHtml(s.state)}</span><p><b>${escapeHtml(s.cost)}</b></p><p>${escapeHtml(s.description)}</p></div>`,
      )
      .join("");
  } catch (err) {
    $("formError").textContent = "Dashboard connection lost: " + err.message;
  }
  if (jobId) await poll();
  await discoverWorkflowForJob();
  if (workflowId) pollWorkflow(workflowId);
  try {
    const savedBatch = JSON.parse(
      localStorage.getItem("leadfinder.aiBatchTask") || "null",
    );
    if (savedBatch?.id) pollAiBatch(savedBatch.id, savedBatch.job_id);
  } catch {
    localStorage.removeItem("leadfinder.aiBatchTask");
  }
  route();
}
init();

$("connectionCards").addEventListener("submit", async (event) => {
  const form = event.target.closest("[data-connection-form]");
  if (!form) return;
  event.preventDefault();
  const provider = form.dataset.connectionForm;
  const values = Object.fromEntries(new FormData(form));
  try {
    await connectionPost("/api/connections/save", { provider, ...values });
    await loadConnections();
    toast(
      `${provider === "google_sheets" ? "Google OAuth client" : "Provider credential"} saved securely.`,
    );
  } catch (err) {
    $("connectionStatus").textContent = err.message;
  }
});
$("connectionCards").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-connection-action]");
  if (!button || button.matches('input[type="checkbox"]')) return;
  const card = button.closest("[data-provider]");
  const provider = card?.dataset.provider;
  const action = button.dataset.connectionAction;
  try {
    if (action === "google-connect") {
      const popup = window.open(
        "/api/connections/google/connect",
        "leadfinder-google-oauth",
        "popup,width=620,height=760",
      );
      pollGoogleConnection(popup);
      $("connectionStatus").textContent =
        "Complete Google approval in the popup. This page will detect the connection.";
      return;
    }
    if (action === "test") {
      if (
        provider === "google_places" &&
        !confirm(
          "Testing Google Places performs one Text Search request and may use billable quota. Continue?",
        )
      )
        return;
      button.disabled = true;
      $("connectionStatus").textContent = `Testing ${provider}…`;
      await connectionPost("/api/connections/test", { provider });
      toast("Connection verified.");
    } else if (action === "sheet-sync") {
      button.disabled = true;
      $("connectionStatus").textContent =
        "Synchronizing the organized research library…";
      const result = await connectionPost("/api/connections/google/sync", {});
      await loadConnections();
      $("connectionStatus").innerHTML =
        `${result.rows} organized leads synchronized. ${link(result.url, "Open Google Sheet ↗")}`;
      toast("Research library synchronized to Google Sheets.");
      return;
    } else if (action === "disconnect") {
      if (
        !confirm(`Disconnect ${provider}? Saved research will not be deleted.`)
      )
        return;
      await connectionPost("/api/connections/disconnect", { provider });
      toast("Connection removed from Windows Credential Manager.");
    }
    await loadConnections();
  } catch (err) {
    $("connectionStatus").textContent = err.message;
    button.disabled = false;
  }
});
$("connectionCards").addEventListener("change", async (event) => {
  const input = event.target.closest('[data-connection-action="enabled"]');
  if (!input) return;
  const provider = input.closest("[data-provider]")?.dataset.provider;
  try {
    await connectionPost("/api/connections/enabled", {
      provider,
      enabled: input.checked,
    });
    await loadConnections();
    toast(input.checked ? "Provider enabled." : "Provider disabled.");
  } catch (err) {
    input.checked = !input.checked;
    $("connectionStatus").textContent = err.message;
  }
});

$("checkUpdates").addEventListener("click", async () => {
  try {
    renderMaintenance(await window.leadFinderWindow.checkForUpdates());
  } catch (err) {
    renderMaintenance({ status: "error", message: err.message });
  }
});
$("downloadUpdate").addEventListener("click", async () => {
  try {
    renderMaintenance(await window.leadFinderWindow.downloadUpdate());
  } catch (err) {
    renderMaintenance({ status: "error", message: err.message });
  }
});
$("installUpdate").addEventListener("click", async () => {
  if (
    !confirm(
      "Restart Lead Extractor and install the downloaded update now? Active searches should be allowed to finish first.",
    )
  )
    return;
  await window.leadFinderWindow.installUpdate();
});
$("repairRuntime").addEventListener("click", async () => {
  if (
    !confirm(
      "Repair the local runtime now? The app may be unavailable for several minutes, but saved research and settings will be preserved.",
    )
  )
    return;
  try {
    renderMaintenance(await window.leadFinderWindow.repairRuntime());
  } catch (err) {
    renderMaintenance({ status: "error", message: err.message });
  }
});
setInterval(async () => {
  if (!jobId || workflowId) return;
  if (await discoverWorkflowForJob()) pollWorkflow(workflowId);
}, 3000);
