const JSON_HEADERS = { "Content-Type": "application/json" };

export async function request(url, options = {}) {
  const { timeoutMs, ...fetchOptions } = options;
  const controller = new AbortController();
  const timeoutId =
    typeof timeoutMs === "number" && timeoutMs > 0
      ? window.setTimeout(() => controller.abort(new Error(`Request timed out after ${timeoutMs}ms`)), timeoutMs)
      : null;

  try {
    const response = await fetch(url, {
      headers: JSON_HEADERS,
      signal: controller.signal,
      ...fetchOptions
    });
    const text = await response.text();
    const contentType = response.headers.get("content-type") || "";
    const data = text ? (contentType.includes("application/json") ? JSON.parse(text) : text) : {};

    if (!response.ok) {
      if (response.status === 502) {
        throw new Error("Backend is not available (HTTP 502 Bad Gateway). Please ensure the backend server is running.");
      }
      if (response.status === 504) {
        throw new Error("Backend request timed out (HTTP 504 Gateway Timeout).");
      }
      throw new Error(data?.error || `Request failed with status ${response.status}: ${response.statusText}`);
    }

    return data;
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error(`Request timed out after ${timeoutMs}ms`);
    }
    if (error instanceof TypeError && String(error.message || "").includes("Failed to fetch")) {
      throw new Error("Could not reach the dashboard backend. Open the app from the active backend URL and refresh the page.");
    }
    throw error;
  } finally {
    if (timeoutId) {
      window.clearTimeout(timeoutId);
    }
  }
}

export async function fetchOperationsData() {
  const [state, process] = await Promise.all([
    request("/api/state"),
    request("/api/process")
  ]);

  return {
    state,
    process: process.current_job || null,
    mounts: [],
    operationsFolders: [],
    operationsSummary: { items: 0, roots: state?.roots?.length || 0 }
  };
}

export function fetchCurrentProcess() {
  return request("/api/process");
}

export function cancelCurrentProcess() {
  return request("/api/process/cancel", {
    method: "POST",
    body: "{}"
  });
}

export function waitCurrentProcess(waitSeconds = 300) {
  return request("/api/process/wait", {
    method: "POST",
    body: JSON.stringify({ wait_seconds: waitSeconds })
  });
}

export function retryCurrentProcess() {
  return request("/api/process/retry", {
    method: "POST",
    body: "{}"
  });
}

export function resumeCurrentProcess() {
  return request("/api/process/resume", {
    method: "POST",
    body: "{}"
  });
}

export function fetchOperationsFolderChildren({ storageUri, rootStorageUri, timeoutMs }) {
  const effectiveTimeoutMs =
    typeof timeoutMs === "number" && timeoutMs > 0
      ? timeoutMs
      : String(storageUri || rootStorageUri || "").startsWith("rclone://")
        ? 60000
        : 15000;
  const params = new URLSearchParams({
    storage_uri: storageUri,
    root_storage_uri: rootStorageUri,
  });
  return request(`/api/operations/folders/children?${params.toString()}`, { timeoutMs: effectiveTimeoutMs });
}

export function refreshOperationsFolderIndex(maxDepth = 6) {
  return request("/api/operations/folder-index/refresh", {
    method: "POST",
    body: JSON.stringify({ max_depth: maxDepth }),
    timeoutMs: 300000,
  });
}

export function fetchProviderItems(provider) {
  return request(`/api/integrations/${provider}/items`);
}

export function fetchSettingsState() {
  return request("/api/state");
}

export function browseLocalPath(path) {
  const params = new URLSearchParams();
  if (path) params.set("path", path);
  return request(`/api/browse${params.toString() ? `?${params.toString()}` : ""}`);
}

export function browseSmbPath({ connectionId, shareName, path, scope }) {
  const params = new URLSearchParams({ connection_id: connectionId });
  if (shareName) params.set("share_name", shareName);
  if (path && path !== "/") params.set("path", path);
  if (scope) params.set("scope", scope);
  return request(`/api/smb/browse?${params.toString()}`);
}

export function discoverLanDevices() {
  return request("/api/lan/discover");
}

export function addRoot(payload) {
  return request("/api/roots", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateRoot(payload) {
  return request("/api/roots", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function saveLanConnection(payload) {
  return request("/api/lan/connections", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function testLanConnection(payload) {
  return request("/api/lan/connections/test", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function deleteLanConnection(id) {
  return request(`/api/lan/connections?id=${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function saveRcloneConnection(payload) {
  return request("/api/rclone/connections", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function syncRcloneConfig() {
  return request("/api/rclone/sync", {
    method: "POST",
    body: "{}"
  });
}

export function fetchRcloneRemotes() {
  return request("/api/rclone/remotes");
}

export function mountRclone(payload) {
  return request("/api/rclone/mount", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function unmountRclone(payload) {
  return request("/api/rclone/unmount", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function saveIntegrations(payload) {
  return request("/api/integrations", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function testIntegrations(payload) {
  return request("/api/integrations/test", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function runManualSync() {
  return request("/api/sync", {
    method: "POST",
    body: "{}"
  });
}

export function previewMoveToProvider(payload) {
  return request("/api/folders/move-to-provider", {
    method: "POST",
    body: JSON.stringify({ ...payload, execute: false })
  });
}

export function executeMoveToProvider(payload) {
  return request("/api/folders/move-to-provider", {
    method: "POST",
    body: JSON.stringify({ ...payload, execute: true })
  });
}

export function runScan(selectedFolders) {
  return request("/api/scan", {
    method: "POST",
    body: JSON.stringify({ folders: selectedFolders || [] })
  });
}

export function buildPlan(deleteLowerQuality) {
  return request("/api/plan", {
    method: "POST",
    body: JSON.stringify({ delete_lower_quality: deleteLowerQuality })
  });
}

export function applyPlan({ execute, pruneEmptyDirs }) {
  return request("/api/apply", {
    method: "POST",
    body: JSON.stringify({ execute, prune_empty_dirs: pruneEmptyDirs })
  });
}

export function removeRoot(path) {
  return request(`/api/roots?path=${encodeURIComponent(path)}`, { method: "DELETE" });
}

export function deleteFolder(path) {
  return request(`/api/folders?path=${encodeURIComponent(path)}&execute=true`, { method: "DELETE" });
}

export function runProviderCleanupScan(providers) {
  return request("/api/cleanup/scan", {
    method: "POST",
    body: JSON.stringify({ providers: providers || [] })
  });
}

export const runCleanupScan = runProviderCleanupScan;

export function runEmptyFolderCleanupScan() {
  return request("/api/cleanup/empty-folders/scan", {
    method: "POST",
    body: "{}"
  });
}

export function runOperationsFolderCleanupScan(folders) {
  return request("/api/operations/folder-cleanup/scan", {
    method: "POST",
    body: JSON.stringify({ folders: folders || [] })
  });
}

export function runOperationsFolderCleanupDelete(folders) {
  return request("/api/operations/folder-cleanup/delete", {
    method: "POST",
    body: JSON.stringify({ folders: folders || [] })
  });
}

export function runPathRepairScan() {
  return request("/api/path-repair/scan", {
    method: "POST",
    body: "{}",
  });
}

export function updateProviderPath({ provider, itemId, path }) {
  return request("/api/path-repair/update", {
    method: "POST",
    body: JSON.stringify({ provider, item_id: itemId, path }),
  });
}

export function deletePathRepairProviderItem({ provider, itemId, addImportExclusion = false }) {
  return request("/api/path-repair/delete", {
    method: "POST",
    body: JSON.stringify({ provider, item_id: itemId, add_import_exclusion: addImportExclusion }),
  });
}

export function searchPathRepairFolders({ provider, query, currentPath = "", year = null }) {
  return request("/api/path-repair/search", {
    method: "POST",
    body: JSON.stringify({ provider, query, current_path: currentPath, year }),
  });
}

export function deleteMovieFile({ path, storageUri, rootPath, rootStorageUri, pruneEmptyDirs = true }) {
  const params = new URLSearchParams({
    execute: "true",
    prune_empty_dirs: pruneEmptyDirs ? "true" : "false",
  });
  if (path) params.set("path", path);
  if (storageUri) params.set("storage_uri", storageUri);
  if (rootPath) params.set("root_path", rootPath);
  if (rootStorageUri) params.set("root_storage_uri", rootStorageUri);
  return request(`/api/files?${params.toString()}`, { method: "DELETE" });
}

export function deleteCleanupFiles(items) {
  return request("/api/cleanup/files/delete", {
    method: "POST",
    body: JSON.stringify({ items: items || [] }),
  });
}

export function deleteMediaFile({ path, storageUri }) {
  const params = new URLSearchParams({ execute: "true" });
  if (path) params.set("path", path);
  if (storageUri) params.set("storage_uri", storageUri);
  return request(`/api/files?${params.toString()}`, { method: "DELETE" });
}
