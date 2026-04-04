const state = {
  payload: null,
  mounts: [],
  lanDevices: null,
  browser: null,
  currentView: "overview",
  selectedActivityId: null,
  integrationTestResults: null,
};

const viewMeta = {
  overview: {
    title: "Overview",
    description: "Scan storage roots, review duplicates, and consolidate media safely.",
  },
  roots: {
    title: "Library Roots",
    description: "Manage scan roots and define canonical movie and series targets.",
  },
  integrations: {
    title: "Integrations",
    description: "Configure Radarr and Sonarr sync for canonical library paths.",
  },
  browser: {
    title: "LAN Browser",
    description: "Discover LAN devices, then browse mounted shares and add folders directly as scan roots.",
  },
  report: {
    title: "Duplicate Report",
    description: "Inspect exact duplicate groups and same-title media collisions.",
  },
  plan: {
    title: "Action Plan",
    description: "Build, preview, and apply move/delete actions with dry-run safety.",
  },
  activity: {
    title: "Activity Log",
    description: "Review recent configuration changes and process history.",
  },
};

function defaultPayload() {
  return {
    roots: [],
    targets: {},
    integrations: {
      radarr: { enabled: false, base_url: "", api_key: "", root_folder_path: "" },
      sonarr: { enabled: false, base_url: "", api_key: "", root_folder_path: "" },
      sync_options: {
        sync_after_apply: true,
        rescan_after_update: true,
        create_root_folder_if_missing: true,
      },
    },
    report: null,
    plan: null,
    apply_result: null,
    sync_result: null,
    activity_log: [],
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
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed");
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

function setView(view) {
  state.currentView = view;
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === view);
  });
  document.querySelectorAll(".view").forEach((node) => {
    node.classList.toggle("active", node.id === `${view}View`);
  });
  const meta = viewMeta[view] || viewMeta.overview;
  document.querySelector("#viewTitle").textContent = meta.title;
  document.querySelector("#viewDescription").textContent = meta.description;
}

function getPayload() {
  return state.payload || defaultPayload();
}

function getActivityLog() {
  return getPayload().activity_log || [];
}

function ensureSelectedActivity() {
  const log = getActivityLog();
  if (!log.length) {
    state.selectedActivityId = null;
    return;
  }
  if (!log.some((entry) => entry.id === state.selectedActivityId)) {
    state.selectedActivityId = log[0].id;
  }
}

function renderSystemSummary(payload) {
  const configuredTargets = [payload.targets.movie_root, payload.targets.series_root, payload.targets.review_root].filter(Boolean);
  document.querySelector("#targetHealthValue").textContent = configuredTargets.length
    ? `${configuredTargets.length} target${configuredTargets.length > 1 ? "s" : ""} ready`
    : "Not configured";
  document.querySelector("#targetHealthMeta").textContent = configuredTargets.length
    ? configuredTargets.join(" | ")
    : "Set movie and series roots to enable canonical moves.";

  const latestActivity = getActivityLog()[0];
  document.querySelector("#activityHeadline").textContent = latestActivity ? latestActivity.message : "No jobs yet";
  document.querySelector("#activityMeta").textContent = latestActivity
    ? `${latestActivity.kind} | ${formatDate(latestActivity.created_at)}`
    : "Run scan, plan, or apply to populate the log.";

  const planSummary = payload.plan?.summary || {};
  const totalActions = (planSummary.move || 0) + (planSummary.delete || 0) + (planSummary.review || 0);
  document.querySelector("#actionHealthValue").textContent = totalActions ? `${totalActions} actions queued` : "No plan";
  document.querySelector("#actionHealthMeta").textContent = totalActions
    ? `Move ${planSummary.move || 0} | Delete ${planSummary.delete || 0} | Review ${planSummary.review || 0}`
    : "Build a plan to preview move, delete, and review actions.";
}

function renderOverview(payload) {
  const reportSummary = payload.report?.summary || {};
  const planSummary = payload.plan?.summary || {};
  const applySummary = payload.apply_result?.summary || {};

  document.querySelector("#lastScanValue").textContent = formatDate(payload.last_scan_at);
  document.querySelector("#lastPlanValue").textContent = formatDate(payload.last_plan_at);
  document.querySelector("#lastApplyValue").textContent = formatDate(payload.last_apply_at);

  document.querySelector("#stats").innerHTML = `
    <div class="stat-card"><span>Files Indexed</span><strong>${reportSummary.files || 0}</strong></div>
    <div class="stat-card"><span>Exact Duplicate Groups</span><strong>${reportSummary.exact_duplicate_groups || 0}</strong></div>
    <div class="stat-card"><span>Media Collisions</span><strong>${reportSummary.media_collision_groups || 0}</strong></div>
    <div class="stat-card"><span>Move Actions</span><strong>${planSummary.move || 0}</strong></div>
    <div class="stat-card"><span>Delete Actions</span><strong>${planSummary.delete || 0}</strong></div>
    <div class="stat-card"><span>Last Apply Errors</span><strong>${applySummary.error || 0}</strong></div>
  `;

  document.querySelector("#rootCount").textContent = String(payload.roots.length);
  document.querySelector("#mountCount").textContent = String(state.mounts.length);

  document.querySelector("#overviewRoots").innerHTML = payload.roots.length
    ? payload.roots
        .map(
          (root) => `
          <div class="collection-item">
            <div>
              <strong>${escapeHtml(root.label)}</strong>
              <div class="muted">${escapeHtml(root.path)}</div>
            </div>
            <div class="item-meta">
              <span class="pill small">P${root.priority}</span>
              <span class="pill small">${escapeHtml(root.kind)}</span>
            </div>
          </div>`
        )
        .join("")
    : `<div class="empty-state">No roots configured yet.</div>`;

  document.querySelector("#mountsList").innerHTML = state.mounts.length
    ? state.mounts
        .map(
          (mount) => `
          <button class="collection-item action-card" data-open-browser="${escapeHtml(mount.mount_point)}">
            <div>
              <strong>${escapeHtml(mount.label)}</strong>
              <div class="muted">${escapeHtml(mount.mount_point)}</div>
            </div>
            <div class="item-meta">
              <span class="pill small">${escapeHtml(mount.filesystem)}</span>
              <span class="pill small ${mount.is_network ? "accent" : ""}">${mount.is_network ? "LAN" : "Local"}</span>
            </div>
          </button>`
        )
        .join("")
    : `<div class="empty-state">No mounted network shares detected.</div>`;

  const activity = getActivityLog().slice(0, 5);
  document.querySelector("#activityOverviewList").innerHTML = activity.length
    ? activity
        .map(
          (entry) => `
          <button class="collection-item action-card" data-activity-id="${escapeHtml(entry.id)}">
            <div>
              <strong>${escapeHtml(entry.message)}</strong>
              <div class="muted">${escapeHtml(entry.kind)} | ${formatDate(entry.created_at)}</div>
            </div>
            <div class="item-meta">
              <span class="pill small">${escapeHtml(entry.status)}</span>
            </div>
          </button>`
        )
        .join("")
    : `<div class="empty-state">No activity yet.</div>`;
}

function renderLanDevices() {
  const payload = state.lanDevices || { devices: [], summary: { devices: 0 } };
  document.querySelector("#lanDeviceCount").textContent = String(payload.summary?.devices || payload.devices.length || 0);
  document.querySelector("#lanDevicesList").innerHTML = payload.devices?.length
    ? payload.devices
        .map((device) => {
          const hostLine = [device.hostname, device.ip_address].filter(Boolean).join(" • ") || device.device_key;
          const services = device.services || [];
          const urls = device.connect_urls || [];
          return `
            <div class="collection-item vertical">
              <div class="row split">
                <strong>${escapeHtml(device.display_name || device.hostname || device.ip_address || device.device_key)}</strong>
                <span class="pill small">${services.length ? `${services.length} service${services.length > 1 ? "s" : ""}` : "Host only"}</span>
              </div>
              <div class="muted">${escapeHtml(hostLine)}</div>
              ${
                services.length
                  ? `<div class="service-tags">
                      ${services
                        .map(
                          (service) =>
                            `<span class="pill small ${service.service_type === "_smb._tcp" ? "accent" : ""}">${escapeHtml(
                              service.service_label
                            )} • ${escapeHtml(service.instance)} • ${escapeHtml(String(service.port))}</span>`
                        )
                        .join("")}
                    </div>`
                  : ""
              }
              ${
                urls.length
                  ? `<div class="external-links">
                      ${urls
                        .map(
                          (url) =>
                            `<a class="external-link" href="${escapeHtml(url)}">${escapeHtml(url)}</a>`
                        )
                        .join("")}
                    </div>`
                  : ""
              }
            </div>`;
        })
        .join("")
    : `<div class="empty-state">No LAN devices discovered yet. Click Refresh LAN. Bonjour-visible hosts will appear here, while mounted shares still show below in the filesystem browser.</div>`;
}

function renderRoots(payload) {
  const targetsForm = document.querySelector("#targetsForm");
  targetsForm.movie_root.value = payload.targets.movie_root || "";
  targetsForm.series_root.value = payload.targets.series_root || "";
  targetsForm.review_root.value = payload.targets.review_root || "";

  document.querySelector("#rootsList").innerHTML = payload.roots.length
    ? payload.roots
        .map(
          (root) => `
          <div class="collection-item">
            <div>
              <strong>${escapeHtml(root.label)}</strong>
              <div class="muted">${escapeHtml(root.path)}</div>
            </div>
            <div class="item-meta">
              <span class="pill small">P${root.priority}</span>
              <span class="pill small">${escapeHtml(root.kind)}</span>
              <button class="btn btn-small" data-remove="${escapeHtml(root.path)}">Remove</button>
            </div>
          </div>`
        )
        .join("")
    : `<div class="empty-state">No scan roots yet. Add one manually or use the browser.</div>`;
}

function setProviderForm(form, provider) {
  form.querySelector('[name="enabled"]').checked = Boolean(provider.enabled);
  form.querySelector('[name="base_url"]').value = provider.base_url || "";
  form.querySelector('[name="api_key"]').value = provider.api_key || "";
  form.querySelector('[name="root_folder_path"]').value = provider.root_folder_path || "";
}

function renderIntegrations(payload) {
  const integrations = payload.integrations || defaultPayload().integrations;
  setProviderForm(document.querySelector("#radarrForm"), integrations.radarr || {});
  setProviderForm(document.querySelector("#sonarrForm"), integrations.sonarr || {});

  const optionsForm = document.querySelector("#integrationOptionsForm");
  optionsForm.querySelector('[name="sync_after_apply"]').checked = Boolean(integrations.sync_options?.sync_after_apply);
  optionsForm.querySelector('[name="rescan_after_update"]').checked = Boolean(integrations.sync_options?.rescan_after_update);
  optionsForm.querySelector('[name="create_root_folder_if_missing"]').checked = Boolean(
    integrations.sync_options?.create_root_folder_if_missing
  );

  const results = state.integrationTestResults;
  document.querySelector("#integrationTestResults").innerHTML = results
    ? Object.entries(results)
        .map(
          ([name, result]) => `
          <div class="collection-item">
            <div>
              <strong>${escapeHtml(name)}</strong>
              <div class="muted">${escapeHtml(result.status || "unknown")}</div>
            </div>
            <div class="item-meta">
              <span class="pill small">${escapeHtml(result.error || result.api_root || "ready")}</span>
            </div>
          </div>`
        )
        .join("")
    : `<div class="empty-state">No connectivity test has been run yet.</div>`;

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
    : `<div class="empty-state">No path sync has been run yet.</div>`;
}

function renderBrowser() {
  const browser = state.browser;
  if (!browser) return;

  document.querySelector("#browserMountLabel").textContent = browser.mount
    ? `${browser.mount.label} | ${browser.mount.filesystem} | ${browser.mount.source}`
    : "Browse folders accessible to this machine.";
  document.querySelector("#browserPathInput").value = browser.path;

  document.querySelector("#browserFavorites").innerHTML = (browser.favorites || [])
    .map(
      (mount) => `
      <button class="collection-item action-card" data-browse="${escapeHtml(mount.mount_point)}">
        <div>
          <strong>${escapeHtml(mount.label)}</strong>
          <div class="muted">${escapeHtml(mount.mount_point)}</div>
        </div>
        <div class="item-meta">
          <span class="pill small">${escapeHtml(mount.filesystem)}</span>
          <span class="pill small ${mount.is_network ? "accent" : ""}">${mount.is_network ? "LAN" : "Local"}</span>
        </div>
      </button>`
    )
    .join("");

  document.querySelector("#breadcrumbs").innerHTML = (browser.breadcrumbs || [])
    .map((crumb) => `<button class="crumb" data-browse="${escapeHtml(crumb.path)}">${escapeHtml(crumb.name)}</button>`)
    .join("");

  document.querySelector("#browserEntries").innerHTML = browser.entries.length
    ? browser.entries
        .map(
          (entry) => `
          <div class="table-row">
            <button class="table-main ${entry.type === "directory" ? "clickable" : ""}" ${
              entry.type === "directory" ? `data-browse="${escapeHtml(entry.path)}"` : ""
            }>
              <span class="entry-icon">${entry.type === "directory" ? "DIR" : "VID"}</span>
              <span>
                <strong>${escapeHtml(entry.name)}</strong>
                <span class="muted block">${escapeHtml(entry.path)}</span>
              </span>
            </button>
            <div class="table-meta">
              <span>${escapeHtml(entry.type)}</span>
              <span>${formatBytes(entry.size)}</span>
              <button class="btn btn-small" data-fill-root="${escapeHtml(entry.path)}">Use</button>
            </div>
          </div>`
        )
        .join("")
    : `<div class="empty-state">Folder is empty.</div>`;
}

function renderReport(payload) {
  const exactGroups = payload.report?.exact_duplicates || [];
  const collisionGroups = payload.report?.media_collisions || [];

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
            ${group.items.map((item) => `<div class="sub-row">${escapeHtml(item.path)}</div>`).join("")}
          </div>`
        )
        .join("")
    : `<div class="empty-state">No exact duplicates found yet.</div>`;

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
    : `<div class="empty-state">No same-title collisions found yet.</div>`;
}

function renderPlan(payload) {
  const actions = payload.plan?.actions || [];
  const applyResult = payload.apply_result;
  const syncResult = payload.sync_result;

  document.querySelector("#planActionCount").textContent = String(actions.length);
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
            <div class="sub-row"><span>${escapeHtml(action.source)}</span></div>
            ${action.destination ? `<div class="sub-row"><span>${escapeHtml(action.destination)}</span></div>` : ""}
            ${action.keep_path ? `<div class="muted">Keep: ${escapeHtml(action.keep_path)}</div>` : ""}
          </div>`
        )
        .join("")
    : `<div class="empty-state">No plan built yet.</div>`;

  document.querySelector("#applySummary").innerHTML = applyResult
    ? `
      <div class="collection-item vertical">
        <div class="row split">
          <strong>${escapeHtml(applyResult.mode || "dry-run")}</strong>
          <span class="pill small">${formatDate(payload.last_apply_at)}</span>
        </div>
        <div class="sub-row"><span>Applied ${applyResult.summary?.applied || 0}</span><span>Dry ${applyResult.summary?.["dry-run"] || 0}</span></div>
        <div class="sub-row"><span>Skipped ${applyResult.summary?.skipped || 0}</span><span>Errors ${applyResult.summary?.error || 0}</span></div>
        ${
          applyResult.integration_sync
            ? `<div class="muted">Integration sync: ${escapeHtml(applyResult.integration_sync.status || "unknown")}</div>`
            : ""
        }
        ${syncResult ? `<div class="muted">Last manual sync: ${escapeHtml(syncResult.status || "unknown")} • ${formatDate(payload.last_sync_at)}</div>` : ""}
      </div>`
    : `<div class="empty-state">No apply result yet.</div>`;
}

function renderActivity() {
  const log = getActivityLog();
  ensureSelectedActivity();

  document.querySelector("#activityCount").textContent = String(log.length);
  document.querySelector("#activityList").innerHTML = log.length
    ? log
        .map(
          (entry) => `
          <button class="collection-item action-card ${entry.id === state.selectedActivityId ? "active" : ""}" data-activity-id="${escapeHtml(
            entry.id
          )}">
            <div>
              <strong>${escapeHtml(entry.message)}</strong>
              <div class="muted">${escapeHtml(entry.kind)} | ${formatDate(entry.created_at)}</div>
            </div>
            <div class="item-meta">
              <span class="pill small">${escapeHtml(entry.status)}</span>
            </div>
          </button>`
        )
        .join("")
    : `<div class="empty-state">No activity yet.</div>`;

  const selected = log.find((entry) => entry.id === state.selectedActivityId);
  if (!selected) {
    document.querySelector("#activityDetail").textContent = "Select an event from the timeline to inspect the process details.";
    return;
  }

  const detailItems = Object.entries(selected.details || {})
    .map(([key, value]) => {
      if (value && typeof value === "object") {
        return `
          <div class="collection-item vertical">
            <strong>${escapeHtml(key)}</strong>
            <pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre>
          </div>`;
      }
      return `
        <div class="collection-item">
          <strong>${escapeHtml(key)}</strong>
          <span class="muted">${escapeHtml(String(value))}</span>
        </div>`;
    })
    .join("");

  document.querySelector("#activityDetail").innerHTML = `
    <div class="collection-item vertical">
      <div class="row split">
        <strong>${escapeHtml(selected.message)}</strong>
        <span class="pill small">${escapeHtml(selected.status)}</span>
      </div>
      <div class="muted">${escapeHtml(selected.kind)} | ${formatDate(selected.created_at)}</div>
    </div>
    ${detailItems || `<div class="empty-state">No extra detail stored for this event.</div>`}
  `;
}

function render() {
  const payload = getPayload();
  renderSystemSummary(payload);
  renderOverview(payload);
  renderRoots(payload);
  renderIntegrations(payload);
  renderLanDevices();
  renderBrowser();
  renderReport(payload);
  renderPlan(payload);
  renderActivity();
}

async function refreshAll() {
  const [payload, mountsPayload, lanPayload] = await Promise.all([
    request("/api/state"),
    request("/api/system/mounts"),
    request("/api/lan/discover"),
  ]);
  state.payload = payload;
  state.mounts = mountsPayload.mounts || [];
  state.lanDevices = lanPayload;
  if (!state.browser) {
    state.browser = await request("/api/browse");
  }
  ensureSelectedActivity();
  render();
}

async function browse(path) {
  state.browser = await request(`/api/browse${path ? `?path=${encodeURIComponent(path)}` : ""}`);
  renderBrowser();
}

async function runAction(label, action, successMessage) {
  setServerStatus(label);
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
      // Keep the original request error if refresh also fails.
    }
    setServerStatus("Action failed");
    showMessage(error.message, true);
    return null;
  }
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

document.querySelectorAll(".nav-item").forEach((item) => {
  item.addEventListener("click", () => setView(item.dataset.view));
});

document.querySelector("#rootForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const result = await runAction(
    "Saving root...",
    () =>
      request("/api/roots", {
        method: "POST",
        body: JSON.stringify(Object.fromEntries(form.entries())),
      }),
    "Root added."
  );
  if (!result) return;
  event.currentTarget.reset();
  event.currentTarget.querySelector('[name="priority"]').value = 50;
});

document.querySelector("#targetsForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  await runAction(
    "Saving targets...",
    () =>
      request("/api/targets", {
        method: "POST",
        body: JSON.stringify(Object.fromEntries(form.entries())),
      }),
    "Targets saved."
  );
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
  renderIntegrations(getPayload());
});

document.querySelector("#runSyncButton").addEventListener("click", async () => {
  const result = await runAction(
    "Syncing Radarr/Sonarr...",
    () =>
      request("/api/sync", {
        method: "POST",
        body: "{}",
      }),
    "Manual sync finished."
  );
  if (!result) return;
});

document.body.addEventListener("click", async (event) => {
  const navJump = event.target.closest("[data-view-jump]");
  if (navJump) {
    setView(navJump.dataset.viewJump);
    return;
  }

  const activityButton = event.target.closest("[data-activity-id]");
  if (activityButton) {
    state.selectedActivityId = activityButton.dataset.activityId;
    renderActivity();
    setView("activity");
    return;
  }

  const browseButton = event.target.closest("[data-browse]");
  if (browseButton) {
    try {
      await browse(browseButton.dataset.browse);
      setView("browser");
    } catch (error) {
      showMessage(error.message, true);
    }
    return;
  }

  const openBrowser = event.target.closest("[data-open-browser]");
  if (openBrowser) {
    try {
      await browse(openBrowser.dataset.openBrowser);
      setView("browser");
    } catch (error) {
      showMessage(error.message, true);
    }
    return;
  }

  const removeButton = event.target.closest("[data-remove]");
  if (removeButton) {
    await runAction(
      "Removing root...",
      () =>
        request(`/api/roots?path=${encodeURIComponent(removeButton.dataset.remove)}`, {
          method: "DELETE",
        }),
      "Root removed."
    );
    return;
  }

  const fillButton = event.target.closest("[data-fill-root]");
  if (fillButton) {
    document.querySelector("#rootPathInput").value = fillButton.dataset.fillRoot;
    setView("roots");
    showMessage("Path copied to root form.");
  }
});

document.querySelector("#browseGoButton").addEventListener("click", async () => {
  try {
    await browse(document.querySelector("#browserPathInput").value.trim());
  } catch (error) {
    showMessage(error.message, true);
  }
});

document.querySelector("#refreshLanDevicesButton").addEventListener("click", async () => {
  const result = await runAction("Discovering LAN devices...", () => request("/api/lan/discover"), "LAN discovery finished.");
  if (!result) return;
  state.lanDevices = result;
  renderLanDevices();
});

document.querySelector("#browserPathInput").addEventListener("keydown", async (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  try {
    await browse(document.querySelector("#browserPathInput").value.trim());
  } catch (error) {
    showMessage(error.message, true);
  }
});

document.querySelector("#browseUpButton").addEventListener("click", async () => {
  if (!state.browser?.parent) return;
  try {
    await browse(state.browser.parent);
  } catch (error) {
    showMessage(error.message, true);
  }
});

document.querySelector("#addCurrentFolderButton").addEventListener("click", () => {
  if (!state.browser?.path) return;
  document.querySelector("#rootPathInput").value = state.browser.path;
  setView("roots");
  showMessage("Current folder copied to root form.");
});

document.querySelector("#scanButton").addEventListener("click", async () => {
  const result = await runAction(
    "Running scan...",
    () => request("/api/scan", { method: "POST", body: "{}" }),
    "Scan finished."
  );
  if (result) setView("report");
});

async function buildPlan() {
  return runAction(
    "Building plan...",
    () =>
      request("/api/plan", {
        method: "POST",
        body: JSON.stringify({
          delete_lower_quality: document.querySelector("#deleteLowerQuality").checked,
        }),
      }),
    "Plan created."
  );
}

document.querySelector("#planButton").addEventListener("click", async () => {
  const result = await buildPlan();
  if (result) setView("plan");
});

document.querySelector("#buildPlanButton").addEventListener("click", async () => {
  const result = await buildPlan();
  if (result) setView("plan");
});

async function applyPlan(execute) {
  return runAction(
    execute ? "Executing plan..." : "Running dry-run...",
    () =>
      request("/api/apply", {
        method: "POST",
        body: JSON.stringify({
          execute,
          prune_empty_dirs: document.querySelector("#pruneEmptyDirs").checked,
        }),
      }),
    execute ? "Plan executed." : "Dry run completed."
  );
}

document.querySelector("#dryRunButton").addEventListener("click", async () => {
  const result = await applyPlan(false);
  if (result) setView("plan");
});

document.querySelector("#executePlanButton").addEventListener("click", async () => {
  if (!window.confirm("Execute the current plan on real files?")) return;
  const result = await applyPlan(true);
  if (result) setView("plan");
});

refreshAll().catch((error) => showMessage(error.message, true));
