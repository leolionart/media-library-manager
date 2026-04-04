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
import { DeleteOutlined, LinkOutlined, SearchOutlined } from "@ant-design/icons";
import { deletePathRepairProviderItem, request, runPathRepairScan, searchPathRepairFolders, updateProviderPath } from "../api";
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
      with_suggestions: issues.filter((issue) => issue?.suggestions?.length).length,
      errors: Number(report?.summary?.errors || report?.errors?.length || 0),
    },
    generated_at: new Date().toISOString(),
  };
}

export function PathRepairView() {
  const { message, modal } = AntApp.useApp();
  const [loading, setLoading] = useState(true);
  const [updatingKey, setUpdatingKey] = useState("");
  const [query, setQuery] = useState("");
  const [payload, setPayload] = useState(() => loadStoredPathRepairReport());
  const [selectedIssueIds, setSelectedIssueIds] = useState([]);
  const [searchState, setSearchState] = useState(emptySearchState);

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

  const selectedIssues = useMemo(
    () => filteredIssues.filter((issue) => selectedIssueIds.includes(String(issue.id))),
    [filteredIssues, selectedIssueIds]
  );
  const selectedBestMatchRows = useMemo(
    () =>
      selectedIssues
        .filter((issue) => issue.suggestions?.length)
        .map((issue) => ({
          provider: issue.provider,
          itemId: issue.item_id,
          path: issue.suggestions[0].path,
        })),
    [selectedIssues]
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

  async function handleApplyBestPathsForSelected() {
    if (!selectedBestMatchRows.length) return;
    setUpdatingKey("__bulk__");
    try {
      for (const row of selectedBestMatchRows) {
        await updateProviderPath({
          provider: row.provider,
          itemId: row.itemId,
          path: row.path,
        });
      }
      await refreshState();
      message.success("Selected provider paths updated.");
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
    try {
      const result = await searchPathRepairFolders({ provider: issue.provider, query: initialQuery });
      setSearchState((current) => ({
        ...current,
        loading: false,
        items: result.items || [],
      }));
    } catch (error) {
      setSearchState((current) => ({ ...current, loading: false }));
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
            <Tag color="warning">{issue.reason}</Tag>
          </Space>
          <Text type="secondary" className="cleanup-path-text">
            {issue.path || "No path from provider"}
          </Text>
        </Flex>
      ),
    },
    {
      title: "Suggested Action",
      key: "suggestion",
      render: (_value, issue) => {
        const suggestion = issue.suggestions?.[0] || null;
        if (!suggestion) {
          return <Text type="secondary">No automatic match</Text>;
        }
        return (
          <Flex vertical gap={4}>
            <Space wrap>
              <Tag color="success">Best Match</Tag>
              <Tag>{suggestion.root_label}</Tag>
              <Tag>Score {suggestion.score}</Tag>
            </Space>
            <Text strong>{suggestion.label}</Text>
            <Text type="secondary" className="cleanup-path-text">
              {suggestion.path}
            </Text>
          </Flex>
        );
      },
    },
    {
      title: "Action",
      key: "action",
      width: 260,
      render: (_value, issue) => {
        const bestSuggestion = issue.suggestions?.[0] || null;
        return (
          <Space wrap>
            {bestSuggestion ? (
              <Tooltip title="Use best path">
                <Button
                  type="primary"
                  icon={<LinkOutlined />}
                  aria-label={`Use best path for ${issue.title}`}
                  loading={updatingKey === `${issue.id}:${bestSuggestion.path}`}
                  onClick={() => handleApplyPath(issue, bestSuggestion.path)}
                />
              </Tooltip>
            ) : null}
            <Tooltip title="Search folder">
              <Button
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
                Scan Missing Paths
              </Button>
              <Button
                type="primary"
                ghost
                disabled={!selectedBestMatchRows.length}
                loading={updatingKey === "__bulk__"}
                onClick={handleApplyBestPathsForSelected}
              >
                Use Best Path For Selected
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
        onCancel={() => setSearchState(emptySearchState)}
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
              try {
                const result = await searchPathRepairFolders({ provider: issue.provider, query: value });
                setSearchState((current) => ({
                  ...current,
                  loading: false,
                  items: result.items || [],
                }));
              } catch (error) {
                setSearchState((current) => ({ ...current, loading: false }));
                message.error(error.message);
              }
            }}
          />

          {searchState.loading ? (
            <div className="card-loading">
              <Spin size="large" />
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
                        <Tag>Score {item.score}</Tag>
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
