const JSON_HEADERS = { "Content-Type": "application/json" };

export async function request(url, options = {}) {
  const response = await fetch(url, {
    headers: JSON_HEADERS,
    ...options
  });

  const text = await response.text();
  const contentType = response.headers.get("content-type") || "";
  const data = text ? (contentType.includes("application/json") ? JSON.parse(text) : text) : {};

  if (!response.ok) {
    throw new Error(data?.error || `Request failed with status ${response.status}`);
  }

  return data;
}

export async function fetchOperationsData() {
  const [state, process, mounts, folders, folderTree] = await Promise.all([
    request("/api/state"),
    request("/api/process"),
    request("/api/system/mounts"),
    request("/api/operations/folders"),
    request("/api/operations/folders/tree")
  ]);

  return {
    state,
    process: process.current_job || null,
    mounts: mounts.mounts || [],
    operationsFolders: folders.items || [],
    operationsSummary: folders.summary || { items: 0, roots: 0 },
    operationsFolderTree: folderTree.items || [],
    operationsTreeSummary: folderTree.summary || { roots: 0, nodes: 0, max_depth: 4 }
  };
}

export function fetchProviderItems(provider) {
  return request(`/api/integrations/${provider}/items`);
}

export function fetchSettingsState() {
  return request("/api/state");
}

export function discoverLanDevices() {
  return request("/api/lan/discover");
}

export function saveTargetPaths(payload) {
  return request("/api/targets", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function addRoot(payload) {
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

export function addManagedFolder(payload) {
  return request("/api/managed-folders", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function deleteManagedFolder(id) {
  return request(`/api/managed-folders?id=${encodeURIComponent(id)}`, { method: "DELETE" });
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

export function runScan() {
  return request("/api/scan", { method: "POST", body: "{}" });
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
