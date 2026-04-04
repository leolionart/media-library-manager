const PROCESS_POLL_INTERVAL_MS = 1500;

const state = {
  payload: null,
  lanDevices: null,
  lanDevicesLoading: false,
  mounts: [],
  selectedLanConnectionId: "",
  addFolderMode: "smb",
  currentJob: null,
  currentView: "operations",
  integrationTestResults: null,
  lanConnectionTestResult: null,
  editingLanConnectionId: null,
  movePreview: null,
  providerItems: [],
  providerMovePreview: null,
  processPoller: null,
  runtimePathAutoValue: "",
  runtimePathManualOverride: false,
};

const viewMeta = {
  operations: {
    title: "Operations",
    description: "Scan connected folders, review duplicate suggestions, and move one folder from place A to place B.",
  },
  settings: {
    title: "Settings",
    description: "Manage SMB profiles, connected folders, and Radarr or Sonarr integration settings.",
  },
};

function defaultPayload() {
  return {
    roots: [],
    integrations: {
      radarr: { enabled: false, base_url: "", api_key: "", root_folder_path: "" },
      sonarr: { enabled: false, base_url: "", api_key: "", root_folder_path: "" },
      sync_options: {
        sync_after_apply: true,
        rescan_after_update: true,
        create_root_folder_if_missing: true,
      },
    },
    lan_connections: { smb: [] },
    report: null,
    plan: null,
    apply_result: null,
    sync_result: null,
    activity_log: [],
    current_job: null,
    last_scan_at: null,
    last_plan_at: null,
    last_apply_at: null,
    last_sync_at: null,
  };
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const contentType = response.headers.get("Content-Type") || "";
  const rawBody = await response.text();
  let payload = null;

  if (rawBody) {
    if (contentType.includes("application/json")) {
      try {
        payload = JSON.parse(rawBody);
      } catch {
        throw new Error(`Server returned invalid JSON for ${url}.`);
      }
    } else {
      if (url.startsWith("/api/")) {
        throw new Error(`API returned ${contentType || "an unexpected response"} for ${url}. Restart the dashboard server and try again.`);
      }
      throw new Error(`Server returned ${contentType || "an unexpected response"} for ${url}.`);
    }
  } else {
    payload = {};
  }

  if (!response.ok) {
    throw new Error(payload?.error || `Request failed with status ${response.status}`);
  }
  return payload;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function showMessage(text, isError = false) {
  const node = document.querySelector("#message");
  node.hidden = false;
  node.textContent = text;
  node.classList.toggle("error", isError);
  clearTimeout(showMessage.timeoutId);
  showMessage.timeoutId = setTimeout(() => {
    node.hidden = true;
  }, 4500);
}

function setServerStatus(text) {
  document.querySelector("#serverStatus").textContent = text;
}

function formatDate(value) {
  if (!value) return "Never";
  return new Date(value).toLocaleString();
}

function formatBytes(value) {
  if (value === null || value === undefined) return "-";
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let size = value;
  let index = -1;
  do {
    size /= 1024;
    index += 1;
  } while (size >= 1024 && index < units.length - 1);
  return `${size.toFixed(size >= 100 ? 0 : 1)} ${units[index]}`;
}

function getPayload() {
  return state.payload || defaultPayload();
}

function getCurrentJob() {
  return state.currentJob || getPayload().current_job || null;
}

function getActivityLog() {
  return getPayload().activity_log || [];
}

function getLanConnections() {
  return getPayload().lan_connections?.smb || [];
}

function getLanDevices() {
  return state.lanDevices || { devices: [], summary: { devices: 0 } };
}

function getMounts() {
  return state.mounts || [];
}

function chooseDefaultLanConnection() {
  const connections = getLanConnections();
  if (state.selectedLanConnectionId) {
    return connections.find((item) => item.id === state.selectedLanConnectionId) || null;
  }
  if (connections.length === 1) {
    return connections[0];
  }
  return null;
}

function applySavedConnection(connection, { forcePath = true, announce = false } = {}) {
  if (!connection) return false;
  state.selectedLanConnectionId = connection.id;
  setAddFolderMode("smb");
  fillLanConnectionForm(connection);
  applyConnectionToFolderForm(connection, { forcePath });
  renderAddFolderConnectionOptions();
  if (announce) {
    showMessage("Saved SMB profile applied automatically.");
  }
  return true;
}

function setView(view) {
  state.currentView = view;
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === view);
  });
  document.querySelectorAll(".view").forEach((node) => {
    node.classList.toggle("active", node.id === `${view}View`);
  });
  const meta = viewMeta[view] || viewMeta.operations;
  document.querySelector("#viewTitle").textContent = meta.title;
  document.querySelector("#viewDescription").textContent = meta.description;
}

function openModal(modalId) {
  document.querySelector(modalId).hidden = false;
}

function closeModal(modalId) {
  document.querySelector(modalId).hidden = true;
}

function setProviderForm(form, provider) {
  form.querySelector('[name="enabled"]').checked = Boolean(provider.enabled);
  form.querySelector('[name="base_url"]').value = provider.base_url || "";
  form.querySelector('[name="api_key"]').value = provider.api_key || "";
  form.querySelector('[name="root_folder_path"]').value = provider.root_folder_path || "";
}

function getProviderPayload(form) {
  return {
    enabled: form.querySelector('[name="enabled"]').checked,
    base_url: form.querySelector('[name="base_url"]').value.trim(),
    api_key: form.querySelector('[name="api_key"]').value.trim(),
    root_folder_path: form.querySelector('[name="root_folder_path"]').value.trim(),
  };
}

function getIntegrationsPayload() {
  const optionsForm = document.querySelector("#integrationOptionsForm");
  return {
    radarr: getProviderPayload(document.querySelector("#radarrForm")),
    sonarr: getProviderPayload(document.querySelector("#sonarrForm")),
    sync_options: {
      sync_after_apply: optionsForm.querySelector('[name="sync_after_apply"]').checked,
      rescan_after_update: optionsForm.querySelector('[name="rescan_after_update"]').checked,
      create_root_folder_if_missing: optionsForm.querySelector('[name="create_root_folder_if_missing"]').checked,
    },
  };
}

function resetLanConnectionForm({ clearSelection = true } = {}) {
  const form = document.querySelector("#lanConnectionForm");
  form.reset();
  form.querySelector('[name="id"]').value = "";
  state.editingLanConnectionId = null;
  if (clearSelection) {
    state.selectedLanConnectionId = "";
    document.querySelector("#savedLanConnectionSelect").value = "";
  }
}

function setAddFolderMode(mode) {
  state.addFolderMode = mode;
  const connectionForm = document.querySelector("#lanConnectionForm");
  connectionForm.hidden = mode !== "manual";
  renderConnectionSummary();
  renderFolderStep();
  syncRuntimePathSuggestions({ force: mode === "direct" });
}

function fillLanConnectionForm(connection = {}) {
  const form = document.querySelector("#lanConnectionForm");
  form.querySelector('[name="id"]').value = connection.id || "";
  form.querySelector('[name="label"]').value = connection.label || "";
  form.querySelector('[name="host"]').value = connection.host || "";
  form.querySelector('[name="share_name"]').value = connection.share_name || "";
  form.querySelector('[name="base_path"]').value = connection.base_path || "";
  form.querySelector('[name="username"]').value = connection.username || "";
  form.querySelector('[name="password"]').value = "";
  state.editingLanConnectionId = connection.id || null;
  state.selectedLanConnectionId = connection.id || "";
  document.querySelector("#savedLanConnectionSelect").value = connection.id || "";
}

function decodeMountValue(value) {
  try {
    return decodeURIComponent(String(value || ""));
  } catch {
    return String(value || "");
  }
}

function normalizeHostToken(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/^\/\//, "")
    .replace(/^.*@/, "")
    .replace(/\._smb\._tcp\.local\.?$/, ".local")
    .replace(/\.+$/, "");
}

function normalizeShareToken(value) {
  return decodeMountValue(value).trim().toLowerCase().replace(/^\/+/, "").replace(/\/+$/, "");
}

function parseMountSource(source) {
  const decoded = decodeMountValue(source);
  if (!decoded.startsWith("//")) {
    return { host: "", share: "" };
  }
  const body = decoded.slice(2);
  const slashIndex = body.indexOf("/");
  const hostPart = slashIndex === -1 ? body : body.slice(0, slashIndex);
  const sharePart = slashIndex === -1 ? "" : body.slice(slashIndex + 1).split("/")[0];
  return {
    host: normalizeHostToken(hostPart),
    share: normalizeShareToken(sharePart),
  };
}

function joinRuntimePath(mountPoint, basePath = "") {
  const prefix = String(mountPoint || "").replace(/\/+$/, "") || "/";
  const segments = String(basePath || "")
    .split("/")
    .filter(Boolean);
  if (!segments.length) {
    return prefix || "/";
  }
  return `${prefix}/${segments.join("/")}`.replace(/\/{2,}/g, "/");
}

function scoreMountSuggestion(connection, mount) {
  if (!connection) return 0;
  const mountSource = parseMountSource(mount.source);
  const connectionHost = normalizeHostToken(connection.host);
  const connectionShare = normalizeShareToken(connection.share_name);
  const mountLabel = normalizeShareToken(mount.label || "");
  const mountPointName = normalizeShareToken((mount.mount_point || "").split("/").filter(Boolean).pop() || "");
  const mountSourceText = normalizeHostToken(mount.source);
  let score = mount.is_network ? 2 : 0;

  if (connectionShare) {
    if (connectionShare === mountSource.share) score += 8;
    if (connectionShare === mountLabel) score += 6;
    if (connectionShare === mountPointName) score += 6;
  }
  if (connectionHost) {
    if (connectionHost === mountSource.host) score += 6;
    if (mountSourceText.includes(connectionHost)) score += 3;
  }
  return score;
}

function buildRuntimePathSuggestions(connection) {
  const mounts = getMounts();
  if (state.addFolderMode === "direct") {
    return mounts.slice(0, 10).map((mount) => ({
      path: mount.mount_point,
      mountPoint: mount.mount_point,
      score: mount.is_network ? 2 : 1,
      reason: mount.is_network ? "Mounted network share" : "Mounted local path",
      source: mount.source,
    }));
  }
  if (!connection) return [];

  const suggestions = mounts
    .map((mount) => ({
      mount,
      score: scoreMountSuggestion(connection, mount),
    }))
    .filter((item) => item.score > 0)
    .map(({ mount, score }) => ({
      path: joinRuntimePath(mount.mount_point, connection.base_path),
      mountPoint: mount.mount_point,
      score,
      reason: score >= 12 ? "Matched host and share" : score >= 8 ? "Matched share" : "Possible mounted path",
      source: mount.source,
    }));

  if (suggestions.length) {
    return Array.from(new Map(suggestions.map((item) => [item.path, item])).values()).sort(
      (left, right) => right.score - left.score || left.path.localeCompare(right.path)
    );
  }

  return mounts
    .filter((mount) => mount.is_network)
    .slice(0, 8)
    .map((mount) => ({
      path: mount.mount_point,
      mountPoint: mount.mount_point,
      score: 1,
      reason: "Mounted network share",
      source: mount.source,
    }));
}

function syncRuntimePathSuggestions({ force = false } = {}) {
  const form = document.querySelector("#addFolderForm");
  const pathInput = form.querySelector('[name="path"]');
  const connection =
    state.addFolderMode === "direct" ? null : getLanConnections().find((item) => item.id === state.selectedLanConnectionId) || null;
  const suggestions = buildRuntimePathSuggestions(connection);
  const currentValue = pathInput.value.trim();
  const canReplace = force || !currentValue || currentValue === state.runtimePathAutoValue;

  if (canReplace) {
    const topSuggestion = suggestions[0];
    if (topSuggestion) {
      pathInput.value = topSuggestion.path;
      state.runtimePathAutoValue = topSuggestion.path;
    } else if (force || currentValue === state.runtimePathAutoValue) {
      pathInput.value = "";
      state.runtimePathAutoValue = "";
    }
  }

  renderRuntimePathAssist();
}

function renderRuntimePathAssist() {
  const node = document.querySelector("#runtimePathAssist");
  const runtimePathField = document.querySelector("#runtimePathField");
  const pathValue = document.querySelector('#addFolderForm [name="path"]').value.trim();
  const connection = getLanConnections().find((item) => item.id === state.selectedLanConnectionId);
  const suggestions = buildRuntimePathSuggestions(state.addFolderMode === "direct" ? null : connection);
  const shouldHidePathField = suggestions.length > 0 && !state.runtimePathManualOverride;

  runtimePathField.classList.toggle("runtime-path-hidden", shouldHidePathField);

  if (state.addFolderMode === "direct") {
    node.innerHTML = suggestions.length
      ? `
        <div class="collection-item vertical runtime-path-assist">
          <div class="row split">
            <strong>Mounted Paths</strong>
            <span class="pill small accent">Pick One</span>
          </div>
          <div class="runtime-path-note">Use one of the mounted paths the app can already reach.</div>
          <div class="runtime-path-actions">
            <button class="btn btn-small" type="button" data-toggle-runtime-path-manual="${state.runtimePathManualOverride ? "off" : "on"}">
              ${state.runtimePathManualOverride ? "Hide Manual Path" : "Edit Manually"}
            </button>
            ${suggestions
              .map(
                (item) =>
                  `<button class="btn btn-small" type="button" data-apply-runtime-path="${escapeHtml(item.path)}">${escapeHtml(item.path)}</button>`
              )
              .join("")}
          </div>
        </div>`
      : `<div class="empty-state">No mounted paths discovered yet. Enter a local runtime path manually.</div>`;
    return;
  }

  if (!connection) {
    node.innerHTML = `<div class="empty-state">Select or save an SMB profile first.</div>`;
    return;
  }

  if (suggestions.length) {
    node.innerHTML = `
      <div class="collection-item vertical runtime-path-assist">
        <div class="row split">
          <strong>Runtime Path Suggestions</strong>
          <span class="pill small accent">${escapeHtml(String(suggestions.length))}</span>
        </div>
        <div class="runtime-path-note">The app matched this SMB profile against currently mounted paths and filled the best option automatically.</div>
        <div class="runtime-path-actions">
          <button class="btn btn-small" type="button" data-toggle-runtime-path-manual="${state.runtimePathManualOverride ? "off" : "on"}">
            ${state.runtimePathManualOverride ? "Hide Manual Path" : "Edit Manually"}
          </button>
          ${suggestions
            .slice(0, 6)
            .map(
              (item) => `
                <button class="btn btn-small ${item.path === pathValue ? "btn-primary" : ""}" type="button" data-apply-runtime-path="${escapeHtml(
                  item.path
                )}">
                  ${escapeHtml(item.path)}
                </button>`
            )
            .join("")}
        </div>
      </div>`;
    return;
  }

  node.innerHTML = `
    <div class="collection-item vertical runtime-path-assist">
      <div class="row split">
        <strong>No Mounted Match Found</strong>
        <span class="pill small">Manual</span>
      </div>
      <div class="runtime-path-note">This SMB profile is not currently mapped to any mounted runtime path the app can detect. Mount the share locally first, or enter the runtime path manually.</div>
    </div>`;
}

function applyConnectionToFolderForm(connection, { forcePath = false } = {}) {
  const form = document.querySelector("#addFolderForm");
  state.runtimePathManualOverride = false;
  if (!connection) {
    form.querySelector('[name="connection_id"]').value = "";
    syncRuntimePathSuggestions({ force: forcePath });
    renderFolderStep();
    return;
  }
  form.querySelector('[name="connection_id"]').value = connection.id || "";
  const labelInput = form.querySelector('[name="label"]');

  if (!labelInput.value.trim()) {
    labelInput.value = connection.base_path
      ? `${connection.label} ${connection.base_path.split("/").filter(Boolean).pop() || connection.share_name}`.trim()
      : connection.label;
  }
  syncRuntimePathSuggestions({ force: forcePath });
  renderFolderStep();
}

function getLanConnectionPayload() {
  const form = document.querySelector("#lanConnectionForm");
  const payload = {
    id: form.querySelector('[name="id"]').value.trim(),
    label: form.querySelector('[name="label"]').value.trim(),
    protocol: "smb",
    host: form.querySelector('[name="host"]').value.trim(),
    port: 445,
    share_name: form.querySelector('[name="share_name"]').value.trim(),
    base_path: form.querySelector('[name="base_path"]').value.trim(),
    username: form.querySelector('[name="username"]').value.trim(),
    password: form.querySelector('[name="password"]').value,
    domain: "",
    version: "3.0",
    enabled: true,
  };
  if (!payload.password && payload.id) {
    delete payload.password;
  }
  return payload;
}

function renderSystemSummary() {
  const payload = getPayload();
  const roots = payload.roots || [];
  const reportSummary = payload.report?.summary || {};
  const enabledIntegrations = ["radarr", "sonarr"].filter((name) => payload.integrations?.[name]?.enabled);

  document.querySelector("#connectedFolderCountValue").textContent = String(roots.length);
  document.querySelector("#connectedFolderMeta").textContent = roots.length
    ? roots.map((root) => root.label).slice(0, 3).join(" • ")
    : "Add one or more root folders in Settings.";

  const duplicateGroups = (reportSummary.exact_duplicate_groups || 0) + (reportSummary.media_collision_groups || 0);
  document.querySelector("#duplicateSummaryValue").textContent = payload.report ? `${duplicateGroups} groups` : "No scan";
  document.querySelector("#duplicateSummaryMeta").textContent = payload.report
    ? `${reportSummary.exact_duplicate_groups || 0} exact • ${reportSummary.media_collision_groups || 0} collision`
    : "Run scan to generate duplicate suggestions.";

  document.querySelector("#integrationSummaryValue").textContent = enabledIntegrations.length
    ? enabledIntegrations.map((name) => name[0].toUpperCase() + name.slice(1)).join(" + ")
    : "Disabled";
  document.querySelector("#integrationSummaryMeta").textContent = enabledIntegrations.length
    ? "Provider settings are ready for path sync."
    : "Radarr and Sonarr are configured from Settings.";

  document.querySelector("#heroLastScanValue").textContent = formatDate(payload.last_scan_at);
  document.querySelector("#heroLastPlanValue").textContent = formatDate(payload.last_plan_at);
  document.querySelector("#heroLastApplyValue").textContent = formatDate(payload.last_apply_at);

}

function renderRoots() {
  const roots = getPayload().roots || [];
  const html = roots.length
    ? roots
        .map(
          (root) => `
            <div class="collection-item vertical">
              <div class="row split">
                <strong>${escapeHtml(root.label)}</strong>
                <div class="item-meta">
                  <span class="pill small">P${root.priority}</span>
                  <span class="pill small">${escapeHtml(root.kind)}</span>
                </div>
              </div>
              <div class="muted">${escapeHtml(root.path)}</div>
              <div class="sub-row"><span>Profile</span><span>${escapeHtml(root.connection_label || "Direct path")}</span></div>
              <div class="item-meta network-profile-actions">
                <select class="action-select" data-folder-action-select="${escapeHtml(root.path)}">
                  <option value="">Actions</option>
                  <option value="use-source">Use As Move Source</option>
                  <option value="use-destination">Use As Move Destination</option>
                  <option value="move-radarr">Move To Radarr...</option>
                  <option value="move-sonarr">Move To Sonarr...</option>
                  <option value="delete-folder">Delete Folder...</option>
                  <option value="remove-root">Remove From App</option>
                </select>
                <button class="btn btn-small" data-run-folder-action="${escapeHtml(root.path)}">Run</button>
              </div>
            </div>`
        )
        .join("")
    : `<div class="empty-state">No connected folders yet. Add one from Settings.</div>`;

  document.querySelector("#operationsRootsList").innerHTML = html;
  document.querySelector("#settingsRootsList").innerHTML = html;
}

function renderAddFolderConnectionOptions() {
  const select = document.querySelector("#addFolderConnectionSelect");
  const options = ['<option value="">Direct path / mounted path</option>']
    .concat(
      getLanConnections().map(
        (connection) => `<option value="${escapeHtml(connection.id)}">${escapeHtml(connection.label)} • //${escapeHtml(connection.host)}/${escapeHtml(connection.share_name)}</option>`
      )
    )
    .join("");
  select.innerHTML = options;
  if (state.selectedLanConnectionId && getLanConnections().some((item) => item.id === state.selectedLanConnectionId)) {
    select.value = state.selectedLanConnectionId;
  }
}

function renderLanConnections() {
  const connections = getLanConnections();
  const activeConnection = connections.find((item) => item.id === state.editingLanConnectionId);
  if (activeConnection) {
    fillLanConnectionForm(activeConnection);
  }

  const savedSelect = document.querySelector("#savedLanConnectionSelect");
  savedSelect.innerHTML = ['<option value="">New connection</option>']
    .concat(
      connections.map(
        (connection) =>
          `<option value="${escapeHtml(connection.id)}">${escapeHtml(connection.label)} • //${escapeHtml(connection.host)}/${escapeHtml(connection.share_name)}</option>`
      )
    )
    .join("");
  if (state.selectedLanConnectionId && connections.some((item) => item.id === state.selectedLanConnectionId)) {
    savedSelect.value = state.selectedLanConnectionId;
  }

  const result = state.lanConnectionTestResult;
  document.querySelector("#lanConnectionTestSummary").innerHTML = result
    ? `
      <div class="collection-item vertical">
        <div class="row split">
          <strong>Latest SMB Test</strong>
          <span class="pill small ${result.status === "success" ? "accent" : ""}">${escapeHtml(result.status || "unknown")}</span>
        </div>
        <div class="muted">${escapeHtml(result.target || result.message || "No details")}</div>
        ${result.message ? `<div class="sub-row"><span>Message</span><span>${escapeHtml(result.message)}</span></div>` : ""}
        ${
          result.shares?.length
            ? `<div class="service-tags">
                ${result.shares
                  .slice(0, 20)
                  .map(
                    (share) =>
                      `<button class="btn btn-small" type="button" data-apply-smb-share="${escapeHtml(share.name)}">${escapeHtml(share.name)}</button>`
                  )
                  .join("")}
              </div>`
            : ""
        }
        ${
          result.listing_preview?.length
            ? `<div class="service-tags">
                ${result.listing_preview
                  .slice(0, 20)
                  .map(
                    (entry) =>
                      `<button class="btn btn-small" type="button" data-apply-smb-path="${escapeHtml(entry.path)}">${escapeHtml(
                        entry.name || entry.path
                      )}</button>`
                  )
                  .join("")}
              </div>`
            : ""
        }
      </div>`
    : `<div class="empty-state">No SMB connection test has been run yet.</div>`;
}

function renderConnectionSummary() {
  const connection = getLanConnections().find((item) => item.id === state.selectedLanConnectionId);
  const connectionSummary = document.querySelector("#selectedConnectionSummary");
  const folderSummary = document.querySelector("#folderConnectionSummary");

  if (state.addFolderMode === "direct") {
    const html = `
      <div class="collection-item vertical compact-connection-summary">
        <div class="row split">
          <strong>Direct Path Mode</strong>
          <span class="pill small">No SMB</span>
        </div>
        <div class="muted">Use this when the runtime path is already mounted and does not need an SMB profile.</div>
      </div>`;
    connectionSummary.innerHTML = html;
    folderSummary.innerHTML = html;
    renderRuntimePathAssist();
    return;
  }

  if (!connection) {
    const hasSavedProfiles = getLanConnections().length > 0;
    const html = `<div class="empty-state">${
      hasSavedProfiles
        ? "Select a saved profile above. Manual fields stay hidden unless you need the fallback."
        : "No saved SMB profile yet. Discover a host or use manual fallback to create one."
    }</div>`;
    connectionSummary.innerHTML = html;
    folderSummary.innerHTML = html;
    renderRuntimePathAssist();
    return;
  }

  const html = `
    <div class="collection-item vertical compact-connection-summary">
      <div class="row split">
        <strong>${escapeHtml(connection.label)}</strong>
        <span class="pill small accent">Ready</span>
      </div>
      <div class="muted">//${escapeHtml(connection.host)}/${escapeHtml(connection.share_name)}</div>
      <div class="sub-row"><span>Base Path</span><span>${escapeHtml(connection.base_path || "/")}</span></div>
      <div class="sub-row"><span>User</span><span>${escapeHtml(connection.username || "-")}</span></div>
    </div>`;
  connectionSummary.innerHTML = html;
  folderSummary.innerHTML = html;
  renderRuntimePathAssist();
}

function renderFolderStep() {
  const folderStepCard = document.querySelector("#folderStepCard");
  const connection = getLanConnections().find((item) => item.id === state.selectedLanConnectionId);
  const ready = state.addFolderMode === "direct" || Boolean(connection);
  folderStepCard.hidden = !ready;
  if (ready) {
    renderRuntimePathAssist();
  }
}

function renderLanDevices() {
  const payload = getLanDevices();
  document.querySelector("#lanDeviceCount").textContent = String(payload.summary?.devices || payload.devices?.length || 0);
  const refreshButton = document.querySelector("#refreshLanDevicesButton");
  refreshButton.disabled = state.lanDevicesLoading;
  refreshButton.classList.toggle("is-loading", state.lanDevicesLoading);
  refreshButton.textContent = state.lanDevicesLoading ? "Scanning..." : "Refresh LAN";
  if (state.lanDevicesLoading) {
    document.querySelector("#lanDevicesList").innerHTML =
      `<div class="empty-state">Scanning LAN for SMB hosts...</div>`;
    return;
  }
  document.querySelector("#lanDevicesList").innerHTML = payload.devices?.length
    ? payload.devices
        .map((device) => {
          const services = device.services || [];
          const preferredHost = device.hostname || device.ip_address || device.device_key;
          const preferredSmb = services.find((service) => service.service_type === "_smb._tcp");
          const secondaryLabel = [device.hostname, device.ip_address].filter(Boolean).join(" • ") || preferredHost;
          return `
            <button class="collection-item action-card lan-device-card" type="button" data-prefill-smb-host="${escapeHtml(
              preferredHost
            )}" data-prefill-smb-label="${escapeHtml(device.display_name || preferredHost)}">
              <div class="lan-device-header">
                <div class="lan-device-copy">
                  <strong>${escapeHtml(device.display_name || preferredHost)}</strong>
                  <div class="muted">${escapeHtml(secondaryLabel)}</div>
                </div>
                <span class="pill small ${preferredSmb ? "accent" : ""}">${preferredSmb ? "SMB" : "Host"}</span>
              </div>
              ${
                services.length
                  ? `<div class="service-tags lan-device-services">
                      ${services
                        .map(
                          (service) =>
                            `<span class="pill small ${service.service_type === "_smb._tcp" ? "accent" : ""}">${escapeHtml(
                              service.service_label
                            )} • ${escapeHtml(String(service.port))}</span>`
                        )
                        .join("")}
                    </div>`
                  : ""
              }
              ${
                device.connect_urls?.length
                  ? `<div class="sub-row lan-device-connect"><span>Connect</span><span>${escapeHtml(device.connect_urls[0])}</span></div>`
                  : ""
              }
            </button>`;
        })
        .join("")
    : `<div class="empty-state">No LAN devices discovered yet. Use Refresh LAN, or enter an IP manually in the SMB form.</div>`;
}

async function refreshLanDevices(showToast = true) {
  state.lanDevicesLoading = true;
  renderLanDevices();
  try {
    const result = await request("/api/lan/discover");
    state.lanDevices = result;
    if (showToast) {
      showMessage(result.devices?.length ? "LAN discovery finished." : "No LAN SMB hosts found. You can enter an IP manually.");
    }
    return result;
  } catch (error) {
    showMessage(error.message, true);
    return null;
  } finally {
    state.lanDevicesLoading = false;
    renderLanDevices();
  }
}

function renderIntegrations() {
  const payload = getPayload();
  const integrations = payload.integrations || defaultPayload().integrations;
  setProviderForm(document.querySelector("#radarrForm"), integrations.radarr || {});
  setProviderForm(document.querySelector("#sonarrForm"), integrations.sonarr || {});
  const optionsForm = document.querySelector("#integrationOptionsForm");
  optionsForm.querySelector('[name="sync_after_apply"]').checked = Boolean(integrations.sync_options?.sync_after_apply);
  optionsForm.querySelector('[name="rescan_after_update"]').checked = Boolean(integrations.sync_options?.rescan_after_update);
  optionsForm.querySelector('[name="create_root_folder_if_missing"]').checked = Boolean(
    integrations.sync_options?.create_root_folder_if_missing
  );

  document.querySelector("#integrationTestResults").innerHTML = state.integrationTestResults
    ? Object.entries(state.integrationTestResults)
        .map(
          ([name, result]) => `
            <div class="collection-item vertical">
              <div class="row split">
                <strong>${escapeHtml(name)}</strong>
                <span class="pill small ${result.status === "error" ? "" : "accent"}">${escapeHtml(result.status || "unknown")}</span>
              </div>
              <div class="muted">${escapeHtml(result.error || result.api_root || "ready")}</div>
            </div>`
        )
        .join("")
    : `<div class="empty-state">No integration connectivity test has been run yet.</div>`;

  const syncResult = payload.sync_result;
  document.querySelector("#syncSummary").innerHTML = syncResult
    ? `
      <div class="collection-item vertical">
        <div class="row split">
          <strong>Latest Sync</strong>
          <span class="pill small ${syncResult.status === "error" ? "" : "accent"}">${escapeHtml(syncResult.status || "unknown")}</span>
        </div>
        <div class="muted">${formatDate(payload.last_sync_at)}</div>
        <div class="sub-row"><span>Updated</span><span>${syncResult.summary?.updated || 0}</span></div>
        <div class="sub-row"><span>Errors</span><span>${syncResult.summary?.error || 0}</span></div>
        <div class="sub-row"><span>Skipped</span><span>${syncResult.summary?.skipped || 0}</span></div>
      </div>`
    : `<div class="empty-state">No manual sync has been run yet.</div>`;
}

function renderMovePreview() {
  const preview = state.movePreview;
  document.querySelector("#moveFolderSummary").innerHTML = preview
    ? `
      <div class="collection-item vertical">
        <div class="row split">
          <strong>${escapeHtml(preview.status === "applied" ? "Folder moved" : "Move preview")}</strong>
          <span class="pill small ${preview.status === "applied" ? "accent" : ""}">${escapeHtml(preview.status)}</span>
        </div>
        <div class="sub-row"><span>Source</span><span>${escapeHtml(preview.source || "-")}</span></div>
        <div class="sub-row"><span>Destination Parent</span><span>${escapeHtml(preview.destination_parent || "-")}</span></div>
        <div class="sub-row"><span>Destination</span><span>${escapeHtml(preview.destination || "-")}</span></div>
      </div>`
    : `<div class="empty-state">No move preview yet.</div>`;
}

function renderProviderMoveModal() {
  const select = document.querySelector("#providerItemSelect");
  const options = ['<option value="">Select provider item</option>']
    .concat(
      state.providerItems.map(
        (item) =>
          `<option value="${escapeHtml(String(item.id))}">${escapeHtml(item.title)}${item.year ? ` (${escapeHtml(String(item.year))})` : ""}</option>`
      )
    )
    .join("");
  select.innerHTML = options;

  const selected = state.providerItems.find((item) => String(item.id) === select.value);
  const preview = state.providerMovePreview;
  document.querySelector("#providerItemMeta").innerHTML = selected
    ? `
      <div class="collection-item vertical">
        <div class="row split">
          <strong>${escapeHtml(selected.title)}${selected.year ? ` (${escapeHtml(String(selected.year))})` : ""}</strong>
          <span class="pill small">${escapeHtml(selected.id)}</span>
        </div>
        <div class="sub-row"><span>Managed Path</span><span>${escapeHtml(selected.path || "-")}</span></div>
        ${
          preview?.move_result
            ? `<div class="sub-row"><span>Preview</span><span>${escapeHtml(preview.move_result.destination || preview.move_result.destination_parent || "-")}</span></div>`
            : ""
        }
      </div>`
    : `<div class="empty-state">Select a provider item to preview the destination path.</div>`;
}

function renderOperationsSummary() {
  const payload = getPayload();
  const reportSummary = payload.report?.summary || {};
  const planSummary = payload.plan?.summary || {};
  document.querySelector("#operationSummaryCards").innerHTML = `
    <div class="stat-card"><span>Files Indexed</span><strong>${reportSummary.files || 0}</strong></div>
    <div class="stat-card"><span>Exact Groups</span><strong>${reportSummary.exact_duplicate_groups || 0}</strong></div>
    <div class="stat-card"><span>Collision Groups</span><strong>${reportSummary.media_collision_groups || 0}</strong></div>
    <div class="stat-card"><span>Plan Actions</span><strong>${(planSummary.move || 0) + (planSummary.delete || 0) + (planSummary.review || 0)}</strong></div>
  `;
}

function renderReport() {
  const exactGroups = getPayload().report?.exact_duplicates || [];
  const collisionGroups = getPayload().report?.media_collisions || [];

  document.querySelector("#exactDuplicateCount").textContent = String(exactGroups.length);
  document.querySelector("#collisionCount").textContent = String(collisionGroups.length);

  document.querySelector("#exactDuplicatesList").innerHTML = exactGroups.length
    ? exactGroups
        .slice(0, 40)
        .map(
          (group) => `
            <div class="collection-item vertical">
              <div class="row split">
                <strong>${formatBytes(group.size)}</strong>
                <span class="pill small">${group.items.length} copies</span>
              </div>
              <div class="muted">${escapeHtml(group.sha256.slice(0, 16))}...</div>
              ${group.items.map((item) => `<div class="sub-row"><span>${escapeHtml(item.path)}</span></div>`).join("")}
            </div>`
        )
        .join("")
    : `<div class="empty-state">No exact duplicate groups yet.</div>`;

  document.querySelector("#reportList").innerHTML = collisionGroups.length
    ? collisionGroups
        .slice(0, 40)
        .map(
          (group) => `
            <div class="collection-item vertical">
              <div class="row split">
                <strong>${escapeHtml(group.canonical_name)}</strong>
                <span class="pill small">${group.items.length} versions</span>
              </div>
              ${group.items
                .map(
                  (item) => `
                    <div class="sub-row">
                      <span>${escapeHtml(item.path)}</span>
                      <span class="muted">Q${item.quality_rank}</span>
                    </div>`
                )
                .join("")}
            </div>`
        )
        .join("")
    : `<div class="empty-state">No collision groups yet.</div>`;
}

function renderPlan() {
  const actions = getPayload().plan?.actions || [];
  const planSummary = getPayload().plan?.summary || {};
  document.querySelector("#planActionCount").textContent = String(actions.length);
  document.querySelector("#planSummaryCards").innerHTML = `
    <div class="stat-card"><span>Move</span><strong>${planSummary.move || 0}</strong></div>
    <div class="stat-card"><span>Delete</span><strong>${planSummary.delete || 0}</strong></div>
    <div class="stat-card"><span>Review</span><strong>${planSummary.review || 0}</strong></div>
  `;
  document.querySelector("#planList").innerHTML = actions.length
    ? actions
        .slice(0, 120)
        .map(
          (action) => `
            <div class="collection-item vertical">
              <div class="row split">
                <strong>${escapeHtml(String(action.type || "").toUpperCase())}</strong>
                <span class="pill small">${escapeHtml(action.reason)}</span>
              </div>
              <div class="sub-row"><span>Source</span><span>${escapeHtml(action.source)}</span></div>
              ${action.destination ? `<div class="sub-row"><span>Destination</span><span>${escapeHtml(action.destination)}</span></div>` : ""}
              ${action.keep_path ? `<div class="sub-row"><span>Keep</span><span>${escapeHtml(action.keep_path)}</span></div>` : ""}
            </div>`
        )
        .join("")
    : `<div class="empty-state">No action plan yet.</div>`;
}

function renderApply() {
  const payload = getPayload();
  const applyResult = payload.apply_result;
  document.querySelector("#applyResultBadge").textContent = applyResult ? escapeHtml(applyResult.mode || "Result") : "No run";
  document.querySelector("#applySummary").innerHTML = applyResult
    ? `
      <div class="collection-item vertical">
        <div class="row split">
          <strong>${escapeHtml(applyResult.mode || "dry-run")}</strong>
          <span class="pill small">${formatDate(payload.last_apply_at)}</span>
        </div>
        <div class="sub-row"><span>Applied</span><span>${applyResult.summary?.applied || 0}</span></div>
        <div class="sub-row"><span>Dry Run</span><span>${applyResult.summary?.["dry-run"] || 0}</span></div>
        <div class="sub-row"><span>Skipped</span><span>${applyResult.summary?.skipped || 0}</span></div>
        <div class="sub-row"><span>Errors</span><span>${applyResult.summary?.error || 0}</span></div>
      </div>`
    : `<div class="empty-state">No apply result yet.</div>`;
}

function renderProcessPanel() {
  const currentJob = getCurrentJob();
  const recent = getActivityLog().slice(0, 12);

  document.querySelector("#currentJobSummary").innerHTML = currentJob
    ? `
      <div class="collection-item vertical">
        <div class="row split">
          <strong>${escapeHtml(currentJob.message)}</strong>
          <span class="pill small ${currentJob.status === "error" ? "" : "accent"}">${escapeHtml(currentJob.status)}</span>
        </div>
        <div class="muted">${escapeHtml(currentJob.kind)} • started ${formatDate(currentJob.started_at)}</div>
        <div class="sub-row"><span>Completed</span><span>${currentJob.summary?.completed || 0} / ${currentJob.summary?.total || 0}</span></div>
        <div class="sub-row"><span>Skipped</span><span>${currentJob.summary?.skipped || 0}</span></div>
        <div class="sub-row"><span>Errors</span><span>${currentJob.summary?.error || 0}</span></div>
      </div>`
    : `<div class="empty-state">No active process right now.</div>`;

  document.querySelector("#currentJobLogs").innerHTML = currentJob?.logs?.length
    ? currentJob.logs
        .slice()
        .reverse()
        .map(
          (entry) => `
            <div class="collection-item vertical process-log-entry">
              <div class="row split">
                <strong>${escapeHtml(entry.message)}</strong>
                <span class="pill small ${entry.level === "error" ? "" : "accent"}">${escapeHtml(entry.level)}</span>
              </div>
              <div class="muted">${formatDate(entry.ts)}</div>
              ${
                entry.details && Object.keys(entry.details).length
                  ? `<pre class="detail-code">${escapeHtml(JSON.stringify(entry.details, null, 2))}</pre>`
                  : ""
              }
            </div>`
        )
        .join("")
    : `<div class="empty-state">Logs will appear here while a job is running.</div>`;

  document.querySelector("#recentActivityList").innerHTML = recent.length
    ? recent
        .map(
          (entry) => `
            <div class="collection-item vertical">
              <div class="row split">
                <strong>${escapeHtml(entry.message)}</strong>
                <span class="pill small ${entry.status === "error" ? "" : "accent"}">${escapeHtml(entry.status)}</span>
              </div>
              <div class="muted">${escapeHtml(entry.kind)} • ${formatDate(entry.created_at)}</div>
            </div>`
        )
        .join("")
    : `<div class="empty-state">No activity yet.</div>`;
}

function render() {
  renderSystemSummary();
  renderRoots();
  renderAddFolderConnectionOptions();
  renderLanConnections();
  renderConnectionSummary();
  renderLanDevices();
  renderFolderStep();
  renderIntegrations();
  renderMovePreview();
  renderProviderMoveModal();
  renderOperationsSummary();
  renderReport();
  renderPlan();
  renderApply();
  renderProcessPanel();
}

async function pollCurrentJob() {
  try {
    const result = await request("/api/process");
    state.currentJob = result.current_job || null;
    renderProcessPanel();
    if (!state.currentJob && state.processPoller) {
      stopProcessPolling();
      await refreshAll();
    }
  } catch {
    // Keep the latest known state.
  }
}

function startProcessPolling() {
  if (state.processPoller) return;
  pollCurrentJob();
  state.processPoller = window.setInterval(pollCurrentJob, PROCESS_POLL_INTERVAL_MS);
}

function stopProcessPolling() {
  if (!state.processPoller) return;
  window.clearInterval(state.processPoller);
  state.processPoller = null;
}

async function refreshAll() {
  const [payload, processPayload, lanPayload, mountsPayload] = await Promise.all([
    request("/api/state"),
    request("/api/process"),
    request("/api/lan/discover"),
    request("/api/system/mounts"),
  ]);
  state.payload = payload;
  state.currentJob = processPayload.current_job || payload.current_job || null;
  state.lanDevices = lanPayload;
  state.mounts = mountsPayload.mounts || [];
  render();
  if (state.currentJob) {
    startProcessPolling();
  } else {
    stopProcessPolling();
  }
}

async function runAction(label, action, successMessage) {
  setServerStatus(label);
  startProcessPolling();
  try {
    const result = await action();
    await refreshAll();
    setServerStatus("Dashboard ready");
    if (successMessage) showMessage(successMessage);
    return result;
  } catch (error) {
    try {
      await refreshAll();
    } catch {
      // keep original error
    }
    setServerStatus("Action failed");
    showMessage(error.message, true);
    return null;
  }
}

document.querySelectorAll(".nav-item").forEach((item) => {
  item.addEventListener("click", () => setView(item.dataset.view));
});

document.querySelector("#openAddFolderModalButton").addEventListener("click", () => {
  document.querySelector("#addFolderForm").reset();
  state.runtimePathAutoValue = "";
  state.runtimePathManualOverride = false;
  state.selectedLanConnectionId = "";
  state.addFolderMode = "smb";
  document.querySelector("#lanConnectionForm").hidden = true;
  renderAddFolderConnectionOptions();
  const autoConnection = chooseDefaultLanConnection();
  if (autoConnection) {
    applySavedConnection(autoConnection, { forcePath: true, announce: false });
  } else {
    renderConnectionSummary();
    renderFolderStep();
  }
  openModal("#addFolderModal");
  refreshLanDevices(false);
});

document.querySelector("#addFolderForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const profileId = form.querySelector('[name="connection_id"]').value;
  const connection = getLanConnections().find((item) => item.id === profileId);
  const payload = {
    path: form.querySelector('[name="path"]').value.trim(),
    label: form.querySelector('[name="label"]').value.trim(),
    priority: form.querySelector('[name="priority"]').value.trim(),
    kind: form.querySelector('[name="kind"]').value,
    connection_id: profileId,
    connection_label: connection?.label || "",
  };
  const result = await runAction(
    "Adding connected folder...",
    () =>
      request("/api/roots", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    "Connected folder added."
  );
  if (!result) return;
  closeModal("#addFolderModal");
});

document.querySelector("#savedLanConnectionSelect").addEventListener("change", (event) => {
  const connection = getLanConnections().find((item) => item.id === event.currentTarget.value);
  if (!connection) {
    state.selectedLanConnectionId = "";
    renderConnectionSummary();
    renderFolderStep();
    return;
  }
  applySavedConnection(connection, { forcePath: true, announce: false });
});

document.querySelector("#useSavedLanConnectionButton").addEventListener("click", () => {
  const connection = getLanConnections().find((item) => item.id === state.selectedLanConnectionId);
  if (!connection) {
    showMessage("Select a saved profile first.", true);
    return;
  }
  applySavedConnection(connection, { forcePath: true, announce: false });
  showMessage("Saved SMB profile applied to the folder form.");
});

document.querySelector("#openManualSmbButton").addEventListener("click", () => {
  setAddFolderMode("manual");
  showMessage("Manual fallback enabled.");
});

document.querySelector("#useDirectPathButton").addEventListener("click", () => {
  state.selectedLanConnectionId = "";
  document.querySelector("#savedLanConnectionSelect").value = "";
  setAddFolderMode("direct");
  applyConnectionToFolderForm(null, { forcePath: true });
  showMessage("Direct path mode enabled.");
});

document.querySelector("#lanConnectionForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const pendingPayload = getLanConnectionPayload();
  const result = await runAction(
    "Saving SMB connection...",
    () =>
      request("/api/lan/connections", {
        method: "POST",
        body: JSON.stringify(pendingPayload),
      }),
    "SMB connection saved."
  );
  if (!result) return;
  const saved =
    result.smb?.find((item) => item.id === pendingPayload.id) ||
    result.smb?.find(
      (item) =>
        item.host === pendingPayload.host &&
        item.share_name === pendingPayload.share_name &&
        item.username === pendingPayload.username
    ) ||
    result.smb?.[0];
  if (saved) {
    applySavedConnection(saved, { forcePath: true, announce: false });
  }
  resetLanConnectionForm({ clearSelection: false });
  renderAddFolderConnectionOptions();
});

document.querySelector("#testLanConnectionButton").addEventListener("click", async () => {
  const result = await runAction(
    "Testing SMB connection...",
    () =>
      request("/api/lan/connections/test", {
        method: "POST",
        body: JSON.stringify(getLanConnectionPayload()),
      }),
    "SMB connection test finished."
  );
  if (!result) return;
  state.lanConnectionTestResult = result;
  renderLanConnections();
});

document.querySelector("#resetLanConnectionButton").addEventListener("click", () => {
  resetLanConnectionForm();
  showMessage("Ready for a new SMB profile.");
});

document.querySelector("#addFolderConnectionSelect").addEventListener("change", (event) => {
  const connection = getLanConnections().find((item) => item.id === event.currentTarget.value);
  if (!connection) {
    renderConnectionSummary();
    renderFolderStep();
    return;
  }
  applySavedConnection(connection, { forcePath: true, announce: false });
});

document.querySelector("#refreshLanDevicesButton").addEventListener("click", async () => {
  setServerStatus("Discovering LAN devices...");
  await refreshLanDevices(true);
  setServerStatus("Dashboard ready");
});

document.querySelector("#saveIntegrationsButton").addEventListener("click", async () => {
  await runAction(
    "Saving integrations...",
    () =>
      request("/api/integrations", {
        method: "POST",
        body: JSON.stringify(getIntegrationsPayload()),
      }),
    "Integrations saved."
  );
});

document.querySelector("#testIntegrationsButton").addEventListener("click", async () => {
  const result = await runAction(
    "Testing integrations...",
    () =>
      request("/api/integrations/test", {
        method: "POST",
        body: JSON.stringify(getIntegrationsPayload()),
      }),
    "Integration test finished."
  );
  if (!result) return;
  state.integrationTestResults = result.results || null;
  renderIntegrations();
});

document.querySelector("#runSyncButton").addEventListener("click", async () => {
  await runAction(
    "Syncing Radarr/Sonarr...",
    () =>
      request("/api/sync", {
        method: "POST",
        body: "{}",
      }),
    "Manual sync finished."
  );
});

document.querySelector("#scanButton").addEventListener("click", async () => {
  await runAction("Running scan...", () => request("/api/scan", { method: "POST", body: "{}" }), "Scan finished.");
});

document.querySelector("#planButton").addEventListener("click", async () => {
  await runAction(
    "Building plan...",
    () =>
      request("/api/plan", {
        method: "POST",
        body: JSON.stringify({ delete_lower_quality: document.querySelector("#deleteLowerQuality").checked }),
      }),
    "Plan created."
  );
});

document.querySelector("#dryRunButton").addEventListener("click", async () => {
  await runAction(
    "Running dry-run...",
    () =>
      request("/api/apply", {
        method: "POST",
        body: JSON.stringify({ execute: false, prune_empty_dirs: document.querySelector("#pruneEmptyDirs").checked }),
      }),
    "Dry run completed."
  );
});

document.querySelector("#executePlanButton").addEventListener("click", async () => {
  if (!window.confirm("Execute the current plan on real files?")) return;
  await runAction(
    "Executing plan...",
    () =>
      request("/api/apply", {
        method: "POST",
        body: JSON.stringify({ execute: true, prune_empty_dirs: document.querySelector("#pruneEmptyDirs").checked }),
      }),
    "Plan executed."
  );
});

document.querySelector("#previewMoveButton").addEventListener("click", async () => {
  const source = document.querySelector("#moveSourceInput").value.trim();
  const destinationParent = document.querySelector("#moveDestinationInput").value.trim();
  const result = await runAction(
    "Previewing folder move...",
    () =>
      request("/api/folders/move", {
        method: "POST",
        body: JSON.stringify({ source, destination_parent: destinationParent, execute: false }),
      }),
    "Move preview ready."
  );
  if (!result) return;
  state.movePreview = result;
  renderMovePreview();
});

document.querySelector("#moveFolderForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const source = document.querySelector("#moveSourceInput").value.trim();
  const destinationParent = document.querySelector("#moveDestinationInput").value.trim();
  if (!window.confirm(`Move folder ${source} into ${destinationParent}?`)) return;
  const result = await runAction(
    "Moving folder...",
    () =>
      request("/api/folders/move", {
        method: "POST",
        body: JSON.stringify({ source, destination_parent: destinationParent, execute: true }),
      }),
    "Folder moved."
  );
  if (!result) return;
  state.movePreview = result;
  renderMovePreview();
});

document.querySelector("#providerItemSelect").addEventListener("change", () => {
  state.providerMovePreview = null;
  renderProviderMoveModal();
});

document.querySelector("#previewProviderMoveButton").addEventListener("click", async () => {
  const form = document.querySelector("#providerMoveForm");
  const selected = state.providerItems.find((item) => String(item.id) === form.querySelector('[name="item_id"]').value);
  if (!selected) {
    showMessage("Select a provider item first.", true);
    return;
  }
  const result = await runAction(
    "Previewing provider move...",
    () =>
      request("/api/folders/move-to-provider", {
        method: "POST",
        body: JSON.stringify({
          provider: form.querySelector('[name="provider"]').value,
          source: form.querySelector('[name="source"]').value,
          item_id: selected.id,
          destination: selected.path,
          execute: false,
        }),
      }),
    "Provider move preview ready."
  );
  if (!result) return;
  state.providerMovePreview = result;
  renderProviderMoveModal();
});

document.querySelector("#providerMoveForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const selected = state.providerItems.find((item) => String(item.id) === form.querySelector('[name="item_id"]').value);
  if (!selected) {
    showMessage("Select a provider item first.", true);
    return;
  }
  if (!window.confirm(`Move contents of ${form.querySelector('[name="source"]').value} into ${selected.path} and refresh ${form.querySelector('[name="provider"]').value}?`)) {
    return;
  }
  const result = await runAction(
    "Moving folder into provider path...",
    () =>
      request("/api/folders/move-to-provider", {
        method: "POST",
        body: JSON.stringify({
          provider: form.querySelector('[name="provider"]').value,
          source: form.querySelector('[name="source"]').value,
          item_id: selected.id,
          destination: selected.path,
          execute: true,
        }),
      }),
    "Folder moved and provider refresh requested."
  );
  if (!result) return;
  state.providerMovePreview = result;
  renderProviderMoveModal();
  closeModal("#providerMoveModal");
});

document.body.addEventListener("click", async (event) => {
  const closeModalButton = event.target.closest("[data-close-modal='add-folder']");
  if (closeModalButton) {
    closeModal("#addFolderModal");
    return;
  }

  const closeProviderModalButton = event.target.closest("[data-close-modal='provider-move']");
  if (closeProviderModalButton) {
    closeModal("#providerMoveModal");
    return;
  }

  const editLanButton = event.target.closest("[data-edit-lan-connection]");
  if (editLanButton) {
    const connection = getLanConnections().find((item) => item.id === editLanButton.dataset.editLanConnection);
    if (!connection) return;
    fillLanConnectionForm(connection);
    setView("settings");
    showMessage("Editing saved SMB profile.");
    return;
  }

  const prefillSmbButton = event.target.closest("[data-prefill-smb-host]");
  if (prefillSmbButton) {
    setAddFolderMode("manual");
    const form = document.querySelector("#lanConnectionForm");
    form.querySelector('[name="label"]').value = prefillSmbButton.dataset.prefillSmbLabel || "";
    form.querySelector('[name="host"]').value = prefillSmbButton.dataset.prefillSmbHost || "";
    setView("settings");
    showMessage("SMB form prefilled. Enter share and credentials, then save once to reuse this profile.");
    return;
  }

  const applyShareButton = event.target.closest("[data-apply-smb-share]");
  if (applyShareButton) {
    const form = document.querySelector("#lanConnectionForm");
    form.querySelector('[name="share_name"]').value = applyShareButton.dataset.applySmbShare || "";
    showMessage("Share name applied. Test again to preview folders in this share.");
    return;
  }

  const applyPathButton = event.target.closest("[data-apply-smb-path]");
  if (applyPathButton) {
    const form = document.querySelector("#lanConnectionForm");
    form.querySelector('[name="base_path"]').value = applyPathButton.dataset.applySmbPath || "";
    showMessage("Base path applied from SMB preview.");
    return;
  }

  const applyRuntimePathButton = event.target.closest("[data-apply-runtime-path]");
  if (applyRuntimePathButton) {
    const value = applyRuntimePathButton.dataset.applyRuntimePath || "";
    const pathInput = document.querySelector('#addFolderForm [name="path"]');
    pathInput.value = value;
    state.runtimePathAutoValue = value;
    state.runtimePathManualOverride = false;
    renderRuntimePathAssist();
    showMessage("Runtime path applied.");
    return;
  }

  const toggleRuntimePathManualButton = event.target.closest("[data-toggle-runtime-path-manual]");
  if (toggleRuntimePathManualButton) {
    state.runtimePathManualOverride = toggleRuntimePathManualButton.dataset.toggleRuntimePathManual === "on";
    renderRuntimePathAssist();
    return;
  }

  const testLanButton = event.target.closest("[data-test-lan-connection]");
  if (testLanButton) {
    const result = await runAction(
      "Testing saved SMB connection...",
      () =>
        request("/api/lan/connections/test", {
          method: "POST",
          body: JSON.stringify({ id: testLanButton.dataset.testLanConnection }),
        }),
      "Saved SMB connection test finished."
    );
    if (!result) return;
    state.lanConnectionTestResult = result;
    renderLanConnections();
    return;
  }

  const deleteLanButton = event.target.closest("[data-delete-lan-connection]");
  if (deleteLanButton) {
    const result = await runAction(
      "Removing SMB connection...",
      () =>
        request(`/api/lan/connections?id=${encodeURIComponent(deleteLanButton.dataset.deleteLanConnection)}`, {
          method: "DELETE",
        }),
      "SMB connection removed."
    );
    if (!result) return;
    if (state.editingLanConnectionId === deleteLanButton.dataset.deleteLanConnection) {
      resetLanConnectionForm();
    }
    return;
  }

  const removeRootButton = event.target.closest("[data-remove-root]");
  if (removeRootButton) {
    await runAction(
      "Removing connected folder...",
      () =>
        request(`/api/roots?path=${encodeURIComponent(removeRootButton.dataset.removeRoot)}`, {
          method: "DELETE",
        }),
      "Connected folder removed."
    );
    return;
  }

  const useMoveSourceButton = event.target.closest("[data-use-move-source]");
  if (useMoveSourceButton) {
    document.querySelector("#moveSourceInput").value = useMoveSourceButton.dataset.useMoveSource;
    setView("operations");
    showMessage("Source folder filled from connected root.");
    return;
  }

  const useMoveDestinationButton = event.target.closest("[data-use-move-destination]");
  if (useMoveDestinationButton) {
    document.querySelector("#moveDestinationInput").value = useMoveDestinationButton.dataset.useMoveDestination;
    setView("operations");
    showMessage("Destination folder filled from connected root.");
    return;
  }

  const runFolderActionButton = event.target.closest("[data-run-folder-action]");
  if (runFolderActionButton) {
    const path = runFolderActionButton.dataset.runFolderAction;
    const select = document.querySelector(`[data-folder-action-select="${CSS.escape(path)}"]`);
    const action = select?.value;
    if (!action) {
      showMessage("Select an action first.", true);
      return;
    }
    if (action === "use-source") {
      document.querySelector("#moveSourceInput").value = path;
      setView("operations");
      showMessage("Source folder filled from folder list.");
      return;
    }
    if (action === "use-destination") {
      document.querySelector("#moveDestinationInput").value = path;
      setView("operations");
      showMessage("Destination folder filled from folder list.");
      return;
    }
    if (action === "remove-root") {
      await runAction(
        "Removing connected folder...",
        () => request(`/api/roots?path=${encodeURIComponent(path)}`, { method: "DELETE" }),
        "Connected folder removed."
      );
      return;
    }
    if (action === "delete-folder") {
      if (!window.confirm(`Delete folder ${path} recursively?`)) return;
      state.movePreview = await runAction(
        "Deleting folder...",
        () => request(`/api/folders?path=${encodeURIComponent(path)}&execute=true`, { method: "DELETE" }),
        "Folder deleted."
      );
      renderMovePreview();
      return;
    }
    if (action === "move-radarr" || action === "move-sonarr") {
      const provider = action === "move-radarr" ? "radarr" : "sonarr";
      const items = await runAction(
        `Loading ${provider} library items...`,
        () => request(`/api/integrations/${provider}/items`),
        null
      );
      if (!items) return;
      state.providerItems = items.items || [];
      state.providerMovePreview = null;
      const form = document.querySelector("#providerMoveForm");
      form.querySelector('[name="provider"]').value = provider;
      form.querySelector('[name="source"]').value = path;
      form.querySelector('[name="item_id"]').value = "";
      document.querySelector("#providerMoveModalTitle").textContent = provider === "radarr" ? "Move To Radarr" : "Move To Sonarr";
      renderProviderMoveModal();
      openModal("#providerMoveModal");
      return;
    }
  }
});

document.querySelector('#addFolderForm [name="path"]').addEventListener("input", (event) => {
  if (event.currentTarget.value.trim() !== state.runtimePathAutoValue) {
    state.runtimePathAutoValue = "";
    state.runtimePathManualOverride = true;
  }
});

resetLanConnectionForm();
renderAddFolderConnectionOptions();
refreshAll().catch((error) => showMessage(error.message, true));
