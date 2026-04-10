import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Empty,
  Flex,
  Input,
  Modal,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { DeleteOutlined, LinkOutlined, SearchOutlined, StopOutlined } from "@ant-design/icons";
import {
  deletePathRepairProviderItem,
  fetchCurrentProcess,
  request,
  runPathRepairScan,
  searchPathRepairFolders,
  updateProviderPath,
} from "../api";
import { MediaLibraryLogPanel } from "./MediaLibraryLogPanel";

const { Text } = Typography;

const emptySearchState = {
  open: false,
  issue: null,
  query: "",
  loading: false,
  items: [],
};

const PATH_REPAIR_REPORT_STORAGE_KEY = "media-library-manager.path-repair-report";

function stripPriorityLabel(value) {
  return String(value || "").replace(/\s+P\d+$/, "").trim();
}

function formatSearchLogTime(value) {
  if (!value) return "--:--:--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--:--:--";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

function buildSearchLogDetailSummary(details) {
  return Object.entries(details || {})
    .map(([key, value]) => {
      if (value === null || value === undefined || value === "") return null;
      return `${String(key).replaceAll("_", " ")}: ${Array.isArray(value) ? value.join(", ") : String(value)}`;
    })
    .filter(Boolean)
    .join(" | ");
}

function isSearchProcessJob(job) {
  return String(job?.kind || "").toLowerCase() === "path-repair" && String(job?.details?.action || "") === "search-path-repair";
}

function renderAnimatedStatusLabel(job) {
  const status = String(job?.status || "").toLowerCase();
  if (status === "running") {
    return (
      <span className="path-repair-running-status">
        <span className="path-repair-running-dot" aria-hidden="true" />
        <span className="path-repair-running-text">Scanning</span>
        <span className="path-repair-running-ellipsis" aria-hidden="true">
          <span>.</span>
          <span>.</span>
          <span>.</span>
        </span>
      </span>
    );
  }
  if (!status) return "Starting";
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function loadStoredPathRepairReport() {
  if (typeof window === "undefined") return { summary: {}, issues: [], errors: [] };
  try {
    const raw = window.localStorage.getItem(PATH_REPAIR_REPORT_STORAGE_KEY);
    return raw ? JSON.parse(raw) : { summary: {}, issues: [], errors: [] };
  } catch {
    return { summary: {}, issues: [], errors: [] };
  }
}

function persistPathRepairReport(report) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(PATH_REPAIR_REPORT_STORAGE_KEY, JSON.stringify(report || { summary: {}, issues: [], errors: [] }));
}

function pruneIssueFromReport(report, provider, itemId) {
  const issues = (report?.issues || []).filter(
    (issue) => !(String(issue?.provider || "").toLowerCase() === String(provider || "").toLowerCase() && Number(issue?.item_id || 0) === Number(itemId || 0))
  );
  return {
    ...(report || { summary: {}, issues: [], errors: [] }),
    issues,
    summary: {
      ...(report?.summary || {}),
      issues: issues.length,
      errors: Number(report?.summary?.errors || report?.errors?.length || 0),
    },
    generated_at: new Date().toISOString(),
  };
}

function formatIssueReason(reason) {
  const value = String(reason || "").trim().toLowerCase();
  if (value === "path_replacement_available") return "replacement found";
  if (value === "path_not_found") return "path not found";
  if (value === "path_not_directory") return "not a directory";
  if (value === "missing_path") return "missing path";
  if (value === "item_missing") return "missing in provider";
  return value || "unknown";
}

export function PathRepairView() {
  const { message, modal } = AntApp.useApp();
  const [loading, setLoading] = useState(true);
  const [updatingKey, setUpdatingKey] = useState("");
  const [query, setQuery] = useState("");
  const [payload, setPayload] = useState(() => loadStoredPathRepairReport());
  const [selectedIssueIds, setSelectedIssueIds] = useState([]);
  const [searchState, setSearchState] = useState(emptySearchState);
  const [searchProcessJob, setSearchProcessJob] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    request("/api/state")
      .then((data) => {
        if (!cancelled) {
          const nextPayload = data?.path_repair_report || loadStoredPathRepairReport();
          setPayload(nextPayload);
          persistPathRepairReport(nextPayload);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          message.error(error.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [message]);

  const issues = payload.issues || [];
  const filteredIssues = useMemo(() => {
    const search = String(query || "").trim().toLowerCase();
    const next = issues.filter((issue) =>
      [issue.title, issue.path, issue.provider, issue.reason]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(search))
    );
    return search ? next : issues;
  }, [issues, query]);

  useEffect(() => {
    const validIssueIds = new Set(filteredIssues.map((issue) => String(issue.id)));
    setSelectedIssueIds((current) => current.filter((id) => validIssueIds.has(String(id))));
  }, [filteredIssues]);

  useEffect(() => {
    if (!searchState.open || !searchState.loading) return undefined;
    let cancelled = false;

    const loadProcess = async () => {
      try {
        const process = await fetchCurrentProcess();
        if (cancelled) return;
        setSearchProcessJob(isSearchProcessJob(process.current_job) ? process.current_job : null);
      } catch {
        if (!cancelled) setSearchProcessJob(null);
      }
    };

    void loadProcess();
    const intervalId = window.setInterval(loadProcess, 700);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [searchState.loading, searchState.open]);

  const selectedIssues = useMemo(
    () => filteredIssues.filter((issue) => selectedIssueIds.includes(String(issue.id))),
    [filteredIssues, selectedIssueIds]
  );
  async function handleRemoveIssues(issuesToRemove) {
    if (!issuesToRemove.length) return;
    setUpdatingKey("__bulk-remove__");
    try {
      for (const issue of issuesToRemove) {
        await deletePathRepairProviderItem({
          provider: issue.provider,
          itemId: issue.item_id,
        });
      }
      await refreshState();
      message.success(
        issuesToRemove.length === 1 ? "Provider item removed." : `${issuesToRemove.length} provider items removed.`
      );
    } catch (error) {
      message.error(error.message);
    } finally {
      setUpdatingKey("");
    }
  }

  async function handleRemoveAndBlockIssues(issuesToRemove) {
    if (!issuesToRemove.length) return;
    setUpdatingKey("__bulk-block__");
    try {
      for (const issue of issuesToRemove) {
        await deletePathRepairProviderItem({
          provider: issue.provider,
          itemId: issue.item_id,
          addImportExclusion: true,
        });
      }
      await refreshState();
      message.success(
        issuesToRemove.length === 1
          ? "Provider item removed and blocked."
          : `${issuesToRemove.length} provider items removed and blocked.`
      );
    } catch (error) {
      message.error(error.message);
    } finally {
      setUpdatingKey("");
    }
  }

  function toggleIssueSelection(issueId) {
    const key = String(issueId);
    setSelectedIssueIds((current) => (current.includes(key) ? current.filter((item) => item !== key) : [...current, key]));
  }

  async function refreshState() {
    const state = await request("/api/state");
    const nextPayload = state?.path_repair_report || loadStoredPathRepairReport();
    setPayload(nextPayload);
    persistPathRepairReport(nextPayload);
  }

  async function handleScan() {
    setLoading(true);
    try {
      const result = await runPathRepairScan();
      const nextPayload = result || { summary: {}, issues: [], errors: [] };
      setPayload(nextPayload);
      persistPathRepairReport(nextPayload);
      message.success("Library path repair scan completed.");
    } catch (error) {
      message.error(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleApplyPath(issue, path, successMessage = "Provider path updated.") {
    const actionKey = `${issue.id}:${path}`;
    setUpdatingKey(actionKey);
    try {
      await updateProviderPath({
        provider: issue.provider,
        itemId: issue.item_id,
        path,
      });
      const state = await request("/api/state");
      const nextPayload = state?.path_repair_report || pruneIssueFromReport(payload, issue.provider, issue.item_id);
      setPayload(nextPayload);
      persistPathRepairReport(nextPayload);
      message.success(successMessage);
    } catch (error) {
      message.error(error.message);
    } finally {
      setUpdatingKey("");
    }
  }

  async function openManualSearch(issue) {
    const initialQuery = String(issue.title || "").trim();
    setSearchState({
      open: true,
      issue,
      query: initialQuery,
      loading: true,
      items: [],
    });
    setSearchProcessJob(null);
    try {
      const result = await searchPathRepairFolders({
        provider: issue.provider,
        query: initialQuery,
        currentPath: issue.path || "",
        year: issue.year || null,
      });
      const process = await fetchCurrentProcess();
      setSearchState((current) => ({
        ...current,
        loading: false,
        items: result.items || [],
      }));
      setSearchProcessJob(isSearchProcessJob(process.current_job) ? process.current_job : null);
    } catch (error) {
      setSearchState((current) => ({ ...current, loading: false }));
      setSearchProcessJob(null);
      message.error(error.message);
    }
  }

  const issueColumns = [
    {
      title: "Item",
      key: "item",
      render: (_value, issue) => (
        <Flex vertical gap={4}>
          <Space wrap>
            <Text strong>{issue.title}</Text>
            <Tag>{issue.provider}</Tag>
            <Tag color="warning">{formatIssueReason(issue.reason)}</Tag>
          </Space>
          <Text type="secondary" className="cleanup-path-text">
            {issue.path || "No path from provider"}
          </Text>
        </Flex>
      ),
    },
    {
      title: "Action",
      key: "action",
      width: 220,
      render: (_value, issue) => {
        return (
          <Space wrap>
            <Tooltip title="Search folder">
              <Button
                type="primary"
                icon={<SearchOutlined />}
                aria-label={`Search folder for ${issue.title}`}
                onClick={() => openManualSearch(issue)}
              />
            </Tooltip>
            <Tooltip title="Remove item from provider">
              <Button
                danger
                icon={<DeleteOutlined />}
                aria-label={`Remove ${issue.title} from provider`}
                onClick={() =>
                  modal.confirm({
                    title: "Remove this item from provider?",
                    content: "This removes the item from Radarr or Sonarr only. Media files are not deleted.",
                    okText: "Remove",
                    okButtonProps: { danger: true },
                    onOk: async () => {
                      const actionKey = `${issue.id}:delete`;
                      setUpdatingKey(actionKey);
                      try {
                        await deletePathRepairProviderItem({
                          provider: issue.provider,
                          itemId: issue.item_id,
                        });
                        const nextPayload = pruneIssueFromReport(payload, issue.provider, issue.item_id);
                        setPayload(nextPayload);
                        persistPathRepairReport(nextPayload);
                        message.success("Provider item removed.");
                      } catch (error) {
                        message.error(error.message);
                      } finally {
                        setUpdatingKey("");
                      }
                    },
                  })
                }
                loading={updatingKey === `${issue.id}:delete`}
              />
            </Tooltip>
            <Tooltip title="Remove and block auto re-import">
              <Button
                danger
                type="primary"
                icon={<StopOutlined />}
                aria-label={`Remove and block ${issue.title} from provider`}
                onClick={() =>
                  modal.confirm({
                    title: "Remove and block this item?",
                    content: "This removes the item from Radarr or Sonarr and adds import exclusion so it is not automatically added again.",
                    okText: "Remove and Block",
                    okButtonProps: { danger: true },
                    onOk: async () => {
                      const actionKey = `${issue.id}:block`;
                      setUpdatingKey(actionKey);
                      try {
                        await deletePathRepairProviderItem({
                          provider: issue.provider,
                          itemId: issue.item_id,
                          addImportExclusion: true,
                        });
                        const nextPayload = pruneIssueFromReport(payload, issue.provider, issue.item_id);
                        setPayload(nextPayload);
                        persistPathRepairReport(nextPayload);
                        message.success("Provider item removed and blocked.");
                      } catch (error) {
                        message.error(error.message);
                      } finally {
                        setUpdatingKey("");
                      }
                    },
                  })
                }
                loading={updatingKey === `${issue.id}:block`}
              />
            </Tooltip>
          </Space>
        );
      },
    },
  ];

  return (
    <Flex vertical gap={16}>
      <Card
        title={
          <Space>
            <LinkOutlined />
            <span>Library Path Repair</span>
          </Space>
        }
      >
        <Flex vertical gap={16}>
          <div className="cleanup-toolbar">
            <Space wrap>
              <Button type="primary" loading={loading} onClick={handleScan}>
                Scan Broken Provider Paths
              </Button>
              <Button
                danger
                disabled={!selectedIssues.length}
                loading={updatingKey === "__bulk-remove__"}
                onClick={() =>
                  modal.confirm({
                    title: `Remove ${selectedIssues.length} selected item${selectedIssues.length === 1 ? "" : "s"} from provider?`,
                    content: "This removes the selected items from Radarr or Sonarr only. Media files are not deleted.",
                    okText: "Remove",
                    okButtonProps: { danger: true },
                    onOk: async () => {
                      await handleRemoveIssues(selectedIssues);
                    },
                  })
                }
              >
                Remove Selected Items
              </Button>
              <Button
                danger
                type="primary"
                disabled={!selectedIssues.length}
                loading={updatingKey === "__bulk-block__"}
                onClick={() =>
                  modal.confirm({
                    title: `Remove and block ${selectedIssues.length} selected item${selectedIssues.length === 1 ? "" : "s"}?`,
                    content: "This removes the selected items from Radarr or Sonarr and adds import exclusion so they are not automatically added again.",
                    okText: "Remove and Block",
                    okButtonProps: { danger: true },
                    onOk: async () => {
                      await handleRemoveAndBlockIssues(selectedIssues);
                    },
                  })
                }
              >
                Remove and Block
              </Button>
              <Button disabled={!selectedIssueIds.length} onClick={() => setSelectedIssueIds([])}>
                Clear Selection
              </Button>
            </Space>
            <Input.Search
              className="folder-list-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              allowClear
              placeholder="Filter by title, path, provider, or reason"
            />
          </div>

          {payload.generated_at ? <Text type="secondary">Latest scan: {new Date(payload.generated_at).toLocaleString()}</Text> : null}

          {payload.errors?.length ? (
            <Alert
              type="error"
              showIcon
              message="Provider scan errors"
              description={payload.errors.map((item) => `${item.provider}: ${item.message}`).join(" • ")}
            />
          ) : null}

          {loading ? (
            <div className="card-loading">
              <Spin size="large" />
            </div>
          ) : filteredIssues.length ? (
            <Table
              size="small"
              rowKey={(issue) => String(issue.id)}
              pagination={{ pageSize: 10 }}
              dataSource={filteredIssues}
              rowSelection={{
                selectedRowKeys: selectedIssueIds,
                onChange: (keys) => setSelectedIssueIds(keys.map(String)),
              }}
              columns={issueColumns}
              onRow={(issue) => ({
                onClick: (event) => {
                  if (event.target.closest("button")) return;
                  toggleIssueSelection(issue.id);
                },
              })}
            />
          ) : (
            <Empty description="No saved provider path issues. Run a scan to inspect the libraries." />
          )}
        </Flex>
      </Card>

      <MediaLibraryLogPanel scope="repair" title="Path Repair Action Logs" />

      <Modal
        open={searchState.open}
        title={searchState.issue ? `Search Folder: ${searchState.issue.title}` : "Search Folder"}
        footer={null}
        width={920}
        onCancel={() => {
          setSearchState(emptySearchState);
          setSearchProcessJob(null);
        }}
      >
        <Flex vertical gap={16}>
          <Input.Search
            value={searchState.query}
            placeholder="Search folder names from connected roots"
            allowClear
            enterButton="Search"
            onChange={(event) => setSearchState((current) => ({ ...current, query: event.target.value }))}
            onSearch={async (value) => {
              const issue = searchState.issue;
              if (!issue || !String(value || "").trim()) return;
              setSearchState((current) => ({ ...current, loading: true, query: value }));
              setSearchProcessJob(null);
              try {
                const result = await searchPathRepairFolders({
                  provider: issue.provider,
                  query: value,
                  currentPath: issue.path || "",
                  year: issue.year || null,
                });
                const process = await fetchCurrentProcess();
                setSearchState((current) => ({
                  ...current,
                  loading: false,
                  items: result.items || [],
                }));
                setSearchProcessJob(isSearchProcessJob(process.current_job) ? process.current_job : null);
              } catch (error) {
                setSearchState((current) => ({ ...current, loading: false }));
                setSearchProcessJob(null);
                message.error(error.message);
              }
            }}
          />

          {searchState.loading ? (
            <div className="path-repair-search-progress">
              <Space wrap>
                <Tag>{searchState.issue?.provider || "provider"}</Tag>
                <Tag color="processing">Query: {searchState.query || "..."}</Tag>
                {searchProcessJob?.summary?.indexed_folders ? (
                  <Tag>Indexed folders: {searchProcessJob.summary.indexed_folders}</Tag>
                ) : null}
                {searchProcessJob?.summary?.total ? (
                  <Tag>
                    Roots: {Number(searchProcessJob?.summary?.completed || 0)}/{Number(searchProcessJob?.summary?.total || 0)}
                  </Tag>
                ) : null}
              </Space>

              <div className="process-log-shell path-repair-search-log-shell">
                <div className="process-log-shell-head">
                  <div className="process-log-shell-lights" aria-hidden="true">
                    <span />
                    <span />
                    <span />
                  </div>
                  <div className="process-log-shell-title">
                    <Text className="process-log-shell-title-main">Folder Search Progress</Text>
                    <Text className="process-log-shell-title-sub">
                      {searchProcessJob?.message || "Waiting for backend search logs..."}
                    </Text>
                  </div>
                  <Text className="process-log-shell-state">{renderAnimatedStatusLabel(searchProcessJob)}</Text>
                </div>
                <div className="process-log-viewport path-repair-search-log-viewport">
                  <div className="process-log-lines">
                    {(searchProcessJob?.logs || []).length ? (
                      searchProcessJob.logs.map((entry) => {
                        const level = String(entry?.level || "info").toLowerCase();
                        const tone = level.includes("error") ? "tone-error" : level.includes("warning") ? "tone-warning" : "tone-info";
                        const detailSummary = buildSearchLogDetailSummary(entry?.details || {});
                        return (
                          <div key={`${entry?.ts}-${entry?.message}`} className={`process-log-line ${tone}`}>
                            <div className="process-log-line-meta">
                              <Text className="process-log-line-time">{formatSearchLogTime(entry?.ts)}</Text>
                              <Tag className={`process-log-line-level ${tone}`}>{entry?.level || "info"}</Tag>
                            </div>
                            <div className="process-log-line-body">
                              <Text className="process-log-line-message">{entry?.message}</Text>
                              {detailSummary ? <Text className="process-log-line-summary">{detailSummary}</Text> : null}
                            </div>
                          </div>
                        );
                      })
                    ) : (
                      <div className="card-loading path-repair-search-log-loading">
                        <Spin size="large" />
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : searchState.items.length ? (
            <Table
              size="small"
              rowKey={(item) => item.path}
              pagination={{ pageSize: 8 }}
              dataSource={searchState.items}
              columns={[
                {
                  title: "Folder",
                  key: "folder",
                  render: (_value, item) => (
                    <Flex vertical gap={4}>
                      <Space wrap>
                        <Text strong>{item.label}</Text>
                        <Tag>{item.root_label}</Tag>
                      </Space>
                      <Text type="secondary" className="cleanup-path-text">
                        {item.path}
                      </Text>
                    </Flex>
                  ),
                },
                {
                  title: "Action",
                  key: "action",
                  width: 140,
                  render: (_value, item) => (
                    <Tooltip title="Use this path">
                      <Button
                        type="primary"
                        icon={<LinkOutlined />}
                        aria-label={`Use path ${item.path}`}
                        loading={updatingKey === `${searchState.issue?.id}:${item.path}`}
                        onClick={async () => {
                          if (!searchState.issue) return;
                          await handleApplyPath(searchState.issue, item.path);
                          setSearchState(emptySearchState);
                        }}
                      />
                    </Tooltip>
                  ),
                },
              ]}
            />
          ) : (
            <Empty description="No matching folders found in connected roots." />
          )}
        </Flex>
      </Modal>
    </Flex>
  );
}

export default PathRepairView;
