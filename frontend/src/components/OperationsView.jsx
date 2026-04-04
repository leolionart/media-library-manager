import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Col,
  Descriptions,
  Dropdown,
  Empty,
  Flex,
  Input,
  List,
  Modal,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import {
  FileOutlined,
  FolderOpenOutlined,
  LoadingOutlined,
  MoreOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import {
  applyPlan,
  buildPlan,
  deleteFolder,
  executeMoveToProvider,
  fetchOperationsData,
  fetchOperationsFolderChildren,
  fetchProviderItems,
  previewMoveToProvider,
  removeRoot,
  runScan,
} from "../api";

const { Text } = Typography;

const emptyState = {
  roots: [],
  integrations: {
    radarr: { enabled: false },
    sonarr: { enabled: false },
  },
  report: null,
  plan: null,
  apply_result: null,
  activity_log: [],
  current_job: null,
  last_scan_at: null,
  last_plan_at: null,
  last_apply_at: null,
};

const emptyProviderModal = {
  open: false,
  provider: "radarr",
  source: "",
  sourceLabel: "",
  items: [],
  query: "",
  selectedItemId: "",
  preview: null,
  loading: false,
};

function formatDate(value) {
  if (!value) return "Never";
  return new Date(value).toLocaleString();
}

function formatBytes(value) {
  if (!value) return "0 B";
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let size = value;
  let unitIndex = -1;
  do {
    size /= 1024;
    unitIndex += 1;
  } while (size >= 1024 && unitIndex < units.length - 1);
  return `${size.toFixed(size >= 100 ? 0 : 1)} ${units[unitIndex]}`;
}

function normalizeSearchText(value) {
  return String(value || "")
    .toLowerCase()
    .replaceAll(/[\._()-]+/g, " ")
    .replaceAll(/\s+/g, " ")
    .trim();
}

function compactDisplayPath(record) {
  if (record.is_root) {
    return record.path;
  }

  const display = String(record.display_path || record.path || "");
  const rootLabel = String(record.root_label || "");

  if (!display) {
    return "-";
  }

  if (display === record.label) {
    return rootLabel ? `${rootLabel} / ${record.label}` : record.label;
  }

  return display;
}

function scoreProviderItem(item, query) {
  const normalizedQuery = normalizeSearchText(query);
  const normalizedTitle = normalizeSearchText(item.title);

  if (!normalizedQuery) return 0;
  if (normalizedTitle === normalizedQuery) return 100;
  if (normalizedTitle.startsWith(normalizedQuery)) return 80;
  if (normalizedTitle.includes(normalizedQuery)) return 60;

  const queryTokens = normalizedQuery.split(" ").filter(Boolean);
  const titleTokens = new Set(normalizedTitle.split(" ").filter(Boolean));
  return queryTokens.filter((token) => titleTokens.has(token)).length * 10;
}

function buildFolderTableData(roots, items) {
  const rootRows = (roots || [])
    .map((root) => {
      const rootKey = root.storage_uri || root.path;
      const row = {
        key: rootKey,
        label: root.label,
        path: root.path,
        display_path: root.label,
        root_path: root.path,
        root_label: root.label,
        connection_id: root.connection_id,
        connection_label: root.connection_label,
        kind: root.kind,
        priority: root.priority,
        storage_uri: root.storage_uri || root.path,
        root_storage_uri: root.storage_uri || root.path,
        is_root: true,
        has_children: true,
        children_loaded: false,
        is_loading: false,
        children: [],
      };
      return row;
    })
    .sort((left, right) => String(left.label).localeCompare(String(right.label)));

  const groupedItems = new Map();
  (items || []).forEach((item) => {
    const rootKey = item.root_storage_uri || item.root_path || item.root_label;
    if (!groupedItems.has(rootKey)) groupedItems.set(rootKey, []);
    groupedItems.get(rootKey).push({
      ...item,
      key: item.storage_uri || item.path,
      is_root: false,
      has_children: Boolean(item.has_children),
      children_loaded: !item.has_children,
      is_file: Boolean(item.is_file),
      is_loading: false,
      children: item.has_children ? [] : undefined,
    });
  });

  return rootRows.map((root) => {
    const children = (groupedItems.get(root.key) || []).sort(
      (left, right) =>
        String(left.display_path || left.label).localeCompare(String(right.display_path || right.label)) ||
        String(left.label).localeCompare(String(right.label))
    );
    return {
      ...root,
      has_children: true,
      children_loaded: children.length > 0,
      children: children.length ? children : [],
    };
  });
}

function buildDuplicateScanSelection(records) {
  return (records || [])
    .filter((record) => record && !record.is_file)
    .map((record) => ({
      label: record.label,
      path: record.path,
      root_path: record.root_path,
      root_label: record.root_label,
      connection_id: record.connection_id,
      connection_label: record.connection_label,
      kind: record.kind,
      priority: record.priority,
      storage_uri: String(record.storage_uri || "").includes("://") ? record.storage_uri : "",
      root_storage_uri: String(record.root_storage_uri || "").includes("://") ? record.root_storage_uri : "",
    }));
}

function replaceNodeChildren(rows, targetKey, children) {
  return rows.map((row) => {
    if (row.key === targetKey) {
      return {
        ...row,
        children: children.length ? children : undefined,
        has_children: children.length > 0,
        children_loaded: true,
        is_loading: false,
      };
    }
    if (!row.children?.length) return row;
    return { ...row, children: replaceNodeChildren(row.children, targetKey, children) };
  });
}

function updateNode(rows, targetKey, updater) {
  return rows.map((row) => {
    if (row.key === targetKey) {
      return updater(row);
    }
    if (!row.children?.length) return row;
    return { ...row, children: updateNode(row.children, targetKey, updater) };
  });
}

function filterFolderTableData(rows, query) {
  if (!query) return rows;

  return rows
    .map((row) => {
      const matchesRow = [row.label, row.path, row.display_path, row.root_label, row.connection_label, row.kind]
        .filter(Boolean)
        .some((value) => normalizeSearchText(value).includes(query));

      if (matchesRow) {
        return row;
      }

      const children = (row.children || []).filter((child) =>
        [child.label, child.path, child.display_path, child.root_label, child.connection_label, child.kind]
          .filter(Boolean)
          .some((value) => normalizeSearchText(value).includes(query))
      );

      if (!children.length) {
        return null;
      }

      return { ...row, children };
    })
    .filter(Boolean);
}

function StatusTag({ value }) {
  const status = String(value || "").toLowerCase();
  let color = "default";

  if (["success", "applied", "running", "info"].includes(status)) color = "success";
  if (["error", "failed"].includes(status)) color = "error";
  if (["dry-run", "review"].includes(status)) color = "processing";

  return <Tag color={color}>{value || "unknown"}</Tag>;
}

function ProviderMoveModal({
  modalState,
  rankedItems,
  selectedItem,
  suggestedItem,
  actionLoading,
  onCancel,
  onQueryChange,
  onSelectItem,
  onPreview,
  onConfirm,
}) {
  return (
    <Modal
      open={modalState.open}
      title={modalState.provider === "radarr" ? "Move Folder To Radarr Movie" : "Move Folder To Sonarr Series"}
      okText="Move Folder"
      onCancel={onCancel}
      onOk={onConfirm}
      okButtonProps={{ disabled: !selectedItem, loading: actionLoading === "move-to-provider" }}
      width={720}
    >
      <Flex vertical gap={16}>
        <Descriptions
          column={1}
          bordered
          size="small"
          items={[
            {
              key: "source",
              label: "Source folder",
              children: (
                <Flex vertical gap={4}>
                  <Text strong>{modalState.sourceLabel || "-"}</Text>
                  <Text type="secondary" className="mono">
                    {modalState.source || "-"}
                  </Text>
                </Flex>
              ),
            },
          ]}
        />

        <Input
          value={modalState.query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder={`Search ${modalState.provider} by movie or series title`}
        />

        <Select
          showSearch
          optionFilterProp="label"
          value={modalState.selectedItemId || undefined}
          loading={modalState.loading}
          onChange={onSelectItem}
          placeholder="Choose the destination item"
          options={rankedItems.map(({ item, score }) => ({
            value: String(item.id),
            label: `${item.title}${item.year ? ` (${item.year})` : ""}${score ? ` • match ${score}` : ""}`,
          }))}
        />

        {suggestedItem ? (
          <Alert
            type="info"
            showIcon
            message={`Suggested match: ${suggestedItem.item.title}${suggestedItem.item.year ? ` (${suggestedItem.item.year})` : ""}`}
            description={
              <Flex justify="space-between" align="center" gap={12} wrap>
                <Text type="secondary" className="mono">
                  {suggestedItem.item.path}
                </Text>
                <Button size="small" onClick={() => onSelectItem(String(suggestedItem.item.id))}>
                  Use Suggested
                </Button>
              </Flex>
            }
          />
        ) : null}

        {selectedItem ? (
          <Descriptions
            column={1}
            bordered
            size="small"
            items={[
              {
                key: "destination-title",
                label: "Destination title",
                children: `${selectedItem.title}${selectedItem.year ? ` (${selectedItem.year})` : ""}`,
              },
              {
                key: "destination-path",
                label: "Destination path",
                children: <Text className="mono">{selectedItem.path}</Text>,
              },
            ]}
          />
        ) : (
          <Empty description="Choose a destination title to continue." />
        )}

        {modalState.preview?.move_result ? (
          <Alert
            type="info"
            showIcon
            message="Preview destination"
            description={modalState.preview.move_result.destination || modalState.preview.move_result.destination_parent}
          />
        ) : null}

        <Flex justify="flex-start">
          <Button disabled={!selectedItem} loading={actionLoading === "preview-provider-move"} onClick={onPreview}>
            Preview Destination
          </Button>
        </Flex>
      </Flex>
    </Modal>
  );
}

export function OperationsView() {
  const { message, modal } = AntApp.useApp();
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState("");
  const [payload, setPayload] = useState(emptyState);
  const [currentJob, setCurrentJob] = useState(null);
  const [folderItems, setFolderItems] = useState([]);
  const [folderTreeRows, setFolderTreeRows] = useState([]);
  const [folderSummary, setFolderSummary] = useState({ items: 0, roots: 0 });
  const [expandedRowKeys, setExpandedRowKeys] = useState([]);
  const [loadingBranchKeys, setLoadingBranchKeys] = useState([]);
  const [search, setSearch] = useState("");
  const [selectedNodeKeys, setSelectedNodeKeys] = useState([]);
  const [deleteLowerQuality, setDeleteLowerQuality] = useState(false);
  const [pruneEmptyDirs, setPruneEmptyDirs] = useState(true);
  const [providerModal, setProviderModal] = useState(emptyProviderModal);

  const refreshAll = async () => {
    const data = await fetchOperationsData();
    setPayload(data.state || emptyState);
    setCurrentJob(data.process || data.state?.current_job || null);
    setFolderItems(data.operationsFolders || []);
    setFolderSummary(data.operationsSummary || { items: 0, roots: 0 });
    const initialRows = buildFolderTableData(data.state?.roots || [], data.operationsFolders || []);
    setFolderTreeRows(initialRows);
    setExpandedRowKeys(initialRows.filter((row) => row.children?.length).map((row) => row.key));
    const allowedKeys = new Set();
    const visit = (rows) => rows.forEach((row) => {
      allowedKeys.add(row.key);
      if (row.children?.length) visit(row.children);
    });
    visit(initialRows);
    setSelectedNodeKeys((current) => current.filter((key) => allowedKeys.has(key)));
    return data;
  };

  useEffect(() => {
    refreshAll()
      .catch((error) => message.error(error.message))
      .finally(() => setLoading(false));
  }, [message]);

  const tableData = folderTreeRows;

  const nodeMap = useMemo(() => {
    const map = new Map();
    const visit = (nodes) => {
      nodes.forEach((node) => {
        map.set(node.key, node);
        if (node.children?.length) visit(node.children);
      });
    };
    visit(tableData);
    return map;
  }, [tableData]);

  const filteredTableData = useMemo(() => {
    const query = normalizeSearchText(search);
    return filterFolderTableData(tableData, query);
  }, [search, tableData]);

  const selectedRecords = useMemo(
    () => selectedNodeKeys.map((key) => nodeMap.get(key)).filter(Boolean),
    [nodeMap, selectedNodeKeys]
  );
  const selectedFolders = useMemo(
    () => selectedRecords.filter((record) => !record.is_root && !record.is_file),
    [selectedRecords]
  );
  const selectedFiles = useMemo(
    () => selectedRecords.filter((record) => !record.is_root && record.is_file),
    [selectedRecords]
  );
  const selectedRoots = useMemo(() => selectedRecords.filter((record) => record.is_root), [selectedRecords]);
  const selectedFolder =
    selectedFolders.length === 1 && selectedRoots.length === 0 && selectedFiles.length === 0 ? selectedFolders[0] : null;
  const canMoveToRadarr = Boolean(payload.integrations?.radarr?.enabled && selectedFolder);
  const canMoveToSonarr = Boolean(payload.integrations?.sonarr?.enabled && selectedFolder);
  const selectedPaths = selectedFolders.map((record) => record.path);
  const selectedRootPaths = selectedRoots.map((record) => record.path);
  const duplicateScanSelection = useMemo(() => buildDuplicateScanSelection(selectedRecords), [selectedRecords]);
  const treeSummary = {
    roots: folderSummary.roots || payload.roots?.length || 0,
    nodes: folderItems.length || 0,
    max_depth: "Unlimited",
  };

  const rankedProviderItems = useMemo(
    () =>
      [...providerModal.items]
        .map((item) => ({ item, score: scoreProviderItem(item, providerModal.query) }))
        .filter(({ item, score }) => {
          if (!providerModal.query.trim()) return true;
          return score > 0 || normalizeSearchText(item.title).includes(normalizeSearchText(providerModal.query));
        })
        .sort((left, right) => right.score - left.score || String(left.item.title).localeCompare(String(right.item.title))),
    [providerModal.items, providerModal.query]
  );

  const selectedProviderItem = useMemo(
    () => providerModal.items.find((item) => String(item.id) === String(providerModal.selectedItemId)) || null,
    [providerModal.items, providerModal.selectedItemId]
  );

  const suggestedProviderItem = rankedProviderItems[0] || null;
  const operationsSummary = payload.report?.summary || {};
  const planSummary = payload.plan?.summary || {};
  const exactDuplicates = payload.report?.exact_duplicates || [];
  const collisions = payload.report?.media_collisions || [];
  const planActions = payload.plan?.actions || [];
  const applyResult = payload.apply_result;
  const recentActivity = (payload.activity_log || []).slice(0, 10);

  const runAction = async (actionKey, action, successMessage) => {
    setActionLoading(actionKey);
    try {
      const result = await action();
      await refreshAll();
      if (successMessage) message.success(successMessage);
      return result;
    } catch (error) {
      message.error(error.message);
      return null;
    } finally {
      setActionLoading("");
    }
  };

  const handleRefreshFolders = async () => {
    setActionLoading("refresh-folders");
    try {
      await refreshAll();
      message.success("Folder list refreshed.");
    } catch (error) {
      message.error(error.message);
    } finally {
      setActionLoading("");
    }
  };

  const loadBranch = async (record) => {
    if (
      !record?.storage_uri ||
      !record?.root_storage_uri ||
      record.children_loaded ||
      record.has_children === false ||
      record.is_file
    ) {
      return;
    }

    setLoadingBranchKeys((current) => (current.includes(record.key) ? current : [...current, record.key]));
    setFolderTreeRows((current) =>
      updateNode(current, record.key, (node) => ({
        ...node,
        is_loading: true,
      }))
    );

    try {
      const result = await fetchOperationsFolderChildren({
        storageUri: record.storage_uri,
        rootStorageUri: record.root_storage_uri,
      });
      const children = (result.items || []).map((item) => ({
        ...item,
        key: item.storage_uri || item.path,
        children_loaded: !item.has_children,
        is_file: Boolean(item.is_file),
        is_loading: false,
        children: item.has_children ? [] : undefined,
      }));
      setFolderTreeRows((current) => replaceNodeChildren(current, record.key, children));
    } catch (error) {
      setFolderTreeRows((current) =>
        updateNode(current, record.key, (node) => ({
          ...node,
          is_loading: false,
        }))
      );
      message.error(error.message);
    } finally {
      setLoadingBranchKeys((current) => current.filter((key) => key !== record.key));
    }
  };

  const closeProviderModal = () => {
    setProviderModal(emptyProviderModal);
  };

  const openProviderModal = async (provider, sourceFolder = selectedFolder) => {
    if (!sourceFolder) return;

    setProviderModal({
      open: true,
      provider,
      source: sourceFolder.path,
      sourceLabel: sourceFolder.label,
      items: [],
      query: sourceFolder.label,
      selectedItemId: "",
      preview: null,
      loading: true,
    });

    try {
      const result = await fetchProviderItems(provider);
      const items = result.items || [];
      const bestMatch = [...items]
        .map((item) => ({ item, score: scoreProviderItem(item, sourceFolder.label) }))
        .sort((left, right) => right.score - left.score || String(left.item.title).localeCompare(String(right.item.title)))[0];

      setProviderModal((current) => ({
        ...current,
        items,
        selectedItemId: bestMatch?.score ? String(bestMatch.item.id) : "",
        loading: false,
      }));
    } catch (error) {
      setProviderModal((current) => ({ ...current, loading: false }));
      message.error(error.message);
    }
  };

  const handleRemoveRoots = async (paths) => {
    await runAction(
      "remove-root",
      async () => {
        for (const path of paths) {
          await removeRoot(path);
        }
      },
      paths.length === 1 ? "Connected folder removed." : `${paths.length} connected folders removed.`
    );
  };

  const handleDeleteFolders = async (paths) => {
    modal.confirm({
      title: paths.length === 1 ? "Delete this folder?" : `Delete ${paths.length} folders?`,
      content: paths.length === 1 ? paths[0] : "This action will delete the selected folders.",
      okText: "Delete",
      okButtonProps: { danger: true },
      onOk: async () => {
        await runAction(
          "delete-folder",
          async () => {
            for (const path of paths) {
              await deleteFolder(path);
            }
          },
          paths.length === 1 ? "Folder deleted." : `${paths.length} folders deleted.`
        );
      },
    });
  };

  const renderRowActions = (record) => (
    <Dropdown
      trigger={["click"]}
      menu={{
        items: [
          { key: "move-radarr", label: "Move To Radarr...", disabled: record.is_root || record.is_file || !payload.integrations?.radarr?.enabled },
          { key: "move-sonarr", label: "Move To Sonarr...", disabled: record.is_root || record.is_file || !payload.integrations?.sonarr?.enabled },
          { type: "divider" },
          { key: "remove-root", label: "Remove From App", disabled: !record.is_root },
          { key: "delete-folder", label: "Delete Folder...", danger: true, disabled: record.is_root || record.is_file },
        ],
        onClick: async ({ domEvent, key }) => {
          domEvent.stopPropagation();
          setSelectedNodeKeys(record.is_root || record.is_file ? [] : [record.key]);
          if (key === "move-radarr" || key === "move-sonarr") {
            await openProviderModal(key === "move-radarr" ? "radarr" : "sonarr", record);
            return;
          }
          if (key === "remove-root") {
            await handleRemoveRoots([record.path]);
            return;
          }
          if (key === "delete-folder") {
            await handleDeleteFolders([record.path]);
          }
        },
      }}
    >
      <Button
        size="small"
        icon={<MoreOutlined />}
        aria-label={`More actions for ${record.label}`}
        onClick={(event) => event.stopPropagation()}
      />
    </Dropdown>
  );

  const tableColumns = [
    {
      title: "Folder",
      dataIndex: "label",
      key: "folder",
      width: "42%",
      render: (_, record) => (
        <Flex vertical gap={6} style={{ minWidth: 0 }}>
          <Space size={[4, 4]} wrap>
            {record.is_loading ? <LoadingOutlined spin /> : null}
            {record.is_file ? <FileOutlined /> : null}
            <Text strong>{record.label}</Text>
            {record.priority ? (
              <Tag color="gold" bordered={false}>
                P{record.priority}
              </Tag>
            ) : null}
            {record.kind ? <Tag>{record.kind}</Tag> : null}
            {record.is_root ? <Tag color="blue">Root</Tag> : null}
            {record.is_file ? <Tag>File</Tag> : null}
          </Space>
        </Flex>
      ),
    },
    {
      title: "Path",
      dataIndex: "display_path",
      key: "path",
      width: "30%",
      render: (_, record) => (
        <Text type="secondary" className="mono">
          {compactDisplayPath(record)}
        </Text>
      ),
    },
    {
      title: "",
      key: "actions",
      width: 64,
      align: "right",
      render: (_, record) => renderRowActions(record),
    },
  ];

  const optionItems = [
    {
      key: "delete-lower-quality",
      title: "Delete lower-quality versions automatically when building plan",
      value: deleteLowerQuality,
      onChange: setDeleteLowerQuality,
    },
    {
      key: "prune-empty-dirs",
      title: "Prune empty folders after apply",
      value: pruneEmptyDirs,
      onChange: setPruneEmptyDirs,
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
      <Row gutter={[16, 16]} align="top">
        <Col xs={24} xl={17}>
          <Flex vertical gap={16}>
            <Card
              title={
                <Space>
                  <FolderOpenOutlined />
                  <span>Folder List</span>
                </Space>
              }
            >
              <Row gutter={[12, 12]} align="middle">
                <Col flex="auto">
                  <Space wrap>
                    <Button
                      type="primary"
                      disabled={!canMoveToRadarr}
                      loading={actionLoading === "move-to-provider" && providerModal.provider === "radarr"}
                      onClick={() => openProviderModal("radarr")}
                    >
                      Move To Radarr
                    </Button>
                    <Button
                      disabled={!canMoveToSonarr}
                      loading={actionLoading === "move-to-provider" && providerModal.provider === "sonarr"}
                      onClick={() => openProviderModal("sonarr")}
                    >
                      Move To Sonarr
                    </Button>
                    <Button
                      type="primary"
                      ghost
                      disabled={!duplicateScanSelection.length}
                      loading={actionLoading === "scan"}
                      onClick={() =>
                        runAction(
                          "scan",
                          () => runScan(duplicateScanSelection),
                          duplicateScanSelection.length === 1
                            ? "Duplicate detection finished for 1 folder."
                            : `Duplicate detection finished for ${duplicateScanSelection.length} folders.`
                        )
                      }
                    >
                      Detect Duplicates
                    </Button>
                    <Dropdown
                      trigger={["click"]}
                      menu={{
                        items: [
                          { key: "remove-root", label: "Remove From App", disabled: !selectedRootPaths.length },
                          { key: "delete-folder", label: "Delete Folder...", danger: true, disabled: !selectedPaths.length },
                        ],
                        onClick: async ({ key }) => {
                          if (key === "remove-root") {
                            await handleRemoveRoots(selectedRootPaths);
                            return;
                          }
                          if (key === "delete-folder") {
                            await handleDeleteFolders(selectedPaths);
                          }
                        },
                      }}
                    >
                      <Button disabled={!selectedRootPaths.length && !selectedPaths.length}>More</Button>
                    </Dropdown>
                    <Button
                      icon={<ReloadOutlined />}
                      loading={actionLoading === "refresh-folders"}
                      disabled={loadingBranchKeys.length > 0}
                      onClick={handleRefreshFolders}
                    >
                      Refresh
                    </Button>
                  </Space>
                </Col>
                <Col xs={24} lg={10} xl={8}>
                  <Input.Search
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Filter folders by name, path, source, or kind"
                    allowClear
                  />
                </Col>
              </Row>
              <Descriptions
                size="small"
                column={{ xs: 1, md: 3 }}
                style={{ marginTop: 16, marginBottom: 16 }}
                items={[
                  { key: "roots", label: "Roots", children: treeSummary.roots },
                  { key: "nodes", label: "Folders", children: treeSummary.nodes },
                  {
                    key: "selected",
                    label: "Selected",
                    children: `${duplicateScanSelection.length} folder${duplicateScanSelection.length === 1 ? "" : "s"}`,
                  },
                ]}
              />
              {filteredTableData.length ? (
                <Table
                  rowKey="key"
                  size="middle"
                  pagination={false}
                  columns={tableColumns}
                  dataSource={filteredTableData}
                  expandable={{
                    childrenColumnName: "children",
                    expandedRowKeys,
                    onExpand: async (expanded, record) => {
                      setExpandedRowKeys((current) =>
                        expanded ? [...new Set([...current, record.key])] : current.filter((key) => key !== record.key)
                      );
                      if (expanded) {
                        await loadBranch(record);
                      }
                    },
                    rowExpandable: (record) => record.has_children !== false,
                  }}
                  loading={loadingBranchKeys.length > 0 && !filteredTableData.length}
                  rowSelection={{
                    selectedRowKeys: selectedNodeKeys,
                    checkStrictly: true,
                    onChange: (keys) => setSelectedNodeKeys(keys),
                    getCheckboxProps: (record) => ({ disabled: record.is_file }),
                  }}
                  locale={{
                    emptyText: search
                      ? "No folders match the current filter."
                      : "No connected folders yet. Add one from Settings.",
                  }}
                />
              ) : (
                <Empty description={search ? "No folders match the current filter." : "No connected folders yet. Add one from Settings."} />
              )}
            </Card>

            <Card
              title={
                <Space>
                  <PlayCircleOutlined />
                  <span>Duplicate Detection</span>
                </Space>
              }
              extra={
                <Space wrap>
                  <Button
                    loading={actionLoading === "plan"}
                    onClick={() => runAction("plan", () => buildPlan(deleteLowerQuality), "Plan created.")}
                  >
                    Build Plan
                  </Button>
                  <Button
                    loading={actionLoading === "dry-run"}
                    onClick={() => runAction("dry-run", () => applyPlan({ execute: false, pruneEmptyDirs }), "Dry run completed.")}
                  >
                    Dry Run Apply
                  </Button>
                  <Button
                    danger
                    loading={actionLoading === "execute"}
                    onClick={() =>
                      modal.confirm({
                        title: "Execute the current plan on real files?",
                        okText: "Execute",
                        okButtonProps: { danger: true },
                        onOk: () =>
                          runAction(
                            "execute",
                            () => applyPlan({ execute: true, pruneEmptyDirs }),
                            "Plan executed."
                          ),
                      })
                    }
                  >
                    Execute Apply
                  </Button>
                </Space>
              }
            >
              <Row gutter={[16, 16]}>
                <Col xs={24} sm={12} xl={6}>
                  <Card size="small">
                    <Statistic title="Files Indexed" value={operationsSummary.files || 0} />
                  </Card>
                </Col>
                <Col xs={24} sm={12} xl={6}>
                  <Card size="small">
                    <Statistic title="Exact Groups" value={operationsSummary.exact_duplicate_groups || 0} />
                  </Card>
                </Col>
                <Col xs={24} sm={12} xl={6}>
                  <Card size="small">
                    <Statistic title="Collision Groups" value={operationsSummary.media_collision_groups || 0} />
                  </Card>
                </Col>
                <Col xs={24} sm={12} xl={6}>
                  <Card size="small">
                    <Statistic
                      title="Plan Actions"
                      value={(planSummary.move || 0) + (planSummary.delete || 0) + (planSummary.review || 0)}
                    />
                  </Card>
                </Col>
              </Row>

              <List
                itemLayout="horizontal"
                dataSource={optionItems}
                renderItem={(item) => (
                  <List.Item actions={[<Switch key={item.key} checked={item.value} onChange={item.onChange} />]}>
                    <List.Item.Meta title={item.title} />
                  </List.Item>
                )}
              />
              <Alert
                style={{ marginTop: 16 }}
                type="info"
                showIcon
                message="Duplicate detection runs on the folders currently selected in Folder List."
              />
            </Card>

            <Row gutter={[16, 16]}>
              <Col xs={24} xl={12}>
                <Card title="Exact Duplicates" extra={<Tag>{exactDuplicates.length}</Tag>}>
                  {exactDuplicates.length ? (
                    <List
                      itemLayout="horizontal"
                      dataSource={exactDuplicates.slice(0, 20)}
                      renderItem={(group) => (
                        <List.Item>
                          <List.Item.Meta
                            title={`${formatBytes(group.size)} • ${group.items.length} copies`}
                            description={group.items.map((item) => item.path).join(" • ")}
                          />
                        </List.Item>
                      )}
                    />
                  ) : (
                    <Empty description="No exact duplicate groups yet." />
                  )}
                </Card>
              </Col>
              <Col xs={24} xl={12}>
                <Card title="Media Collisions" extra={<Tag>{collisions.length}</Tag>}>
                  {collisions.length ? (
                    <List
                      itemLayout="horizontal"
                      dataSource={collisions.slice(0, 20)}
                      renderItem={(group) => (
                        <List.Item>
                          <List.Item.Meta
                            title={group.canonical_name}
                            description={group.items.map((item) => `${item.path} (Q${item.quality_rank})`).join(" • ")}
                          />
                        </List.Item>
                      )}
                    />
                  ) : (
                    <Empty description="No collision groups yet." />
                  )}
                </Card>
              </Col>
            </Row>

            <Row gutter={[16, 16]}>
              <Col xs={24} xl={12}>
                <Card title="Action Plan" extra={<Tag>{planActions.length}</Tag>}>
                  {planActions.length ? (
                    <List
                      itemLayout="horizontal"
                      dataSource={planActions.slice(0, 50)}
                      renderItem={(action) => (
                        <List.Item>
                          <List.Item.Meta
                            title={`${String(action.type || "").toUpperCase()} • ${action.reason}`}
                            description={[action.source, action.destination, action.keep_path].filter(Boolean).join(" • ")}
                          />
                        </List.Item>
                      )}
                    />
                  ) : (
                    <Empty description="No action plan yet." />
                  )}
                </Card>
              </Col>
              <Col xs={24} xl={12}>
                <Card title="Apply Result" extra={<Tag>{applyResult?.mode || "No run"}</Tag>}>
                  {applyResult ? (
                    <List
                      itemLayout="horizontal"
                      dataSource={[
                        `Applied: ${applyResult.summary?.applied || 0}`,
                        `Dry Run: ${applyResult.summary?.["dry-run"] || 0}`,
                        `Skipped: ${applyResult.summary?.skipped || 0}`,
                        `Errors: ${applyResult.summary?.error || 0}`,
                      ]}
                      renderItem={(item) => <List.Item>{item}</List.Item>}
                    />
                  ) : (
                    <Empty description="No apply result yet." />
                  )}
                </Card>
              </Col>
            </Row>
          </Flex>
        </Col>

        <Col xs={24} xl={7}>
          <Flex vertical gap={16}>
            <Card
              title={
                <Space>
                  <SyncOutlined />
                  <span>Process Logs</span>
                </Space>
              }
            >
              {currentJob ? (
                <Flex vertical gap={16}>
                  <Card size="small">
                    <Flex vertical gap={12}>
                      <Space wrap>
                        <StatusTag value={currentJob.status || "running"} />
                        <Tag>{currentJob.kind || "process"}</Tag>
                      </Space>
                      <Text strong>{currentJob.message}</Text>
                      <Text type="secondary">Started {formatDate(currentJob.started_at)}</Text>
                    </Flex>
                  </Card>
                  <List
                    itemLayout="horizontal"
                    dataSource={(currentJob.logs || []).slice().reverse()}
                    renderItem={(entry) => (
                      <List.Item>
                        <List.Item.Meta
                          title={
                            <Space>
                              <StatusTag value={entry.level} />
                              <span>{entry.message}</span>
                            </Space>
                          }
                          description={formatDate(entry.ts)}
                        />
                      </List.Item>
                    )}
                  />
                </Flex>
              ) : (
                <Empty description="No active process right now." />
              )}
            </Card>

            <Card title="Recent Activity">
              {recentActivity.length ? (
                <List
                  itemLayout="horizontal"
                  dataSource={recentActivity}
                  renderItem={(entry) => (
                    <List.Item>
                      <List.Item.Meta
                        title={
                          <Space>
                            <StatusTag value={entry.status} />
                            <span>{entry.message}</span>
                          </Space>
                        }
                        description={`${entry.kind} • ${formatDate(entry.created_at)}`}
                      />
                    </List.Item>
                  )}
                />
              ) : (
                <Empty description="No activity yet." />
              )}
            </Card>
          </Flex>
        </Col>
      </Row>

      <ProviderMoveModal
        modalState={providerModal}
        rankedItems={rankedProviderItems}
        selectedItem={selectedProviderItem}
        suggestedItem={suggestedProviderItem}
        actionLoading={actionLoading}
        onCancel={closeProviderModal}
        onQueryChange={(query) => setProviderModal((current) => ({ ...current, query, preview: null }))}
        onSelectItem={(value) => setProviderModal((current) => ({ ...current, selectedItemId: value, preview: null }))}
        onPreview={async () => {
          if (!selectedProviderItem) return;
          const result = await runAction(
            "preview-provider-move",
            () =>
              previewMoveToProvider({
                provider: providerModal.provider,
                source: providerModal.source,
                item_id: selectedProviderItem.id,
                destination: selectedProviderItem.path,
              }),
            "Preview ready."
          );
          if (!result) return;
          setProviderModal((current) => ({ ...current, preview: result }));
        }}
        onConfirm={async () => {
          if (!selectedProviderItem) return;
          const result = await runAction(
            "move-to-provider",
            () =>
              executeMoveToProvider({
                provider: providerModal.provider,
                source: providerModal.source,
                item_id: selectedProviderItem.id,
                destination: selectedProviderItem.path,
              }),
            "Folder moved into provider path."
          );
          if (result) closeProviderModal();
        }}
      />
    </Flex>
  );
}
