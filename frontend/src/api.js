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
      throw new Error(data?.error || `Request failed with status ${response.status}`);
    }

    return data;
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error(`Request timed out after ${timeoutMs}ms`);
    }
    throw error;
  } finally {
    if (timeoutId) {
      window.clearTimeout(timeoutId);
    }
  }
}

export async function fetchOperationsData() {
  const [state, process, mounts] = await Promise.all([
    request("/api/state"),
    request("/api/process"),
    request("/api/system/mounts")
  ]);

  return {
    state,
    process: process.current_job || null,
    mounts: mounts.mounts || [],
    operationsFolders: [],
    operationsSummary: { items: 0, roots: state?.roots?.length || 0 }
  };
}

export function fetchOperationsFolderChildren({ storageUri, rootStorageUri, timeoutMs = 8000 }) {
  const params = new URLSearchParams({
    storage_uri: storageUri,
    root_storage_uri: rootStorageUri,
  });
  return request(`/api/operations/folders/children?${params.toString()}`, { timeoutMs });
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
