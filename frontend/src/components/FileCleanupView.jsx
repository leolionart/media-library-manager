import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Descriptions,
  Empty,
  Flex,
  Input,
  Segmented,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import { DeleteOutlined, FileSearchOutlined, FolderOpenOutlined } from "@ant-design/icons";
import { deleteFolder, deleteMovieFile, request, runCleanupScan, runEmptyFolderCleanupScan } from "../api";
import { MediaLibraryLogPanel } from "./MediaLibraryLogPanel";

const { Text } = Typography;

const CLEANUP_MODE_OPTIONS = [
  { label: "Duplicate Files", value: "files" },
  { label: "Empty Duplicate Folders", value: "folders" },
];
const CLEANUP_MODE_STORAGE_KEY = "media-library-manager.cleanup-mode";
const CLEANUP_INCLUDE_EMPTY_FOLDERS_STORAGE_KEY = "media-library-manager.cleanup.include-empty-folders";

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

function summarizeLabels(items, limit = 3) {
  const labels = items.map((item) => String(item?.canonical_name || item?.folder_name || item?.title || item?.path || "")).filter(Boolean);
  if (!labels.length) return "None";
  if (labels.length <= limit) return labels.join(", ");
  return `${labels.slice(0, limit).join(", ")} +${labels.length - limit} more`;
}

function normalizeSearchText(value) {
  return String(value || "")
    .toLowerCase()
    .replaceAll(/[\._()-]+/g, " ")
    .replaceAll(/\s+/g, " ")
    .trim();
}

function folderStatusMeta(item) {
  if (item?.has_video) return { color: "success", label: "Has Video" };
  if (item?.empty_reason === "empty") return { color: "default", label: "Empty Directory" };
  if (item?.empty_reason === "sidecar-only") return { color: "warning", label: "Sidecar Only" };
  return { color: "warning", label: "No Video" };
}

export function FileCleanupView() {
  const { message, modal } = AntApp.useApp();
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState("");
  const [refreshToken, setRefreshToken] = useState(0);
  const [payload, setPayload] = useState({});
  const [mode, setMode] = useState(() => {
    if (typeof window === "undefined") return "folders";
    const savedMode = window.localStorage.getItem(CLEANUP_MODE_STORAGE_KEY);
    return savedMode === "files" || savedMode === "folders" ? savedMode : "folders";
  });
  const [includeEmptyFolderCleanup, setIncludeEmptyFolderCleanup] = useState(() => {
    if (typeof window === "undefined") return true;
    const savedValue = window.localStorage.getItem(CLEANUP_INCLUDE_EMPTY_FOLDERS_STORAGE_KEY);
    return savedValue === null ? true : savedValue === "true";
  });
  const [fileQuery, setFileQuery] = useState("");
  const [folderQuery, setFolderQuery] = useState("");
  const [selectedGroupIds, setSelectedGroupIds] = useState([]);
  const [selectedFileKeys, setSelectedFileKeys] = useState([]);
  const [selectedEmptyGroupIds, setSelectedEmptyGroupIds] = useState([]);
  const [selectedEmptyFolderKeys, setSelectedEmptyFolderKeys] = useState([]);
  const [deletingKey, setDeletingKey] = useState("");
  const [deletingFolderKey, setDeletingFolderKey] = useState("");
  const [autoSelectedFolderScope, setAutoSelectedFolderScope] = useState("");

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

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(CLEANUP_MODE_STORAGE_KEY, mode);
    }
  }, [mode]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(CLEANUP_INCLUDE_EMPTY_FOLDERS_STORAGE_KEY, String(includeEmptyFolderCleanup));
    }
  }, [includeEmptyFolderCleanup]);

  const cleanupReport = payload.cleanup_report || {};
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
    setSelectedGroupIds((current) => current.filter((id) => validGroupIds.has(String(id))));
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
    setSelectedFileKeys((current) => current.filter((key) => validKeys.has(String(key))));
  }, [fileRows]);

  const emptyFolderReport = payload.empty_folder_cleanup_report || {};
  const emptyFolderGroups = useMemo(() => emptyFolderReport.groups || [], [emptyFolderReport]);
  const emptyFolderErrors = emptyFolderReport.errors || [];

  const filteredEmptyFolderGroups = useMemo(() => {
    const search = normalizeSearchText(folderQuery);
    if (!search) return emptyFolderGroups;
    return emptyFolderGroups.filter((group) =>
      [
        group.folder_name,
        group.canonical_name,
        ...(group.items || []).flatMap((item) => [item.path, item.root_label, item.root_path, item.status]),
      ]
        .filter(Boolean)
        .some((value) => normalizeSearchText(value).includes(search))
    );
  }, [emptyFolderGroups, folderQuery]);

  useEffect(() => {
    const validGroupIds = new Set(filteredEmptyFolderGroups.map((group) => String(group.id)));
    setSelectedEmptyGroupIds((current) => current.filter((id) => validGroupIds.has(String(id))));
  }, [filteredEmptyFolderGroups]);

  const selectedEmptyGroups = useMemo(
    () => filteredEmptyFolderGroups.filter((group) => selectedEmptyGroupIds.includes(String(group.id))),
    [filteredEmptyFolderGroups, selectedEmptyGroupIds]
  );
  const selectedEmptyGroupSummary = useMemo(() => summarizeLabels(selectedEmptyGroups), [selectedEmptyGroups]);

  const emptyFolderRows = useMemo(
    () =>
      selectedEmptyGroups.flatMap((group) =>
        (group.items || []).map((item) => ({
          ...item,
          groupId: String(group.id),
          groupFolderName: group.folder_name || group.canonical_name,
          groupDeleteCandidates: Number(group.deletion_candidate_count || 0),
          rowKey: `${group.id}:${item.delete_path || item.storage_uri || item.path || item.root_path || item.root_label}`,
        }))
      ),
    [selectedEmptyGroups]
  );

  useEffect(() => {
    const validKeys = new Set(emptyFolderRows.map((item) => item.rowKey));
    setSelectedEmptyFolderKeys((current) => current.filter((key) => validKeys.has(String(key))));
  }, [emptyFolderRows]);

  const emptyFolderAutoSelectionScope = useMemo(
    () => `${payload.last_empty_folder_cleanup_at || ""}:${selectedEmptyGroupIds.slice().sort().join("|")}`,
    [payload.last_empty_folder_cleanup_at, selectedEmptyGroupIds]
  );

  const emptyFolderCandidateKeys = useMemo(
    () => emptyFolderRows.filter((item) => item.is_deletion_candidate).map((item) => item.rowKey),
    [emptyFolderRows]
  );

  useEffect(() => {
    if (!selectedEmptyGroupIds.length) {
      setAutoSelectedFolderScope("");
      return;
    }
    if (autoSelectedFolderScope === emptyFolderAutoSelectionScope) {
      return;
    }
    setSelectedEmptyFolderKeys((current) => {
      const validKeys = new Set(emptyFolderRows.map((item) => item.rowKey));
      const next = new Set(current.filter((key) => validKeys.has(String(key))));
      for (const key of emptyFolderCandidateKeys) {
        next.add(String(key));
      }
      return Array.from(next);
    });
    setAutoSelectedFolderScope(emptyFolderAutoSelectionScope);
  }, [
    autoSelectedFolderScope,
    emptyFolderAutoSelectionScope,
    emptyFolderCandidateKeys,
    emptyFolderRows,
    selectedEmptyGroupIds.length,
  ]);

  async function refreshCleanup(providers = cleanupReport.providers || []) {
    await runCleanupScan(providers);
    setRefreshToken((value) => value + 1);
  }

  async function refreshEmptyFolderCleanup() {
    await runEmptyFolderCleanupScan();
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

  async function handleDeleteEmptyFolders(rows) {
    if (!rows.length) return;
    for (const item of rows) {
      await deleteFolder(item.delete_path || item.path);
    }
    setSelectedEmptyFolderKeys([]);
    await refreshEmptyFolderCleanup();
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

  function toggleEmptyGroupSelection(groupId) {
    const key = String(groupId);
    setSelectedEmptyGroupIds((current) => (current.includes(key) ? current.filter((item) => item !== key) : [...current, key]));
  }

  function toggleEmptyFolderSelection(rowKey) {
    const key = String(rowKey);
    const row = emptyFolderRows.find((item) => item.rowKey === key);
    if (!row || !row.is_deletion_candidate) return;
    setSelectedEmptyFolderKeys((current) => (current.includes(key) ? current.filter((item) => item !== key) : [...current, key]));
  }

  async function handleDeleteSelectedFiles() {
    const rows = fileRows.filter((item) => selectedFileKeys.includes(item.rowKey));
    if (!rows.length) return;
    await handleDeleteRows(rows);
  }

  async function handleDeleteSelectedEmptyFolders() {
    const rows = emptyFolderRows.filter((item) => selectedEmptyFolderKeys.includes(item.rowKey) && item.is_deletion_candidate);
    if (!rows.length) return;
    await handleDeleteEmptyFolders(rows);
  }

  async function handleRunProviderCleanupScan() {
    setActionLoading("scan-files");
    let providerScanCompleted = false;
    let emptyFolderScanCompleted = false;
    try {
      await runCleanupScan([]);
      providerScanCompleted = true;
      if (includeEmptyFolderCleanup) {
        try {
          await runEmptyFolderCleanupScan();
          emptyFolderScanCompleted = true;
          setMode("folders");
        } catch (error) {
          message.warning(
            `Provider cleanup scan completed, but empty duplicate folder scan failed. Saved folder results were kept. ${error.message}`
          );
        }
      }
      if (!includeEmptyFolderCleanup) {
        message.success("Provider cleanup scan completed.");
      } else if (emptyFolderScanCompleted) {
        message.success("Cleanup scans completed. Empty duplicate folder results were refreshed too.");
      }
    } catch (error) {
      message.error(error.message);
    } finally {
      if (providerScanCompleted || emptyFolderScanCompleted) {
        setRefreshToken((value) => value + 1);
      }
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
            <Text strong>{group.canonical_name}</Text>
            <Tag>{group.items.length} files</Tag>
          </Space>
          <Text type="secondary">{group.folder_path}</Text>
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
      width: 180,
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
          <Text strong>{item.groupTitle}</Text>
          <Text type="secondary">{item.groupFolderPath}</Text>
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
              <Text strong>{String(item.path || "").split("/").pop()}</Text>
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

  const emptyFolderGroupColumns = [
    {
      title: "Folder",
      key: "folder",
      render: (_value, group) => (
        <Flex vertical gap={4}>
          <Space wrap>
            <Text strong>{group.folder_name || group.canonical_name}</Text>
            <Tag>{group.items.length} copies</Tag>
            {Number(group.deletion_candidate_count || 0) ? <Tag color="warning">{group.deletion_candidate_count} cleanup</Tag> : null}
          </Space>
          <Text type="secondary">{summarizeLabels(group.items || [])}</Text>
        </Flex>
      ),
    },
    {
      title: "Video Copies",
      key: "video",
      width: 140,
      render: (_value, group) => (
        <Space wrap>
          <Tag color="success">{(group.items || []).filter((item) => item.has_video).length} with video</Tag>
          <Tag>{(group.items || []).filter((item) => !item.has_video).length} without video</Tag>
        </Space>
      ),
    },
    {
      title: "Roots",
      key: "roots",
      width: 240,
      render: (_value, group) => (
        <Space wrap>
          {[...new Set((group.items || []).map((item) => item.root_label).filter(Boolean))].map((label) => (
            <Tag key={label}>{label}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: "Action",
      key: "action",
      width: 140,
      render: (_value, group) => (
        <Button size="small" onClick={() => setSelectedEmptyGroupIds([String(group.id)])}>
          Only This
        </Button>
      ),
    },
  ];

  const emptyFolderColumns = [
    {
      title: "Group",
      key: "group",
      width: 220,
      render: (_value, item) => (
        <Flex vertical gap={4}>
          <Text strong>{item.groupFolderName}</Text>
          <Text type="secondary">{item.root_label || item.root_path || "-"}</Text>
        </Flex>
      ),
    },
    {
      title: "Folder",
      key: "folder",
      render: (_value, item) => (
        <Flex vertical gap={4}>
            <Space wrap>
              <Text strong>{String(item.path || "").split("/").pop() || item.groupFolderName}</Text>
              <Tag color={folderStatusMeta(item).color}>{folderStatusMeta(item).label}</Tag>
              {item.is_deletion_candidate ? <Tag color="warning">Delete Candidate</Tag> : <Tag color="success">Keep</Tag>}
            </Space>
            <Text type="secondary" className="cleanup-path-text">
              {item.path}
            </Text>
          </Flex>
      ),
    },
    {
      title: "Contents",
      key: "contents",
      width: 220,
      render: (_value, item) => (
        <Space wrap>
          {item.root_kind ? <Tag>{String(item.root_kind).toUpperCase()}</Tag> : null}
          {item.empty_reason ? <Tag>{item.empty_reason}</Tag> : <Tag color="success">media present</Tag>}
        </Space>
      ),
    },
    {
      title: "Action",
      key: "action",
      width: 140,
      render: (_value, item) => (
        <Button
          danger
          icon={<DeleteOutlined />}
          disabled={!item.is_deletion_candidate}
          loading={deletingFolderKey === item.rowKey}
          onClick={() =>
            modal.confirm({
              title: "Delete this folder?",
              content: item.path,
              okText: "Delete",
              okButtonProps: { danger: true },
              onOk: async () => {
                setDeletingFolderKey(item.rowKey);
                try {
                  await handleDeleteEmptyFolders([item]);
                  message.success("Folder deleted.");
                } catch (error) {
                  message.error(error.message);
                } finally {
                  setDeletingFolderKey("");
                }
              },
            })
          }
        >
          Delete
        </Button>
      ),
    },
  ];

  const fileModeContent = (
    <Flex vertical gap={16}>
      <div className="cleanup-toolbar">
        <Space wrap>
          <Button
            type="primary"
            loading={actionLoading === "scan-files"}
            onClick={handleRunProviderCleanupScan}
          >
            Scan Providers
          </Button>
          <Space size={8}>
            <Switch checked={includeEmptyFolderCleanup} onChange={setIncludeEmptyFolderCleanup} />
            <Text>Also refresh empty duplicate folders</Text>
          </Space>
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
          { key: "selected-groups", label: "Selected Groups", children: selectedGroupSummary },
        ]}
      />

      <Alert
        type="info"
        showIcon
        message="Cleanup reports are saved automatically."
        description={
          payload.last_cleanup_at
            ? `Latest provider cleanup scan: ${formatDate(payload.last_cleanup_at)}. Refreshing the browser keeps this report until you run another scan.`
            : "Run a cleanup scan once, then the saved report stays available after refresh."
        }
      />

      {cleanupErrors.length ? (
        <Alert
          type="error"
          showIcon
          message="Provider scan errors"
          description={cleanupErrors.map((item) => `${item.provider}: ${item.message}`).join(" • ")}
        />
      ) : null}

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
                  ? "No duplicate groups found in the latest cleanup scan."
                  : "Run a cleanup scan to load provider duplicate groups."
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
            <Text strong>Selected Files</Text>
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
  );

  const folderModeContent = (
    <Flex vertical gap={16}>
      <div className="cleanup-toolbar">
        <Space wrap>
          <Button
            type="primary"
            loading={actionLoading === "scan-empty-folders"}
            onClick={async () => {
              setActionLoading("scan-empty-folders");
              try {
                await runEmptyFolderCleanupScan();
                message.success("Empty duplicate folder cleanup scan completed.");
                setRefreshToken((value) => value + 1);
              } catch (error) {
                message.error(error.message);
              } finally {
                setActionLoading("");
              }
            }}
          >
            Find Empty Duplicate Folders
          </Button>
        </Space>
        <Input.Search
          className="folder-list-search"
          value={folderQuery}
          onChange={(event) => setFolderQuery(event.target.value)}
          allowClear
          placeholder="Filter by folder, path, root, or status"
        />
      </div>

      <Descriptions
        size="small"
        column={{ xs: 1, md: 2, xl: 4 }}
        items={[
          {
            key: "last-empty-scan",
            label: "Latest Scan",
            children: formatDate(payload.last_empty_folder_cleanup_at),
          },
          { key: "roots", label: "Roots Scanned", children: Number(emptyFolderReport.summary?.roots_scanned || 0) },
          { key: "groups", label: "Duplicate Groups", children: filteredEmptyFolderGroups.length },
          {
            key: "cleanup",
            label: "Delete Candidates",
            children: Number(emptyFolderReport.summary?.deletion_candidates || 0),
          },
          {
            key: "selected-empty-groups",
            label: "Selected Groups",
            children: selectedEmptyGroupSummary,
          },
        ]}
      />

      <Alert
        type="info"
        showIcon
        message="Folder junk cleanup is the default view."
        description={
          payload.last_empty_folder_cleanup_at
            ? `Latest empty-folder cleanup scan: ${formatDate(payload.last_empty_folder_cleanup_at)}. Reports survive refresh, and delete candidates are auto-selected when you open a group.`
            : "This scan compares top-level duplicate folder names across connected roots, then inspects only the duplicate groups recursively. Sidecar-only and fully empty folders are shown as cleanup candidates."
        }
      />

      {emptyFolderErrors.length ? (
        <Alert
          type="error"
          showIcon
          message="Empty folder scan errors"
          description={emptyFolderErrors.map((item) => `${item.root_label || item.path || item.root_path}: ${item.message}`).join(" • ")}
        />
      ) : null}

      {selectedEmptyGroupIds.length ? (
        <Flex justify="space-between" align="center" gap={12} wrap>
          <Space wrap>
            <Tag>{selectedEmptyGroupIds.length} selected group{selectedEmptyGroupIds.length === 1 ? "" : "s"}</Tag>
            <Tag>{emptyFolderRows.length} folder copies in scope</Tag>
            <Tag>{selectedEmptyFolderKeys.length} selected for delete</Tag>
          </Space>
          <Space wrap>
            <Button onClick={() => setSelectedEmptyGroupIds([])}>Clear Selection</Button>
            <Button
              danger
              disabled={!selectedEmptyFolderKeys.length}
              onClick={() =>
                modal.confirm({
                  title: `Delete ${selectedEmptyFolderKeys.length} selected folder${selectedEmptyFolderKeys.length === 1 ? "" : "s"}?`,
                  content: "Only the selected no-video duplicates will be removed.",
                  okText: "Delete",
                  okButtonProps: { danger: true },
                  onOk: async () => {
                    try {
                      await handleDeleteSelectedEmptyFolders();
                      message.success("Selected folders deleted.");
                    } catch (error) {
                      message.error(error.message);
                    }
                  },
                })
              }
            >
              Delete Selected Folders
            </Button>
          </Space>
        </Flex>
      ) : null}

      <Table
        size="small"
        rowKey={(group) => String(group.id)}
        pagination={{ pageSize: 8 }}
        dataSource={filteredEmptyFolderGroups}
        rowSelection={{
          selectedRowKeys: selectedEmptyGroupIds,
          onChange: (keys) => setSelectedEmptyGroupIds(keys.map(String)),
        }}
        locale={{
          emptyText: (
            <Empty
              description={
                payload.last_empty_folder_cleanup_at
                  ? "No duplicate folders without video were found in the latest scan."
                  : "Run an empty-folder cleanup scan to load duplicate folder candidates."
              }
            />
          ),
        }}
        columns={emptyFolderGroupColumns}
        onRow={(group) => ({
          onClick: (event) => {
            if (event.target.closest("button")) return;
            toggleEmptyGroupSelection(group.id);
          },
        })}
      />

      {selectedEmptyGroups.length ? (
        <Flex vertical gap={16}>
          <Flex justify="space-between" align="center" gap={12} wrap>
            <Text strong>Selected Folder Copies</Text>
            <Space wrap>
              <Tag>{selectedEmptyGroupSummary}</Tag>
              <Tag>{emptyFolderRows.length} copies</Tag>
              <Tag>{selectedEmptyFolderKeys.length} selected</Tag>
              <Button
                danger
                disabled={!selectedEmptyFolderKeys.length}
                onClick={() =>
                  modal.confirm({
                    title: `Delete ${selectedEmptyFolderKeys.length} selected folder${selectedEmptyFolderKeys.length === 1 ? "" : "s"}?`,
                    content: "Only the checked no-video duplicate folders will be removed.",
                    okText: "Delete",
                    okButtonProps: { danger: true },
                    onOk: async () => {
                      try {
                        await handleDeleteSelectedEmptyFolders();
                        message.success("Selected folders deleted.");
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
            dataSource={emptyFolderRows}
            pagination={{ pageSize: 12 }}
            rowSelection={{
              selectedRowKeys: selectedEmptyFolderKeys,
              onChange: (keys) => setSelectedEmptyFolderKeys(keys.map(String)),
              getCheckboxProps: (item) => ({
                disabled: !item.is_deletion_candidate,
              }),
            }}
            columns={emptyFolderColumns}
            onRow={(item) => ({
              onClick: (event) => {
                if (event.target.closest("button")) return;
                toggleEmptyFolderSelection(item.rowKey);
              },
            })}
          />
        </Flex>
      ) : null}
    </Flex>
  );

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
            {mode === "files" ? <FileSearchOutlined /> : <FolderOpenOutlined />}
            <span>{mode === "files" ? "Provider Duplicate Groups" : "Empty Duplicate Folders"}</span>
          </Space>
        }
        className="cleanup-list-card"
        extra={
          <Segmented
            className="process-log-filter-segmented"
            options={CLEANUP_MODE_OPTIONS}
            value={mode}
            onChange={setMode}
          />
        }
      >
        {mode === "files" ? fileModeContent : folderModeContent}
      </Card>

      <MediaLibraryLogPanel scope="cleanup" title="Cleanup Action Logs" />
    </Flex>
  );
}

export default FileCleanupView;
