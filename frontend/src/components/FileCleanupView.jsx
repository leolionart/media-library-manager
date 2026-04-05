import { useEffect, useMemo, useState } from "react";
import { Alert, App as AntApp, Button, Card, Descriptions, Empty, Flex, Input, Space, Spin, Table, Tag, Typography } from "antd";
import { DeleteOutlined, FileSearchOutlined } from "@ant-design/icons";
import { deleteMovieFile, request, runCleanupScan } from "../api";
import { MediaLibraryLogPanel } from "./MediaLibraryLogPanel";

const { Text } = Typography;
const EMPTY_REPORT = {};

function formatBytes(value) {
  const size = Number(value || 0);
  if (!size) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1);
  const amount = size / 1024 ** exponent;
  return `${amount.toFixed(amount >= 10 || exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}

function keepCandidateKey(group) {
  return String(group?.items?.[0]?.storage_uri || group?.items?.[0]?.path || "");
}

function formatDate(value) {
  if (!value) return "Never";
  return new Date(value).toLocaleString();
}

function stripPriorityLabel(value) {
  return String(value || "").replace(/\s+P\d+$/, "").trim();
}

function summarizeLabels(items, limit = 3) {
  const labels = items.map((item) => stripPriorityLabel(item?.canonical_name || item?.title || item?.path || "")).filter(Boolean);
  if (!labels.length) return "None";
  if (labels.length <= limit) return labels.join(", ");
  return `${labels.slice(0, limit).join(", ")} +${labels.length - limit} more`;
}

function sameStringArray(left, right) {
  if (left === right) return true;
  if (left.length !== right.length) return false;
  for (let index = 0; index < left.length; index += 1) {
    if (String(left[index]) !== String(right[index])) return false;
  }
  return true;
}

function normalizeCleanupErrorMessage(value) {
  const message = String(value || "").trim();
  if (!message) return "Unknown error.";
  if (message.startsWith("[") && message.includes('"Path"') && message.includes('"Name"')) {
    return "The storage backend returned a raw directory listing instead of a readable error. Re-run the scan after restarting the backend.";
  }
  return message;
}

function CleanupErrorAlert({ errors }) {
  return (
    <Alert
      type="error"
      showIcon
      title="Provider file cleanup errors"
      description={
        <div className="cleanup-error-list">
          {errors.map((item, index) => (
            <div key={`${item.root_label || item.provider || item.root_path || "error"}-${index}`} className="cleanup-error-item">
              <Text strong className="cleanup-error-source">
                {stripPriorityLabel(item.root_label || item.provider || item.path || item.root_path || "Unknown source")}
              </Text>
              <Text className="cleanup-error-message">{normalizeCleanupErrorMessage(item.message)}</Text>
            </div>
          ))}
        </div>
      }
    />
  );
}

export function FileCleanupView() {
  const { message, modal } = AntApp.useApp();
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);
  const [payload, setPayload] = useState({});
  const [fileQuery, setFileQuery] = useState("");
  const [selectedGroupIds, setSelectedGroupIds] = useState([]);
  const [selectedFileKeys, setSelectedFileKeys] = useState([]);
  const [deletingKey, setDeletingKey] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    request("/api/state")
      .then((data) => {
        if (!cancelled) {
          setPayload(data || {});
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
  }, [message, refreshToken]);

  const cleanupReport = payload.cleanup_report || EMPTY_REPORT;
  const cleanupGroups = useMemo(() => cleanupReport.folder_media_duplicates || cleanupReport.groups || [], [cleanupReport]);
  const cleanupErrors = cleanupReport.errors || [];

  const filteredCleanupGroups = useMemo(() => {
    const search = fileQuery.trim().toLowerCase();
    if (!search) return cleanupGroups;
    return cleanupGroups.filter((group) =>
      [group.canonical_name, group.folder_path, group.root_label, group.kind, group.provider]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(search))
    );
  }, [cleanupGroups, fileQuery]);

  useEffect(() => {
    const validGroupIds = new Set(filteredCleanupGroups.map((group) => String(group.id)));
    setSelectedGroupIds((current) => {
      const next = current.filter((id) => validGroupIds.has(String(id)));
      return sameStringArray(current, next) ? current : next;
    });
  }, [filteredCleanupGroups]);

  const selectedGroups = useMemo(
    () => filteredCleanupGroups.filter((group) => selectedGroupIds.includes(String(group.id))),
    [filteredCleanupGroups, selectedGroupIds]
  );
  const selectedGroupSummary = useMemo(() => summarizeLabels(selectedGroups), [selectedGroups]);

  const suggestedKeepKeys = useMemo(
    () => new Set(selectedGroups.map((group) => keepCandidateKey(group)).filter(Boolean)),
    [selectedGroups]
  );

  const fileRows = useMemo(
    () =>
      selectedGroups.flatMap((group) =>
        (group.items || []).map((item) => ({
          ...item,
          groupId: String(group.id),
          groupTitle: group.canonical_name,
          groupFolderPath: group.folder_path,
          keepCandidateKey: keepCandidateKey(group),
          rowKey: `${group.id}:${item.storage_uri || item.path}`,
        }))
      ),
    [selectedGroups]
  );

  useEffect(() => {
    const validKeys = new Set(fileRows.map((item) => item.rowKey));
    setSelectedFileKeys((current) => {
      const next = current.filter((key) => validKeys.has(String(key)));
      return sameStringArray(current, next) ? current : next;
    });
  }, [fileRows]);

  async function refreshCleanup(providers = cleanupReport.providers || []) {
    await runCleanupScan(providers);
    setRefreshToken((value) => value + 1);
  }

  async function handleDeleteRows(rows) {
    if (!rows.length) return;
    for (const item of rows) {
      await deleteMovieFile({
        path: item.path,
        storageUri: item.storage_uri,
        rootPath: item.root_path,
        rootStorageUri: item.root_storage_uri,
      });
    }
    setSelectedFileKeys([]);
    await refreshCleanup();
  }

  function toggleGroupSelection(groupId) {
    const key = String(groupId);
    setSelectedGroupIds((current) => (current.includes(key) ? current.filter((item) => item !== key) : [...current, key]));
  }

  function toggleFileSelection(rowKey) {
    const key = String(rowKey);
    const row = fileRows.find((item) => item.rowKey === key);
    if (!row) return;
    if (suggestedKeepKeys.has(String(row.storage_uri || row.path || ""))) return;
    setSelectedFileKeys((current) => (current.includes(key) ? current.filter((item) => item !== key) : [...current, key]));
  }

  async function handleDeleteSelectedFiles() {
    const rows = fileRows.filter((item) => selectedFileKeys.includes(item.rowKey));
    if (!rows.length) return;
    await handleDeleteRows(rows);
  }

  async function handleRunProviderCleanupScan() {
    setActionLoading("scan-files");
    try {
      await runCleanupScan([]);
      setRefreshToken((value) => value + 1);
      message.success("Provider file cleanup scan completed.");
    } catch (error) {
      message.error(error.message);
    } finally {
      setActionLoading("");
    }
  }

  const groupColumns = [
    {
      title: "Title",
      key: "title",
      render: (_value, group) => (
        <Flex vertical gap={4}>
          <Space wrap>
            <Text strong>{stripPriorityLabel(group.canonical_name)}</Text>
            <Tag>{group.items.length} files</Tag>
          </Space>
          <Text type="secondary">{stripPriorityLabel(group.folder_path)}</Text>
        </Flex>
      ),
    },
    {
      title: "Provider",
      key: "provider",
      width: 120,
      render: (_value, group) => group.provider || group.kind || "-",
    },
    {
      title: "Root",
      dataIndex: "root_label",
      key: "root_label",
      width: 180,
      render: (value) => stripPriorityLabel(value),
    },
    {
      title: "Action",
      key: "action",
      width: 140,
      render: (_value, group) => (
        <Button size="small" onClick={() => setSelectedGroupIds([String(group.id)])}>
          Only This
        </Button>
      ),
    },
  ];

  const fileColumns = [
    {
      title: "Group",
      key: "group",
      width: 220,
      render: (_value, item) => (
        <Flex vertical gap={4}>
          <Text strong>{stripPriorityLabel(item.groupTitle)}</Text>
          <Text type="secondary">{stripPriorityLabel(item.groupFolderPath)}</Text>
        </Flex>
      ),
    },
    {
      title: "File",
      dataIndex: "path",
      key: "path",
      render: (_value, item) => {
        const itemKey = String(item.storage_uri || item.path || "");
        const isKeepCandidate = suggestedKeepKeys.has(itemKey);
        return (
          <Flex vertical gap={4}>
            <Space wrap>
              <Text strong>{stripPriorityLabel(String(item.path || "").split("/").pop())}</Text>
              {isKeepCandidate ? <Tag color="gold">Suggested keep</Tag> : null}
            </Space>
            <Text type="secondary" className="cleanup-path-text">
              {item.path}
            </Text>
          </Flex>
        );
      },
    },
    {
      title: "Quality",
      key: "quality",
      width: 220,
      render: (_value, item) => (
        <Space wrap>
          {item.resolution ? <Tag>{item.resolution}p</Tag> : null}
          {item.source ? <Tag>{String(item.source).toUpperCase()}</Tag> : null}
          {item.codec ? <Tag>{String(item.codec).toUpperCase()}</Tag> : null}
          <Tag>Q{item.quality_rank || 0}</Tag>
        </Space>
      ),
    },
    {
      title: "Size",
      dataIndex: "size",
      key: "size",
      width: 110,
      render: (value) => formatBytes(value),
    },
    {
      title: "Action",
      key: "action",
      width: 140,
      render: (_value, item) => {
        const itemKey = String(item.storage_uri || item.path || "");
        const disabled = suggestedKeepKeys.has(itemKey);
        return (
          <Button
            danger
            icon={<DeleteOutlined />}
            disabled={disabled}
            loading={deletingKey === itemKey}
            onClick={() =>
              modal.confirm({
                title: "Delete this media file?",
                content: item.path,
                okText: "Delete",
                okButtonProps: { danger: true },
                onOk: async () => {
                  setDeletingKey(itemKey);
                  try {
                    await handleDeleteRows([item]);
                    message.success("Media file deleted.");
                  } catch (error) {
                    message.error(error.message);
                  } finally {
                    setDeletingKey("");
                  }
                },
              })
            }
          >
            Delete
          </Button>
        );
      },
    },
  ];

  if (loading) {
    return (
      <div className="app-loading">
        <Spin size="large" />
      </div>
    );
  }

  return (
    <Flex vertical gap={16}>
      <Card
        title={
          <Space>
            <FileSearchOutlined />
            <span>Provider Duplicate Files</span>
          </Space>
        }
        className="cleanup-list-card"
      >
        <Flex vertical gap={16}>
          <div className="cleanup-toolbar">
            <Space wrap>
              <Button type="primary" loading={actionLoading === "scan-files"} onClick={handleRunProviderCleanupScan}>
                Scan Providers
              </Button>
            </Space>
            <Input.Search
              className="folder-list-search"
              value={fileQuery}
              onChange={(event) => setFileQuery(event.target.value)}
              allowClear
              placeholder="Filter by title, folder, provider, or root"
            />
          </div>

          <Descriptions
            size="small"
            column={{ xs: 1, md: 2, xl: 4 }}
            items={[
              { key: "last-scan", label: "Latest Scan", children: formatDate(payload.last_cleanup_at) },
              {
                key: "providers",
                label: "Providers",
                children: (cleanupReport.providers || []).length ? cleanupReport.providers.join(", ") : "None",
              },
              { key: "groups", label: "Groups", children: cleanupGroups.length },
              { key: "indexed", label: "Indexed Files", children: Number(cleanupReport.summary?.indexed_files || 0) },
            ]}
          />

          {cleanupErrors.length ? <CleanupErrorAlert errors={cleanupErrors} /> : null}

          {selectedGroupIds.length ? (
            <Flex justify="space-between" align="center" gap={12} wrap>
              <Space wrap>
                <Tag>{selectedGroupIds.length} selected group{selectedGroupIds.length === 1 ? "" : "s"}</Tag>
                <Tag>{fileRows.length} file{fileRows.length === 1 ? "" : "s"} in scope</Tag>
              </Space>
              <Space wrap>
                <Button onClick={() => setSelectedGroupIds([])}>Clear Selection</Button>
                <Button
                  danger
                  disabled={!selectedFileKeys.length}
                  onClick={() =>
                    modal.confirm({
                      title: `Delete ${selectedFileKeys.length} selected media file${selectedFileKeys.length === 1 ? "" : "s"}?`,
                      okText: "Delete",
                      okButtonProps: { danger: true },
                      onOk: async () => {
                        try {
                          await handleDeleteSelectedFiles();
                          message.success("Selected media files deleted.");
                        } catch (error) {
                          message.error(error.message);
                        }
                      },
                    })
                  }
                >
                  Delete Selected Files
                </Button>
              </Space>
            </Flex>
          ) : null}

          <Table
            size="small"
            rowKey={(group) => String(group.id)}
            pagination={{ pageSize: 8 }}
            dataSource={filteredCleanupGroups}
            rowSelection={{
              selectedRowKeys: selectedGroupIds,
              onChange: (keys) => setSelectedGroupIds(keys.map(String)),
            }}
            locale={{
              emptyText: (
                <Empty
                  description={
                    payload.last_cleanup_at
                      ? "No provider duplicate groups found in the latest cleanup scan."
                      : "Run a provider file cleanup scan to load duplicate groups from Radarr or Sonarr paths."
                  }
                />
              ),
            }}
            columns={groupColumns}
            onRow={(group) => ({
              onClick: (event) => {
                if (event.target.closest("button")) return;
                toggleGroupSelection(group.id);
              },
            })}
          />

          {selectedGroups.length ? (
            <Flex vertical gap={16}>
              <Flex justify="space-between" align="center" gap={12} wrap>
                <Text strong>Selected Provider Files</Text>
                <Space wrap>
                  <Tag>{selectedGroupSummary}</Tag>
                  <Tag>{fileRows.length} files</Tag>
                  <Tag>{selectedFileKeys.length} selected file{selectedFileKeys.length === 1 ? "" : "s"}</Tag>
                  <Button
                    danger
                    disabled={!selectedFileKeys.length}
                    onClick={() =>
                      modal.confirm({
                        title: `Delete ${selectedFileKeys.length} selected media file${selectedFileKeys.length === 1 ? "" : "s"}?`,
                        okText: "Delete",
                        okButtonProps: { danger: true },
                        onOk: async () => {
                          try {
                            await handleDeleteSelectedFiles();
                            message.success("Selected media files deleted.");
                          } catch (error) {
                            message.error(error.message);
                          }
                        },
                      })
                    }
                  >
                    Delete Selected
                  </Button>
                </Space>
              </Flex>

              <Table
                size="small"
                rowKey="rowKey"
                dataSource={fileRows}
                pagination={{ pageSize: 12 }}
                rowSelection={{
                  selectedRowKeys: selectedFileKeys,
                  onChange: (keys) => setSelectedFileKeys(keys.map(String)),
                  getCheckboxProps: (item) => ({
                    disabled: suggestedKeepKeys.has(String(item.storage_uri || item.path || "")),
                  }),
                }}
                columns={fileColumns}
                onRow={(item) => ({
                  onClick: (event) => {
                    if (event.target.closest("button")) return;
                    toggleFileSelection(item.rowKey);
                  },
                })}
              />
            </Flex>
          ) : null}
        </Flex>
      </Card>

      <MediaLibraryLogPanel scope="cleanup" title="Library Cleanup Logs" />
    </Flex>
  );
}

export default FileCleanupView;
