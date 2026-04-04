const PROCESS_POLL_INTERVAL_MS = 1500;
const DASHBOARD_VIEW_STORAGE_KEY = "media-library-manager.current-view";

const state = {
  payload: null,
  lanDevices: null,
  lanDevicesLoading: false,
  pendingRequests: 0,
  loadingRegions: {},
  mounts: [],
  operationsFolders: [],
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
  providerMoveQuery: "",
  processPoller: null,
  rootsSearchQuery: "",
  selectedRootPaths: {},
  openFolderMenuKey: "",
  runtimePathAutoValue: "",
  runtimePathManualOverride: false,
  manualConnectionRequested: false,
  smbBrowser: null,
  selectedSmbEntries: {},
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

function isKnownView(view) {
  return Object.prototype.hasOwnProperty.call(viewMeta, view);
}

function loadInitialView() {
  try {
    const savedView = window.localStorage.getItem(DASHBOARD_VIEW_STORAGE_KEY);
    if (savedView && isKnownView(savedView)) {
      return savedView;
    }
  } catch {
    // Ignore storage access failures and fall back to the default view.
  }
  return state.currentView;
}

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
  state.pendingRequests += 1;
  renderGlobalLoadingState();
  try {
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
  } finally {
    state.pendingRequests = Math.max(0, state.pendingRequests - 1);
    renderGlobalLoadingState();
  }
}

function renderGlobalLoadingState() {
  const busy = state.pendingRequests > 0;
  document.body.classList.toggle("app-busy", busy);
  const indicator = document.querySelector("#globalLoadingIndicator");
  if (!indicator) return;
  indicator.hidden = !busy;
}

function setLoadingRegion(regionId, active, label = "Loading...") {
  const next = { ...state.loadingRegions };
  if (active) {
    next[regionId] = label;
  } else {
    delete next[regionId];
  }
  state.loadingRegions = next;
  renderLoadingRegions();
}

function renderLoadingRegions() {
  document.querySelectorAll("[data-loading]").forEach((node) => {
    delete node.dataset.loading;
    delete node.dataset.loadingLabel;
  });
  Object.entries(state.loadingRegions).forEach(([regionId, label]) => {
    const node = document.querySelector(regionId);
    if (!node) return;
    node.dataset.loading = "true";
    node.dataset.loadingLabel = label;
  });
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

function setActivityBanner(text = "", { active = false, isError = false } = {}) {
  const addFolderModalOpen = !document.querySelector("#addFolderModal").hidden;
  const providerMoveModalOpen = !document.querySelector("#providerMoveModal").hidden;
  const cleanText = String(text || "").trim();
  const targets = [
    { banner: "#addFolderActivityBanner", title: "#addFolderActivityTitle", body: "#addFolderActivityText", show: addFolderModalOpen },
    { banner: "#providerMoveActivityBanner", title: "#providerMoveActivityTitle", body: "#providerMoveActivityText", show: providerMoveModalOpen },
  ];

  if ((!active && !isError) || (!cleanText && active)) {
    targets.forEach((target) => {
      const banner = document.querySelector(target.banner);
      if (!banner) return;
      banner.hidden = true;
      banner.classList.remove("error");
    });
    return;
  }

  const content = {
    title: isError ? "Failed" : "Working",
    text: cleanText || "The latest action failed.",
  };

  targets.forEach((target) => {
    const banner = document.querySelector(target.banner);
    const title = document.querySelector(target.title);
    const body = document.querySelector(target.body);
    if (!banner || !title || !body) return;
    banner.hidden = !target.show || (!active && !isError);
    banner.classList.toggle("error", isError);
    title.textContent = content.title;
    body.textContent = content.text;
  });
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

function getBasename(path) {
  const parts = String(path || "").split("/").filter(Boolean);
  return parts.length ? parts[parts.length - 1] : String(path || "");
}

function normalizeSearchText(value) {
  return String(value || "")
    .toLowerCase()
    .replaceAll(/[\._()-]+/g, " ")
    .replaceAll(/\s+/g, " ")
    .trim();
}

function scoreProviderItem(item, query) {
  const normalizedQuery = normalizeSearchText(query);
  const title = normalizeSearchText(item.title || "");
  if (!normalizedQuery) return 0;
  if (title === normalizedQuery) return 100;
  if (title.startsWith(normalizedQuery)) return 80;
  if (title.includes(normalizedQuery)) return 60;
  const queryTokens = normalizedQuery.split(" ").filter(Boolean);
  const titleTokens = new Set(title.split(" ").filter(Boolean));
  const tokenMatches = queryTokens.filter((token) => titleTokens.has(token)).length;
  return tokenMatches ? tokenMatches * 10 : 0;
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

function getOperationsFolders() {
  return state.operationsFolders || [];
}

function getSelectedRootPaths() {
  return Object.keys(state.selectedRootPaths || {});
}

function syncRootSelection() {
  const availablePaths = new Set(getOperationsFolders().map((item) => item.path));
  state.selectedRootPaths = Object.fromEntries(
    getSelectedRootPaths()
      .filter((path) => availablePaths.has(path))
      .map((path) => [path, true])
  );
  if (state.openFolderMenuKey === "bulk" && !getSelectedRootPaths().length) {
    state.openFolderMenuKey = "";
  }
  if (state.openFolderMenuKey && state.openFolderMenuKey !== "bulk" && !availablePaths.has(state.openFolderMenuKey)) {
    state.openFolderMenuKey = "";
  }
}

function setRootSelection(path, selected) {
  if (!path) return;
  if (selected) {
    state.selectedRootPaths[path] = true;
  } else {
    delete state.selectedRootPaths[path];
  }
}

function toggleRootSelection(path) {
  setRootSelection(path, !state.selectedRootPaths[path]);
}

function setFilteredRootsSelected(selected) {
  const filteredRoots = getFilteredRoots();
  filteredRoots.forEach((root) => setRootSelection(root.path, selected));
}

function closeFolderActionMenu() {
  state.openFolderMenuKey = "";
}

function toggleFolderActionMenu(key) {
  state.openFolderMenuKey = state.openFolderMenuKey === key ? "" : key;
}

function getFilteredRoots() {
  const roots = getOperationsFolders();
  const searchQuery = state.rootsSearchQuery.trim().toLowerCase();
  return searchQuery
    ? roots.filter((root) =>
        [root.label, root.path, root.display_path, root.connection_label, root.kind, root.root_label]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(searchQuery))
      )
    : roots;
}

function getFolderActionTargets(action, triggerPath = "") {
  if (triggerPath) {
    return [triggerPath];
  }
  return getSelectedRootPaths();
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

function createSmbEntryKey(entry) {
  return [entry.type || "directory", entry.share_name || "", entry.path || "", entry.name || ""].join("::");
}

function getSelectedSmbEntries() {
  return Object.values(state.selectedSmbEntries || {});
}

function applySavedConnection(connection, { forcePath = true, announce = false } = {}) {
  if (!connection) return false;
  state.manualConnectionRequested = false;
  state.selectedLanConnectionId = connection.id;
  setAddFolderMode("smb");
  fillLanConnectionForm(connection);
  applyConnectionToFolderForm(connection, { forcePath });
  renderAddFolderConnectionOptions();
  renderLanConnections();
  if (announce) {
    showMessage("Saved SMB profile applied automatically.");
  }
  return true;
}

function renderConnectionSetupVisibility() {
  const connection = getLanConnections().find((item) => item.id === state.selectedLanConnectionId) || null;
  const hasSelectedProfile = state.addFolderMode === "smb" && Boolean(connection);
  const discoveryCard = document.querySelector("#lanDiscoveryCard");
  const manualForm = document.querySelector("#lanConnectionForm");
  const testSummary = document.querySelector("#lanConnectionTestSummary");

  discoveryCard.hidden = hasSelectedProfile;
  manualForm.hidden = state.addFolderMode !== "manual" || !state.manualConnectionRequested;
  testSummary.hidden = state.addFolderMode !== "manual" || !state.manualConnectionRequested;
}

function setView(view) {
  const nextView = isKnownView(view) ? view : "operations";
  state.currentView = nextView;
  try {
    window.localStorage.setItem(DASHBOARD_VIEW_STORAGE_KEY, nextView);
  } catch {
    // Ignore storage access failures and keep the UI responsive.
  }
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === nextView);
  });
  document.querySelectorAll(".view").forEach((node) => {
    node.classList.toggle("active", node.id === `${nextView}View`);
  });
  const meta = viewMeta[nextView] || viewMeta.operations;
  document.querySelector("#viewTitle").textContent = meta.title;
  document.querySelector("#viewDescription").textContent = meta.description;
}

function openModal(modalId) {
  document.querySelector(modalId).hidden = false;
  setActivityBanner();
}

function closeModal(modalId) {
  document.querySelector(modalId).hidden = true;
  setActivityBanner();
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
  if (mode !== "manual") {
    state.manualConnectionRequested = false;
  }
  if (mode === "direct") {
    state.smbBrowser = null;
    state.selectedSmbEntries = {};
  }
  renderConnectionSetupVisibility();
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
  if (!mount.is_network) return 0;
  let score = 2;

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

  const networkMounts = mounts.filter((mount) => mount.is_network);
  const suggestions = networkMounts
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

  return networkMounts
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
  if (!node || !runtimePathField) {
    return;
  }
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
          <div class="runtime-path-note">Use one of the local paths the app can already reach.</div>
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
      : `<div class="empty-state">No local path shortcuts discovered yet. Enter a direct runtime path manually if you still want one.</div>`;
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
          <strong>Local Path Shortcuts</strong>
          <span class="pill small accent">${escapeHtml(String(suggestions.length))}</span>
        </div>
        <div class="runtime-path-note">These local mounts are optional shortcuts only. SMB-native access works without mounting the share first.</div>
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
        <strong>SMB-Native Ready</strong>
        <span class="pill small accent">Optional</span>
      </div>
      <div class="runtime-path-note">No local mount shortcut was found for this SMB profile. You can still add and manage this folder directly over SMB.</div>
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

async function startProviderMove(provider, sourcePath) {
  const items = await runAction(
    `Loading ${provider} library items...`,
    () => request(`/api/integrations/${provider}/items`),
    null
  );
  if (!items) return;
  state.providerItems = items.items || [];
  state.providerMovePreview = null;
  state.providerMoveQuery = getBasename(sourcePath);
  const form = document.querySelector("#providerMoveForm");
  form.querySelector('[name="provider"]').value = provider;
  form.querySelector('[name="source"]').value = sourcePath;
  form.querySelector('[name="item_id"]').value = "";
  document.querySelector("#providerMoveModalTitle").textContent = provider === "radarr" ? "Choose Radarr Movie" : "Choose Sonarr Series";
  document.querySelector("#providerMoveModalDescription").textContent = provider === "radarr"
    ? "Find the movie already managed by Radarr. The folder will be moved into Radarr's managed movie path."
    : "Find the series already managed by Sonarr. The folder will be moved into Sonarr's managed series path.";
  renderProviderMoveModal();
  openModal("#providerMoveModal");
}

async function handleFolderAction(action, paths) {
  const targets = [...new Set((paths || []).filter(Boolean))];
  if (!targets.length) {
    showMessage("Select one or more folders first.", true);
    return;
  }

  closeFolderActionMenu();

  if (action === "move-radarr" || action === "move-sonarr") {
    if (targets.length !== 1) {
      showMessage("Choose exactly one folder before moving into a provider path.", true);
      return;
    }
    const provider = action === "move-radarr" ? "radarr" : "sonarr";
    await startProviderMove(provider, targets[0]);
    return;
  }

  if (action === "remove-root") {
    await runAction(
      targets.length === 1 ? "Removing connected folder..." : "Removing connected folders...",
      async () => {
        for (const path of targets) {
          await request(`/api/roots?path=${encodeURIComponent(path)}`, { method: "DELETE" });
        }
        return { removed: targets.length };
      },
      targets.length === 1 ? "Connected folder removed." : `${targets.length} connected folders removed.`
    );
    return;
  }

  if (action === "delete-folder") {
    const confirmation = targets.length === 1
      ? `Delete folder ${targets[0]} recursively?`
      : `Delete ${targets.length} folders recursively?`;
    if (!window.confirm(confirmation)) return;
    state.movePreview = await runAction(
      targets.length === 1 ? "Deleting folder..." : "Deleting folders...",
      async () => {
        let result = null;
        for (const path of targets) {
          result = await request(`/api/folders?path=${encodeURIComponent(path)}&execute=true`, { method: "DELETE" });
        }
        return result;
      },
      targets.length === 1 ? "Folder deleted." : `${targets.length} folders deleted.`
    );
  }
}

function renderRoots() {
  const roots = getPayload().roots || [];
  const operationsFolders = getOperationsFolders();
  const filteredRoots = getFilteredRoots();
  syncRootSelection();
  const selectedPaths = getSelectedRootPaths();
  const visibleSelectionCount = filteredRoots.filter((root) => state.selectedRootPaths[root.path]).length;
  const hasVisibleRoots = filteredRoots.length > 0;
  const allVisibleSelected = hasVisibleRoots && visibleSelectionCount === filteredRoots.length;
  document.querySelector("#toggleFolderBulkMenuButton").disabled = !selectedPaths.length;

  const selectAllCheckbox = document.querySelector("#operationsRootsSelectAll");
  selectAllCheckbox.checked = allVisibleSelected;
  selectAllCheckbox.indeterminate = visibleSelectionCount > 0 && !allVisibleSelected;
  selectAllCheckbox.disabled = !hasVisibleRoots;

  const bulkMenu = document.querySelector("#folderBulkMenu");
  const bulkMenuButton = document.querySelector("#toggleFolderBulkMenuButton");
  const bulkMenuOpen = state.openFolderMenuKey === "bulk" && selectedPaths.length > 0;
  bulkMenu.hidden = !bulkMenuOpen;
  bulkMenuButton.setAttribute("aria-expanded", bulkMenuOpen ? "true" : "false");
  document.querySelectorAll("[data-bulk-folder-action='move-radarr'], [data-bulk-folder-action='move-sonarr']").forEach((item) => {
    item.disabled = selectedPaths.length !== 1;
  });

  document.querySelector("#operationsRootsCount").textContent = `${filteredRoots.length} folder${filteredRoots.length === 1 ? "" : "s"}`;
  document.querySelector("#operationsRootsFilterSummary").textContent = !operationsFolders.length
    ? "No folders discovered inside connected roots yet."
    : state.rootsSearchQuery.trim()
      ? `Showing ${filteredRoots.length} of ${operationsFolders.length} folders inside connected roots.`
      : `${operationsFolders.length} folders discovered inside connected roots.`;
  document.querySelector("#folderSelectionActions").hidden = !operationsFolders.length;
  document.querySelector("#folderSelectionStatus").textContent = `${selectedPaths.length} selected`;
  document.querySelector("#useSelectedAsSourceButton").disabled = selectedPaths.length !== 1;
  document.querySelector("#useSelectedAsDestinationButton").disabled = selectedPaths.length !== 1;

  const operationsHtml = filteredRoots.length
    ? filteredRoots
        .map(
          (root) => {
            const isSelected = Boolean(state.selectedRootPaths[root.path]);
            const isMenuOpen = state.openFolderMenuKey === root.path;
            return `
            <div class="folder-list-item ${isSelected ? "is-selected" : ""}">
              <sl-checkbox
                class="folder-library-checkbox folder-list-select"
                data-root-selection-checkbox="${escapeHtml(root.path)}"
                aria-label="Select ${escapeHtml(root.label)}"
                ${isSelected ? "checked" : ""}
              ></sl-checkbox>
              <button class="folder-list-main folder-list-main-button" type="button" data-toggle-root-selection="${escapeHtml(root.path)}">
                <span class="folder-row-name">${escapeHtml(root.label)}</span>
                <span class="folder-row-badges">
                  <span class="pill small">P${root.priority}</span>
                </span>
              </button>
              <div class="folder-path">${escapeHtml(root.display_path || root.path)}</div>
              <div class="folder-row-profile">${escapeHtml(root.connection_label || root.root_label || "Direct path")}</div>
              <div class="folder-row-kind"><span class="pill small">${escapeHtml(root.kind)}</span></div>
              <div class="folder-list-actions">
                <div class="folder-action-menu-shell">
                  <button
                    class="btn btn-small btn-icon"
                    type="button"
                    data-open-folder-menu="${escapeHtml(root.path)}"
                    aria-haspopup="menu"
                    aria-expanded="${isMenuOpen ? "true" : "false"}"
                  >
                    ⋯
                  </button>
                  <div class="folder-action-menu" role="menu" ${isMenuOpen ? "" : "hidden"}>
                    <button class="folder-action-menu-item" type="button" role="menuitem" data-folder-menu-action="move-radarr" data-folder-menu-path="${escapeHtml(root.path)}">
                      Move To Radarr...
                    </button>
                    <button class="folder-action-menu-item" type="button" role="menuitem" data-folder-menu-action="move-sonarr" data-folder-menu-path="${escapeHtml(root.path)}">
                      Move To Sonarr...
                    </button>
                    <button class="folder-action-menu-item danger" type="button" role="menuitem" data-folder-menu-action="delete-folder" data-folder-menu-path="${escapeHtml(root.path)}">
                      Delete Folder...
                    </button>
                  </div>
                </div>
              </div>
            </div>`;
          }
        )
        .join("")
    : `<div class="empty-state">${operationsFolders.length ? "No folders match the current filter." : "No folders discovered inside connected roots yet. Add a root in Settings, then scan or browse that root."}</div>`;

  const settingsHtml = roots.length
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
                <button class="btn btn-small" data-remove-root="${escapeHtml(root.path)}">Remove</button>
              </div>
            </div>`
        )
        .join("")
    : `<div class="empty-state">No connected folders yet. Add one from Settings.</div>`;

  document.querySelector("#operationsRootsList").innerHTML = operationsHtml;
  document.querySelector("#settingsRootsList").innerHTML = settingsHtml;
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

  const deleteButton = document.querySelector("#deleteSelectedLanConnectionButton");
  deleteButton.hidden = !state.selectedLanConnectionId;
  deleteButton.disabled = !state.selectedLanConnectionId;

  const result = state.lanConnectionTestResult;
  const testSummary = document.querySelector("#lanConnectionTestSummary");
  testSummary.hidden = !result;
  testSummary.innerHTML = result
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
    : "";
}

function renderConnectionSummary() {
  const connection = getLanConnections().find((item) => item.id === state.selectedLanConnectionId);
  const connectionSummary = document.querySelector("#selectedConnectionSummary");
  renderConnectionSetupVisibility();

  if (state.addFolderMode === "direct") {
    const html = `<div class="connection-inline-summary">Using direct runtime path. No SMB profile is attached.</div>`;
    connectionSummary.innerHTML = html;
    renderRuntimePathAssist();
    return;
  }

  if (!connection) {
    connectionSummary.innerHTML = "";
    return;
  }

  const html = `<div class="connection-inline-summary">Using <strong>${escapeHtml(connection.label)}</strong> • //${escapeHtml(
    connection.host
  )}${connection.share_name ? `/${escapeHtml(connection.share_name)}` : ""}</div>`;
  connectionSummary.innerHTML = html;
}

function createVirtualConnectionForBrowserEntry(connection, browser, entry) {
  if (!connection || !browser || !entry) return null;
  if (entry.type === "share") {
    return {
      ...connection,
      share_name: entry.share_name || entry.name || "",
      base_path: "/",
    };
  }
  return {
    ...connection,
    share_name: entry.share_name || browser.connection?.share_name || connection.share_name,
    base_path: entry.path || "/",
  };
}

function normalizeSmbRootPath(pathValue) {
  const clean = String(pathValue || "").trim();
  if (!clean || clean === ".") return "/";
  return `/${clean.replace(/^\/+/, "").replace(/\/+$/, "")}`;
}

function getSmbShareNameForEntry(connection, browser, entry) {
  if (!entry) return "";
  if (entry.type === "share") {
    return String(entry.share_name || entry.name || "").trim().replace(/^\/+|\/+$/g, "");
  }
  return String(entry.share_name || browser?.connection?.share_name || connection?.share_name || "").trim().replace(/^\/+|\/+$/g, "");
}

function encodeSmbUriPath(pathValue) {
  const normalized = normalizeSmbRootPath(pathValue);
  if (normalized === "/") return "/";
  return `/${normalized
    .slice(1)
    .split("/")
    .filter(Boolean)
    .map((part) => encodeURIComponent(part))
    .join("/")}`;
}

function createSmbStorageUri(connection, browser, entry) {
  const connectionId = String(connection?.id || "").trim();
  const shareName = getSmbShareNameForEntry(connection, browser, entry);
  if (!connectionId || !shareName) return "";
  const entryPath = entry?.type === "share" ? "/" : entry?.path || "/";
  const encodedShare = encodeURIComponent(shareName);
  const encodedPath = encodeSmbUriPath(entryPath);
  return `smb://${encodedShare}${encodedPath}?connection_id=${encodeURIComponent(connectionId)}`;
}

function toSmbPseudoSegment(value, fallback = "unknown") {
  const text = String(value || "").trim().replaceAll("/", "_");
  return text || fallback;
}

function createSmbPseudoRootPath(connection, browser, entry) {
  const connectionSegment = toSmbPseudoSegment(connection?.id, "connection");
  const shareSegment = toSmbPseudoSegment(getSmbShareNameForEntry(connection, browser, entry), "share");
  const rootPath = normalizeSmbRootPath(entry?.type === "share" ? "/" : entry?.path || "/");
  const base = `/smb/${connectionSegment}/${shareSegment}`;
  if (rootPath === "/") return base;
  return `${base}${rootPath}`.replace(/\/{2,}/g, "/");
}

function createSmbRootPayload(connection, browser, entry, form) {
  const shareName = getSmbShareNameForEntry(connection, browser, entry);
  const storageUri = createSmbStorageUri(connection, browser, entry);
  if (!shareName || !storageUri) return null;
  return {
    path: createSmbPseudoRootPath(connection, browser, entry),
    storage_uri: storageUri,
    share_name: shareName,
    label: entry.name,
    priority: form.querySelector('[name="priority"]').value.trim(),
    kind: form.querySelector('[name="kind"]').value,
    connection_id: connection.id,
    connection_label: connection?.label || "",
  };
}

function getRuntimeSuggestionForSmbEntry(connection, browser, entry) {
  const virtualConnection = createVirtualConnectionForBrowserEntry(connection, browser, entry);
  if (!virtualConnection) return "";
  return buildRuntimePathSuggestions(virtualConnection)[0]?.path || "";
}

function formatSmbRuntimeStatus(runtimePath) {
  return runtimePath || "SMB-native access";
}

async function loadSmbBrowser({ shareName = "", path = "/", scope = "" } = {}) {
  const connection = getLanConnections().find((item) => item.id === state.selectedLanConnectionId);
  if (!connection) return null;
  const params = new URLSearchParams({ connection_id: connection.id });
  if (scope) params.set("scope", scope);
  if (shareName) params.set("share_name", shareName);
  if (path && path !== "/") params.set("path", path);
  setLoadingRegion("#smbFolderBrowser", true, "Loading SMB folders...");
  setLoadingRegion("#smbSelectionSummary", true, "Refreshing selection...");
  try {
    const result = await request(`/api/smb/browse?${params.toString()}`);
    state.smbBrowser = result;
    renderFolderStep();
    return result;
  } finally {
    setLoadingRegion("#smbFolderBrowser", false);
    setLoadingRegion("#smbSelectionSummary", false);
  }
}

function renderSmbBrowser() {
  const browserNode = document.querySelector("#smbFolderBrowser");
  const crumbsNode = document.querySelector("#smbBrowserBreadcrumbs");
  const summaryNode = document.querySelector("#smbSelectionSummary");
  const connection = getLanConnections().find((item) => item.id === state.selectedLanConnectionId) || null;
  const browser = state.smbBrowser;

  if (!browserNode || !crumbsNode || !summaryNode) return;

  if (!connection || !browser) {
    browserNode.innerHTML = `<div class="empty-state">Select or save an SMB profile above, then load shares or folders for this host.</div>`;
    crumbsNode.innerHTML = "";
    summaryNode.innerHTML = `<div class="empty-state">Choose one or more SMB shares or folders to add them together.</div>`;
    return;
  }

  crumbsNode.innerHTML = (browser.breadcrumbs || [])
    .map(
      (crumb, index) => `
        <button
          class="crumb"
          type="button"
          data-browse-smb-crumb="true"
          data-browse-smb-share="${escapeHtml(crumb.share_name || "")}"
          data-browse-smb-path="${escapeHtml(crumb.path || "/")}"
          ${index === browser.breadcrumbs.length - 1 ? "aria-current='page'" : ""}
        >
          ${escapeHtml(crumb.name || "/")}
        </button>`
    )
    .join("");

  browserNode.innerHTML = browser.entries?.length
    ? browser.entries
        .map((entry) => {
          const key = createSmbEntryKey(entry);
          const checked = Boolean(state.selectedSmbEntries[key]);
          const runtimePath = getRuntimeSuggestionForSmbEntry(connection, browser, entry);
          const canBrowse = entry.type === "share" || entry.type === "directory";
          const selectable = Boolean(getSmbShareNameForEntry(connection, browser, entry));
          return `
            <div class="collection-item vertical smb-browser-item ${selectable ? "" : "is-unavailable"}">
              <div class="row split">
                <label class="row smb-browser-select">
                  <sl-checkbox
                    class="folder-library-checkbox"
                    data-toggle-smb-entry="${escapeHtml(key)}"
                    ${checked ? "checked" : ""}
                    ${selectable ? "" : "disabled"}
                  ></sl-checkbox>
                  <strong>${escapeHtml(entry.name)}</strong>
                </label>
                <span class="pill small ${selectable ? (entry.type === "directory" ? "accent" : "") : ""}">${
                  selectable ? escapeHtml(entry.type) : "unavailable"
                }</span>
              </div>
              ${entry.comment ? `<div class="muted">${escapeHtml(entry.comment)}</div>` : ""}
              <div class="sub-row"><span>Runtime (optional)</span><span>${escapeHtml(formatSmbRuntimeStatus(runtimePath))}</span></div>
              ${
                canBrowse
                  ? `<div class="field-row">
                      <button
                        class="btn btn-small"
                        type="button"
                        data-browse-smb-entry="true"
                        data-browse-smb-share="${escapeHtml(entry.share_name || browser.connection?.share_name || "")}"
                        data-browse-smb-path="${escapeHtml(entry.path || "/")}"
                      >
                        Browse
                      </button>
                    </div>`
                  : ""
              }
            </div>`;
        })
        .join("")
    : `<div class="empty-state">No SMB shares or folders found at this level.</div>`;

  const selections = getSelectedSmbEntries();
  const availableCount = (browser.entries || []).filter((entry) => Boolean(getSmbShareNameForEntry(connection, browser, entry))).length;
  summaryNode.innerHTML = selections.length
    ? selections
        .map((entry) => {
          const runtimePath = getRuntimeSuggestionForSmbEntry(connection, browser, entry);
          return `
            <div class="collection-item vertical">
              <div class="row split">
                <strong>${escapeHtml(entry.name)}</strong>
                <button class="btn btn-small" type="button" data-remove-smb-entry="${escapeHtml(createSmbEntryKey(entry))}">Remove</button>
              </div>
              <div class="muted">${escapeHtml(entry.share_name || browser.connection?.share_name || "")}</div>
              <div class="sub-row"><span>Runtime (optional)</span><span>${escapeHtml(formatSmbRuntimeStatus(runtimePath))}</span></div>
            </div>`;
        })
        .join("")
    : `<div class="empty-state">${
        availableCount
          ? "Choose one or more SMB shares or folders to add them together."
          : "No addable SMB folders at this level yet. Browse into a share and choose folders there."
      }</div>`;
}

function renderFolderStep() {
  const folderStepCard = document.querySelector("#folderStepCard");
  const connection = getLanConnections().find((item) => item.id === state.selectedLanConnectionId);
  const ready = state.addFolderMode === "direct" || Boolean(connection);
  folderStepCard.hidden = !ready;
  document.querySelector("#smbFolderPicker").hidden = state.addFolderMode === "direct";
  document.querySelector("#directFolderFields").hidden = state.addFolderMode !== "direct";
  if (ready && state.addFolderMode === "direct") {
    renderRuntimePathAssist();
  }
  if (ready && state.addFolderMode !== "direct") {
    renderSmbBrowser();
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
          const preferredHost = device.ip_address || device.hostname || device.device_key;
          const preferredSmb = services.find((service) => service.service_type === "_smb._tcp");
          const smbTarget = preferredSmb ? `smb://${preferredHost}` : preferredHost;
          return `
            <button class="collection-item action-card lan-device-card" type="button" data-prefill-smb-host="${escapeHtml(
              preferredHost
            )}" data-prefill-smb-label="${escapeHtml(device.display_name || preferredHost)}">
              <div class="lan-device-header">
                <div class="lan-device-copy">
                  <strong>${escapeHtml(device.display_name || preferredHost)}</strong>
                  <div class="muted">${escapeHtml(smbTarget)}</div>
                </div>
                <span class="pill small ${preferredSmb ? "accent" : ""}">${preferredSmb ? "SMB" : "Host"}</span>
              </div>
            </button>`;
        })
        .join("")
    : `<div class="empty-state">No LAN devices discovered yet. Use Refresh LAN, or enter an IP manually in the SMB form.</div>`;
}

async function refreshLanDevices(showToast = true) {
  state.lanDevicesLoading = true;
  setLoadingRegion("#lanDevicesList", true, "Scanning LAN...");
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
    setLoadingRegion("#lanDevicesList", false);
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

function renderProviderMoveModal() {
  const form = document.querySelector("#providerMoveForm");
  const select = document.querySelector("#providerItemSelect");
  const searchInput = document.querySelector("#providerItemSearchInput");
  const currentValue = form.querySelector('[name="item_id"]').value;
  if (searchInput && searchInput.value !== state.providerMoveQuery) {
    searchInput.value = state.providerMoveQuery;
  }

  const rankedItems = state.providerItems
    .map((item) => ({ item, score: scoreProviderItem(item, state.providerMoveQuery) }))
    .filter(({ item, score }) => {
      if (!state.providerMoveQuery.trim()) return true;
      return score > 0 || normalizeSearchText(item.title).includes(normalizeSearchText(state.providerMoveQuery));
    })
    .sort((left, right) => right.score - left.score || String(left.item.title).localeCompare(String(right.item.title)));

  const visibleItems = rankedItems.map(({ item }) => item);
  const selectedValue = visibleItems.some((item) => String(item.id) === currentValue)
    ? currentValue
    : visibleItems[0]
      ? String(visibleItems[0].id)
      : "";

  const options = ['<option value="">Select destination item</option>']
    .concat(
      visibleItems.map(
        (item) =>
          `<option value="${escapeHtml(String(item.id))}">${escapeHtml(item.title)}${item.year ? ` (${escapeHtml(String(item.year))})` : ""}</option>`
      )
    )
    .join("");
  select.innerHTML = options;
  form.querySelector('[name="item_id"]').value = selectedValue;
  select.value = selectedValue;
  document.querySelector("#previewProviderMoveButton").disabled = !selectedValue;
  form.querySelector('[type="submit"]').disabled = !selectedValue;

  const selected = state.providerItems.find((item) => String(item.id) === selectedValue);
  const preview = state.providerMovePreview;
  document.querySelector("#providerItemMeta").innerHTML = selected
    ? `
      <div class="collection-item vertical">
        <div class="row split">
          <strong>${escapeHtml(selected.title)}${selected.year ? ` (${escapeHtml(String(selected.year))})` : ""}</strong>
          <span class="pill small">${escapeHtml(form.querySelector('[name="provider"]').value || "provider")}</span>
        </div>
        <div class="sub-row"><span>Managed Path</span><span>${escapeHtml(selected.path || "-")}</span></div>
        ${
          preview?.move_result
            ? `<div class="sub-row"><span>Preview</span><span>${escapeHtml(preview.move_result.destination || preview.move_result.destination_parent || "-")}</span></div>`
            : ""
        }
      </div>`
    : `<div class="empty-state">${state.providerMoveQuery.trim() ? "No matching provider item found for that title." : "Type a movie or series name to narrow the destination list."}</div>`;
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
  renderConnectionSetupVisibility();
  renderConnectionSummary();
  renderLanDevices();
  renderFolderStep();
  renderIntegrations();
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
  const regions = [
    "#operationsRootsList",
    "#settingsRootsList",
    "#recentActivityList",
    "#currentJobLogs",
    "#exactDuplicatesList",
    "#reportList",
    "#planList",
    "#applySummary",
  ];
  regions.forEach((regionId) => setLoadingRegion(regionId, true, "Loading..."));
  try {
    const [payload, processPayload, lanPayload, mountsPayload, operationsFoldersPayload] = await Promise.all([
      request("/api/state"),
      request("/api/process"),
      request("/api/lan/discover"),
      request("/api/system/mounts"),
      request("/api/operations/folders"),
    ]);
    state.payload = payload;
    state.currentJob = processPayload.current_job || payload.current_job || null;
    state.lanDevices = lanPayload;
    state.mounts = mountsPayload.mounts || [];
    state.operationsFolders = operationsFoldersPayload.items || [];
    syncRootSelection();
    render();
    if (state.currentJob) {
      startProcessPolling();
    } else {
      stopProcessPolling();
    }
  } finally {
    regions.forEach((regionId) => setLoadingRegion(regionId, false));
  }
}

async function runAction(label, action, successMessage) {
  setServerStatus(label);
  setActivityBanner(label, { active: true });
  startProcessPolling();
  try {
    const result = await action();
    await refreshAll();
    setServerStatus("Dashboard ready");
    setActivityBanner();
    if (successMessage) showMessage(successMessage);
    return result;
  } catch (error) {
    try {
      await refreshAll();
    } catch {
      // keep original error
    }
    setServerStatus("Action failed");
    setActivityBanner(error.message, { isError: true });
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
  state.manualConnectionRequested = false;
  state.selectedLanConnectionId = "";
  state.addFolderMode = "smb";
  state.smbBrowser = null;
  state.selectedSmbEntries = {};
  document.querySelector("#lanConnectionForm").hidden = true;
  renderAddFolderConnectionOptions();
  const autoConnection = chooseDefaultLanConnection();
  if (autoConnection) {
    state.selectedSmbEntries = {};
    applySavedConnection(autoConnection, { forcePath: true, announce: false });
    loadSmbBrowser({ scope: "host" }).catch((error) =>
      showMessage(error.message, true)
    );
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
  if (state.addFolderMode === "direct") {
    const payload = {
      path: form.querySelector('[name="path"]').value.trim(),
      label: form.querySelector('[name="label"]').value.trim(),
      priority: form.querySelector('[name="direct_priority"]').value.trim(),
      kind: form.querySelector('[name="direct_kind"]').value,
      connection_id: "",
      connection_label: "",
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
    return;
  }

  const profileId = form.querySelector('[name="connection_id"]').value;
  const connection = getLanConnections().find((item) => item.id === profileId);
  const browser = state.smbBrowser;
  const selectedEntries = getSelectedSmbEntries();
  if (!connection || !browser) {
    showMessage("Select an SMB profile and load shares or folders first.", true);
    return;
  }
  if (!selectedEntries.length) {
    showMessage("Choose one or more SMB shares or folders first.", true);
    return;
  }

  const roots = selectedEntries.map((entry) => ({
    payload: createSmbRootPayload(connection, browser, entry, form),
    label: entry.name,
  }));
  const unresolved = roots.filter((item) => !item.payload).map((item) => item.label);
  if (unresolved.length) {
    const label = unresolved.slice(0, 3).join(", ");
    const suffix = unresolved.length > 3 ? ` and ${unresolved.length - 3} more` : "";
    showMessage(`Cannot determine SMB share/path for ${label}${suffix}. Browse into a share and try again.`, true);
    return;
  }
  const rootPayload = roots.map((item) => item.payload);

  const result = await runAction(
    "Adding connected folders...",
    () =>
      request("/api/roots/bulk", {
        method: "POST",
        body: JSON.stringify({ roots: rootPayload }),
      }),
    selectedEntries.length === 1 ? "Connected folder added." : `${selectedEntries.length} connected folders added.`
  );
  if (!result) return;
  closeModal("#addFolderModal");
});

document.querySelector("#savedLanConnectionSelect").addEventListener("change", (event) => {
  const connection = getLanConnections().find((item) => item.id === event.currentTarget.value);
  if (!connection) {
    state.manualConnectionRequested = false;
    state.selectedLanConnectionId = "";
    state.smbBrowser = null;
    state.selectedSmbEntries = {};
    renderConnectionSummary();
    renderFolderStep();
    return;
  }
  state.selectedSmbEntries = {};
  applySavedConnection(connection, { forcePath: true, announce: false });
  loadSmbBrowser({ scope: "host" }).catch((error) => showMessage(error.message, true));
});

document.querySelector("#deleteSelectedLanConnectionButton").addEventListener("click", async () => {
  const connection = getLanConnections().find((item) => item.id === state.selectedLanConnectionId);
  if (!connection) {
    showMessage("Select a saved profile first.", true);
    return;
  }

  const affectedRoots = (getPayload().roots || []).filter((root) => root.connection_id === connection.id);
  const warning = affectedRoots.length
    ? ` This profile is still linked to ${affectedRoots.length} connected folder(s).`
    : "";
  if (!window.confirm(`Delete SMB profile ${connection.label}?${warning}`)) return;

  const result = await runAction(
    "Removing SMB connection...",
    () =>
      request(`/api/lan/connections?id=${encodeURIComponent(connection.id)}`, {
        method: "DELETE",
      }),
    "SMB connection removed."
  );
  if (!result) return;

  state.selectedLanConnectionId = "";
  state.editingLanConnectionId = null;
  state.manualConnectionRequested = false;
  resetLanConnectionForm();
  renderAddFolderConnectionOptions();
  renderConnectionSetupVisibility();
  renderConnectionSummary();
  renderFolderStep();
});

document.querySelector("#openManualSmbButton").addEventListener("click", () => {
  state.manualConnectionRequested = true;
  setAddFolderMode("manual");
  showMessage("Manual SMB form opened.");
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
    state.selectedSmbEntries = {};
    applySavedConnection(saved, { forcePath: true, announce: false });
    loadSmbBrowser({ shareName: saved.share_name || "", path: saved.base_path || "/" }).catch((error) => showMessage(error.message, true));
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
    state.smbBrowser = null;
    state.selectedSmbEntries = {};
    renderConnectionSummary();
    renderFolderStep();
    return;
  }
  state.selectedSmbEntries = {};
  applySavedConnection(connection, { forcePath: true, announce: false });
  loadSmbBrowser({ shareName: connection.share_name || "", path: connection.base_path || "/" }).catch((error) => showMessage(error.message, true));
});

document.querySelector("#refreshLanDevicesButton").addEventListener("click", async () => {
  setServerStatus("Discovering LAN devices...");
  setActivityBanner("Discovering LAN devices...", { active: true });
  await refreshLanDevices(true);
  setServerStatus("Dashboard ready");
  setActivityBanner();
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

document.querySelector("#providerItemSelect").addEventListener("change", () => {
  state.providerMovePreview = null;
  renderProviderMoveModal();
});

document.querySelector("#providerItemSearchInput").addEventListener("input", (event) => {
  state.providerMoveQuery = event.currentTarget.value || "";
  state.providerMovePreview = null;
  renderProviderMoveModal();
});

document.querySelector("#operationsRootsSearchInput").addEventListener("input", (event) => {
  state.rootsSearchQuery = event.currentTarget.value || "";
  closeFolderActionMenu();
  renderRoots();
});

document.querySelector("#operationsRootsSelectAll").addEventListener("sl-change", (event) => {
  setFilteredRootsSelected(event.currentTarget.checked);
  closeFolderActionMenu();
  renderRoots();
});

document.querySelector("#moveSelectedToRadarrButton").addEventListener("click", async () => {
  await handleFolderAction("move-radarr", getSelectedRootPaths());
});

document.querySelector("#moveSelectedToSonarrButton").addEventListener("click", async () => {
  await handleFolderAction("move-sonarr", getSelectedRootPaths());
});

document.querySelector("#toggleFolderBulkMenuButton").addEventListener("click", () => {
  toggleFolderActionMenu("bulk");
  renderRoots();
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
  const clickedInsideFolderMenu = event.target.closest(".folder-action-menu-shell");
  if (!clickedInsideFolderMenu) {
    closeFolderActionMenu();
    renderRoots();
  }

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
    state.manualConnectionRequested = true;
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
    const shareName = applyShareButton.dataset.applySmbShare || "";
    form.querySelector('[name="share_name"]').value = shareName;
    if (state.selectedLanConnectionId) {
      state.selectedSmbEntries = {};
      await runAction("Loading SMB folders...", () => loadSmbBrowser({ shareName, path: "/" }), null);
      showMessage(`Loaded share ${shareName}.`);
      return;
    }
    showMessage("Share name applied. Save or select this SMB profile to browse folders in that share.");
    return;
  }

  const browseSmbEntryButton = event.target.closest("[data-browse-smb-entry]");
  if (browseSmbEntryButton) {
    await runAction(
      "Loading SMB folders...",
      () =>
        loadSmbBrowser({
          shareName: browseSmbEntryButton.dataset.browseSmbShare || "",
          path: browseSmbEntryButton.dataset.browseSmbPath || "/",
        }),
      null
    );
    return;
  }

  const browseSmbCrumbButton = event.target.closest("[data-browse-smb-crumb]");
  if (browseSmbCrumbButton) {
    await runAction(
      "Loading SMB folders...",
      () =>
        loadSmbBrowser({
          shareName: browseSmbCrumbButton.dataset.browseSmbShare || "",
          path: browseSmbCrumbButton.dataset.browseSmbPath || "/",
        }),
      null
    );
    return;
  }

  const removeSmbEntryButton = event.target.closest("[data-remove-smb-entry]");
  if (removeSmbEntryButton) {
    delete state.selectedSmbEntries[removeSmbEntryButton.dataset.removeSmbEntry];
    renderSmbBrowser();
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

  const toggleRootSelectionButton = event.target.closest("[data-toggle-root-selection]");
  if (toggleRootSelectionButton) {
    toggleRootSelection(toggleRootSelectionButton.dataset.toggleRootSelection);
    renderRoots();
    return;
  }

  const openFolderMenuButton = event.target.closest("[data-open-folder-menu]");
  if (openFolderMenuButton) {
    toggleFolderActionMenu(openFolderMenuButton.dataset.openFolderMenu);
    renderRoots();
    return;
  }

  const folderMenuActionButton = event.target.closest("[data-folder-menu-action]");
  if (folderMenuActionButton) {
    const action = folderMenuActionButton.dataset.folderMenuAction;
    const path = folderMenuActionButton.dataset.folderMenuPath || "";
    await handleFolderAction(action, getFolderActionTargets(action, path));
    return;
  }

  const bulkFolderActionButton = event.target.closest("[data-bulk-folder-action]");
  if (bulkFolderActionButton) {
    const action = bulkFolderActionButton.dataset.bulkFolderAction;
    const path = bulkFolderActionButton.dataset.folderMenuPath || "";
    await handleFolderAction(action, getFolderActionTargets(action, path));
  }
});

document.body.addEventListener("sl-change", (event) => {
  const smbEntryToggle = event.target.closest("[data-toggle-smb-entry]");
  if (smbEntryToggle) {
    const key = smbEntryToggle.dataset.toggleSmbEntry;
    const browser = state.smbBrowser;
    const entry = browser?.entries?.find((item) => createSmbEntryKey(item) === key);
    if (!entry) return;
    if (smbEntryToggle.checked) {
      state.selectedSmbEntries[key] = entry;
    } else {
      delete state.selectedSmbEntries[key];
    }
    renderSmbBrowser();
    return;
  }

  const rootSelectionCheckbox = event.target.closest("[data-root-selection-checkbox]");
  if (!rootSelectionCheckbox) return;
  setRootSelection(rootSelectionCheckbox.dataset.rootSelectionCheckbox, rootSelectionCheckbox.checked);
  renderRoots();
});

document.querySelector('#addFolderForm [name="path"]').addEventListener("input", (event) => {
  if (event.currentTarget.value.trim() !== state.runtimePathAutoValue) {
    state.runtimePathAutoValue = "";
    state.runtimePathManualOverride = true;
  }
});

resetLanConnectionForm();
renderAddFolderConnectionOptions();
setView(loadInitialView());
refreshAll().catch((error) => showMessage(error.message, true));
