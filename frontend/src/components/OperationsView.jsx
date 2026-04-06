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
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  FileOutlined,
  FolderOpenOutlined,
  LoadingOutlined,
  MoreOutlined,
  ReloadOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import {
  applyPlan,
  buildPlan,
  cancelCurrentProcess,
  deleteFolder,
  executeMoveToProvider,
  fetchOperationsData,
  fetchCurrentProcess,
  fetchOperationsFolderChildren,
  fetchProviderItems,
  previewMoveToProvider,
  removeRoot,
  runOperationsFolderCleanupDelete,
  runOperationsFolderCleanupScan,
  runScan,
} from "../api";
import { MediaLibraryLogPanel } from "./MediaLibraryLogPanel";

const { Text } = Typography;
const EMPTY_REPORT = {};

const emptyState = {
  roots: [],
  integrations: {
    radarr: { enabled: false },
    sonarr: { enabled: false },
  },
  report: null,
  plan: null,
  apply_result: null,
  empty_folder_cleanup_report: null,
  activity_log: [],
  current_job: null,
  last_scan_at: null,
  last_plan_at: null,
  last_apply_at: null,
  last_empty_folder_cleanup_at: null,
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

function normalizeCleanupErrorMessage(value) {
  const message = String(value || "").trim();
  if (!message) return "Unknown error.";
  if (message.startsWith("[") && message.includes('"Path"') && message.includes('"Name"')) {
    return "The storage backend returned a raw directory listing instead of a readable error. Re-run the scan after restarting the backend.";
  }
  return message;
}

function isRateLimitedCleanupError(value) {
  const message = String(value || "").toLowerCase();
  return message.includes("rate_limit_exceeded") || message.includes("ratelimitexceeded") || message.includes("quota exceeded");
}

function normalizeSearchText(value) {
  return String(value || "")
    .toLowerCase()
    .replaceAll(/[\._()-]+/g, " ")
    .replaceAll(/\s+/g, " ")
    .trim();
}

function stripPriorityLabel(value) {
  return String(value || "").replace(/\s+P\d+$/, "").trim();
}

function compactDisplayPath(record) {
  if (record.is_root) {
    return stripPriorityLabel(record.path);
  }

  const display = stripPriorityLabel(record.display_path || record.path || "");
  const rootLabel = stripPriorityLabel(record.root_label || "");

  if (!display) {
    return "-";
  }

  if (display === record.label) {
    return rootLabel ? `${rootLabel} / ${record.label}` : record.label;
  }

  return display;
}

function rootSourceMeta(record) {
  const storageUri = String(record?.root_storage_uri || record?.storage_uri || "").toLowerCase();
  if (storageUri.startsWith("smb://")) return { label: "SMB", color: "geekblue" };
  if (storageUri.startsWith("rclone://")) return { label: "Rclone", color: "purple" };
  return { label: "Local", color: "default" };
}

function summarizeLabels(items, limit = 3) {
  const labels = items.map((item) => stripPriorityLabel(item?.folder_name || item?.canonical_name || item?.label || item?.path || "")).filter(Boolean);
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

function cleanupFolderStatusMeta(item) {
  if (item?.empty_reason === "inferior-video-set") return { color: "volcano", label: "Inferior Episode Set" };
  if (item?.empty_reason === "empty") return { color: "default", label: "Empty Directory" };
  if (item?.empty_reason === "sidecar-only") return { color: "warning", label: "Sidecar Only" };
  if (item?.has_video) return { color: "success", label: "Has Video" };
  return { color: "warning", label: "No Video" };
}

function buildCleanupRootErrorMap(errors, roots = [], connections = []) {
  const activeConnectionIds = new Set((connections || []).map((item) => String(item?.id || "").trim()).filter(Boolean));
  const activeRootPaths = new Set((roots || []).map((item) => String(item?.path || "").trim()).filter(Boolean));
  return (errors || []).reduce((map, item) => {
    const key = String(item?.root_path || item?.root_label || "").trim();
    if (!key) return map;
    const message = normalizeCleanupErrorMessage(item?.message);
    const connectionId = String(item?.connection_id || "").trim();
    const staleConnectionError =
      message.startsWith("connection not found:")
      && ((connectionId && activeConnectionIds.has(connectionId)) || activeRootPaths.has(key));
    if (staleConnectionError) return map;
    map.set(key, {
      rootLabel: item?.root_label || item?.root_path || "Unknown root",
      message,
      isRateLimited: isRateLimitedCleanupError(item?.message),
    });
    return map;
  }, new Map());
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

function getReadableActionTypeLabel(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "move") return "Move";
  if (normalized === "delete") return "Delete";
  if (normalized === "review") return "Check";
  return value || "Action";
}

function humanizeActionReason(value) {
  return String(value || "unknown_action").replaceAll("_", " ");
}

function decodePathPreview(value) {
  const raw = String(value || "");
  if (!raw) return "";
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

function formatActionHeadline(action) {
  const canonicalName = String(action?.details?.canonical_name || "").trim();
  if (canonicalName) {
    return canonicalName;
  }
  const preferredPath = decodePathPreview(action?.keep_path || action?.destination || action?.source || "");
  const withoutQuery = preferredPath.split("?")[0];
  const segments = withoutQuery.split("/").filter(Boolean);
  return segments[segments.length - 1] || preferredPath || "Upcoming change";
}

function buildPlanPreviewLines(action) {
  const rows = [];

  if (action.source) {
    rows.push({
      key: `source-${action.source}`,
      tone: "remove",
      sign: "-",
      label: action.type === "move" ? "from" : action.type === "delete" ? "remove" : "check",
      path: decodePathPreview(action.source),
    });
  }

  if (action.destination) {
    rows.push({
      key: `destination-${action.destination}`,
      tone: "add",
      sign: "+",
      label: action.type === "review" ? "suggested folder" : "to",
      path: decodePathPreview(action.destination),
    });
  }

  if (action.keep_path && action.keep_path !== action.destination) {
    rows.push({
      key: `keep-${action.keep_path}`,
      tone: "keep",
      sign: "+",
      label: "keep",
      path: decodePathPreview(action.keep_path),
    });
  }

  return rows;
}

function isRealApplyMode(value) {
  return ["apply", "execute"].includes(String(value || "").toLowerCase());
}

function getPendingPlan(plan, applyResult, lastPlanAt, lastApplyAt) {
  if (!plan) return null;
  if (!applyResult || !isRealApplyMode(applyResult.mode)) return plan;

  const appliedPlanGeneratedAt = String(applyResult.plan_generated_at || "").trim();
  const planGeneratedAt = String(plan.generated_at || "").trim();
  if (appliedPlanGeneratedAt && planGeneratedAt) {
    return appliedPlanGeneratedAt === planGeneratedAt ? null : plan;
  }

  const planTime = Date.parse(planGeneratedAt || lastPlanAt || "") || 0;
  const applyTime = Date.parse(applyResult.generated_at || lastApplyAt || "") || 0;
  if (planTime && applyTime && applyTime >= planTime) {
    return null;
  }

  return plan;
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
            label: `${item.title}${item.year ? ` (${item.year})` : ""}`,
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

function PlanReviewModal({
  open,
  plan,
  deleteLowerQuality,
  pruneEmptyDirs,
  actionLoading,
  onClose,
  onDeleteLowerQualityChange,
  onPruneEmptyDirsChange,
  onDryRun,
  onExecute,
}) {
  const summary = plan?.summary || {};
  const actions = plan?.actions || [];

  return (
    <Modal
      open={open}
      title="Preview Changes"
      onCancel={onClose}
      footer={null}
      width={960}
    >
      <Flex vertical gap={16}>
        <Alert
          type="info"
          showIcon
          message="Check what will happen before the app changes any files."
          description="Preview only shows what would change. Apply Changes makes the real file updates."
        />

        <Descriptions
          bordered
          size="small"
          column={{ xs: 1, md: 2 }}
          items={[
            { key: "move", label: "Move", children: Number(summary.move || 0) },
            { key: "delete", label: "Delete", children: Number(summary.delete || 0) },
            { key: "review", label: "Check manually", children: Number(summary.review || 0) },
            { key: "generated", label: "Created", children: formatDate(plan?.generated_at) },
          ]}
        />

        <List
          itemLayout="horizontal"
          dataSource={[
            {
              key: "delete-lower-quality",
              title: "Delete lower-quality versions automatically when building plan",
              value: deleteLowerQuality,
              onChange: onDeleteLowerQualityChange,
            },
            {
              key: "prune-empty-dirs",
              title: "Remove empty folders after changes are applied",
              value: pruneEmptyDirs,
              onChange: onPruneEmptyDirsChange,
            },
          ]}
          renderItem={(item) => (
            <List.Item actions={[<Switch key={item.key} checked={item.value} onChange={item.onChange} />]}>
              <List.Item.Meta title={item.title} />
            </List.Item>
          )}
        />

        {actions.length ? (
          <div className="plan-review-list">
            <Flex justify="space-between" align="center" gap={12} wrap className="plan-review-list-head">
              <Text strong>Upcoming changes</Text>
              <Tag>{actions.length} items</Tag>
            </Flex>
            <div className="plan-review-viewport">
              <Flex vertical gap={10}>
                {actions.slice(0, 80).map((action, index) => (
                  <div key={`${action.type}-${action.reason}-${index}`} className="plan-review-entry">
                    <div className="plan-review-entry-head">
                      <Space wrap size={[8, 8]}>
                        <Tag color={action.type === "delete" ? "error" : action.type === "review" ? "warning" : "processing"}>
                          {getReadableActionTypeLabel(action.type)}
                        </Tag>
                        <Text strong>{humanizeActionReason(action.reason)}</Text>
                        {action.details?.kind ? <Tag>{String(action.details.kind).toUpperCase()}</Tag> : null}
                        {Number.isFinite(Number(action.details?.candidate_quality_rank)) ? (
                          <Tag>Candidate Q{Number(action.details?.candidate_quality_rank)}</Tag>
                        ) : null}
                        {Number.isFinite(Number(action.details?.keeper_quality_rank)) ? (
                          <Tag color="success">Keep Q{Number(action.details?.keeper_quality_rank)}</Tag>
                        ) : null}
                      </Space>
                      <Text className="plan-review-entry-title">{formatActionHeadline(action)}</Text>
                    </div>
                    <div className="plan-review-diff">
                      {buildPlanPreviewLines(action).map((row) => (
                        <div key={row.key} className={`plan-review-diff-line tone-${row.tone}`}>
                          <Text className={`plan-review-diff-sign tone-${row.tone}`}>{row.sign}</Text>
                          <Text className="plan-review-diff-label">{row.label}</Text>
                          <Text className="plan-review-diff-path">{row.path}</Text>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </Flex>
            </div>
          </div>
        ) : (
          <Empty description="There are no changes to make right now." />
        )}

        <Flex justify="space-between" align="center" gap={12} wrap>
          <Text type="secondary">After you start, progress continues in Process Logs.</Text>
          <Space wrap>
            <Button onClick={onClose}>Close</Button>
            <Button loading={actionLoading === "dry-run"} onClick={onDryRun}>
              Preview Only
            </Button>
            <Button danger loading={actionLoading === "execute"} onClick={onExecute}>
              Apply Changes
            </Button>
          </Space>
        </Flex>
      </Flex>
    </Modal>
  );
}

function DuplicateFolderCleanupModal({
  open,
  report,
  selectedRootCount,
  selectedGroups,
  selectedGroupIds,
  selectedGroupSummary,
  cleanupFolderRows,
  cleanupDeleteRows,
  cleanupGroupColumns,
  cleanupFolderColumns,
  selectedCleanupFolderKeys,
  actionLoading,
  onClose,
  onSelectGroups,
  onSelectFolders,
  onToggleGroup,
  onToggleFolder,
  onClearSelection,
  onDelete,
}) {
  const summary = report?.summary || {};
  const groups = report?.groups || [];

  return (
    <Modal
      open={open}
      title="Review Duplicate Folder Cleanup"
      onCancel={onClose}
      footer={null}
      width={1080}
    >
      <Flex vertical gap={16}>
        <Alert
          type="info"
          showIcon
          message="Review duplicate folder groups before removing anything."
          description="Select the duplicate groups to inspect, then delete only the candidate folders you want to remove."
        />

        <Descriptions
          bordered
          size="small"
          column={{ xs: 1, md: 2 }}
          items={[
            { key: "generated", label: "Latest Scan", children: formatDate(report?.generated_at) },
            { key: "selected-roots", label: "Selected Roots", children: selectedRootCount },
            { key: "groups", label: "Groups", children: Number(summary.duplicate_groups || 0) },
            { key: "candidates", label: "Candidates", children: Number(summary.deletion_candidates || 0) },
          ]}
        />

        <div className="plan-review-list">
          <Flex justify="space-between" align="center" gap={12} wrap className="plan-review-list-head">
            <Space wrap>
              <Text strong>Duplicate groups</Text>
              <Tag>{groups.length} items</Tag>
            </Space>
          </Flex>
          <Table
            size="small"
            rowKey={(group) => String(group.id)}
            pagination={{ pageSize: 8 }}
            dataSource={groups}
            rowSelection={{
              selectedRowKeys: selectedGroupIds,
              onChange: (keys) => onSelectGroups(keys.map(String)),
            }}
            locale={{
              emptyText: report?.generated_at
                ? "No duplicate folder groups found in the latest selected-root scan."
                : "Run a duplicate folder scan to review cleanup candidates.",
            }}
            columns={cleanupGroupColumns}
            onRow={(group) => ({
              onClick: (event) => {
                if (event.target.closest("button")) return;
                onToggleGroup(group.id);
              },
            })}
          />
        </div>

        {selectedGroups.length ? (
          <div className="plan-review-list">
            <Flex justify="space-between" align="center" gap={12} wrap className="plan-review-list-head">
              <Space wrap>
                <Text strong>Selected duplicate copies</Text>
                <Tag>{selectedGroupSummary}</Tag>
                <Tag>{cleanupFolderRows.length} copies</Tag>
                <Tag>{cleanupDeleteRows.length} delete candidate{cleanupDeleteRows.length === 1 ? "" : "s"}</Tag>
              </Space>
              <Button onClick={onClearSelection}>Clear Selection</Button>
            </Flex>
            <Table
              size="small"
              rowKey="rowKey"
              dataSource={cleanupFolderRows}
              pagination={{ pageSize: 12 }}
              rowSelection={{
                selectedRowKeys: selectedCleanupFolderKeys,
                onChange: (keys) => onSelectFolders(keys.map(String)),
                getCheckboxProps: (item) => ({
                  disabled: !item.is_deletion_candidate,
                }),
              }}
              columns={cleanupFolderColumns}
              onRow={(item) => ({
                onClick: (event) => {
                  if (event.target.closest("button")) return;
                  onToggleFolder(item.rowKey);
                },
              })}
            />
          </div>
        ) : null}

        <Flex justify="space-between" align="center" gap={12} wrap>
          <Text type="secondary">Progress continues in Process Logs after deletion starts.</Text>
          <Space wrap>
            <Button onClick={onClose}>Close</Button>
            <Button
              danger
              disabled={!cleanupDeleteRows.length}
              loading={actionLoading === "delete-folder-cleanup"}
              onClick={onDelete}
            >
              Delete Selected Candidates
            </Button>
          </Space>
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
  const [planReviewOpen, setPlanReviewOpen] = useState(false);
  const [cleanupReviewOpen, setCleanupReviewOpen] = useState(false);
  const [processPollingEnabled, setProcessPollingEnabled] = useState(false);
  const [selectedCleanupGroupIds, setSelectedCleanupGroupIds] = useState([]);
  const [selectedCleanupFolderKeys, setSelectedCleanupFolderKeys] = useState([]);

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

  useEffect(() => {
    if (!processPollingEnabled && currentJob?.status !== "running") {
      return undefined;
    }

    let cancelled = false;
    const poll = async () => {
      try {
        const process = await fetchCurrentProcess();
        if (cancelled) return;
        const nextJob = process.current_job || null;
        setCurrentJob(nextJob);
        if (nextJob && nextJob.status !== "running" && !processPollingEnabled) {
          await refreshAll();
        }
      } catch (error) {
        if (!cancelled) {
          console.error(error);
        }
      }
    };

    void poll();
    const timerId = window.setInterval(poll, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(timerId);
    };
  }, [currentJob?.id, currentJob?.status, processPollingEnabled]);

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
  const activePlan = useMemo(
    () => getPendingPlan(payload.plan, payload.apply_result, payload.last_plan_at, payload.last_apply_at),
    [payload.plan, payload.apply_result, payload.last_plan_at, payload.last_apply_at]
  );
  const planActions = activePlan?.actions || [];
  const folderCleanupReport = payload.empty_folder_cleanup_report || EMPTY_REPORT;
  const folderCleanupGroups = useMemo(() => folderCleanupReport.groups || [], [folderCleanupReport]);
  const folderCleanupErrors = folderCleanupReport.errors || [];
  const cleanupRootErrors = useMemo(
    () => buildCleanupRootErrorMap(folderCleanupErrors, payload.roots || [], payload.lan_connections?.smb || []),
    [folderCleanupErrors, payload.roots, payload.lan_connections]
  );
  const rateLimitedCleanupRoots = useMemo(
    () => [...cleanupRootErrors.values()].filter((item) => item.isRateLimited),
    [cleanupRootErrors]
  );
  const selectedCleanupGroups = useMemo(
    () => folderCleanupGroups.filter((group) => selectedCleanupGroupIds.includes(String(group.id))),
    [folderCleanupGroups, selectedCleanupGroupIds]
  );
  const selectedCleanupGroupSummary = useMemo(() => summarizeLabels(selectedCleanupGroups), [selectedCleanupGroups]);
  const cleanupFolderRows = useMemo(
    () =>
      selectedCleanupGroups.flatMap((group) =>
        (group.items || []).map((item) => ({
          ...item,
          groupId: String(group.id),
          groupFolderName: group.folder_name || group.relative_path || group.canonical_name,
          rowKey: `${group.id}:${item.delete_path || item.storage_uri || item.path || item.root_path || item.root_label}`,
        }))
      ),
    [selectedCleanupGroups]
  );
  const cleanupDeleteRows = useMemo(
    () => cleanupFolderRows.filter((item) => selectedCleanupFolderKeys.includes(item.rowKey) && item.is_deletion_candidate),
    [cleanupFolderRows, selectedCleanupFolderKeys]
  );

  useEffect(() => {
    const validGroupIds = new Set(folderCleanupGroups.map((group) => String(group.id)));
    setSelectedCleanupGroupIds((current) => {
      const next = current.filter((id) => validGroupIds.has(String(id)));
      return sameStringArray(current, next) ? current : next;
    });
  }, [folderCleanupGroups]);

  useEffect(() => {
    const validKeys = new Set(cleanupFolderRows.map((item) => item.rowKey));
    setSelectedCleanupFolderKeys((current) => {
      const next = current.filter((key) => validKeys.has(String(key)));
      return sameStringArray(current, next) ? current : next;
    });
  }, [cleanupFolderRows]);

  useEffect(() => {
    if (!selectedCleanupGroupIds.length) return;
    const autoSelected = cleanupFolderRows.filter((item) => item.is_deletion_candidate).map((item) => item.rowKey);
    setSelectedCleanupFolderKeys((current) => {
      const merged = [...new Set([...current, ...autoSelected])];
      return sameStringArray(current, merged) ? current : merged;
    });
  }, [cleanupFolderRows, selectedCleanupGroupIds.length]);

  const runAction = async (actionKey, action, successMessage, options = {}) => {
    const { trackProcess = false } = options;
    setActionLoading(actionKey);
    if (trackProcess) {
      setProcessPollingEnabled(true);
      fetchCurrentProcess()
        .then((process) => setCurrentJob(process.current_job || null))
        .catch((error) => console.error(error));
    }
    try {
      const result = await action();
      await refreshAll();
      if (successMessage) message.success(successMessage);
      return result;
    } catch (error) {
      try {
        await refreshAll();
      } catch (refreshError) {
        console.error(refreshError);
      }
      message.error(error.message);
      return null;
    } finally {
      if (trackProcess) {
        setProcessPollingEnabled(false);
      }
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

  const handleDetectDuplicates = async () => {
    if (!duplicateScanSelection.length) return;

    const scanResult = await runAction(
      "scan",
      () => runScan(duplicateScanSelection),
      duplicateScanSelection.length === 1
        ? "Duplicate detection finished for 1 folder."
        : `Duplicate detection finished for ${duplicateScanSelection.length} folders.`,
      { trackProcess: true }
    );
    if (!scanResult) return;

    const planResult = await runAction("plan", () => buildPlan(deleteLowerQuality), "Change preview is ready.", {
      trackProcess: true,
    });
    if (planResult) {
      setPlanReviewOpen(true);
    }
  };

  const handleScanDuplicateFolders = async () => {
    if (duplicateScanSelection.length < 2) {
      message.warning("Select at least two folders or roots to compare.");
      return;
    }
    const scanResult = await runAction(
      "scan-folder-cleanup",
      () => runOperationsFolderCleanupScan(duplicateScanSelection),
      "Duplicate library folder scan completed.",
      { trackProcess: true }
    );
    if (!scanResult) return;
    setCleanupReviewOpen(true);
  };

  const handleDeleteDuplicateFolders = async () => {
    if (!cleanupDeleteRows.length) return;
    await runAction(
      "delete-folder-cleanup",
      () =>
        runOperationsFolderCleanupDelete(
          cleanupDeleteRows.map((item) => ({
            path: item.path,
            delete_path: item.delete_path || item.path,
            root_label: item.root_label,
            group_id: item.groupId,
            empty_reason: item.empty_reason,
          }))
        ),
      cleanupDeleteRows.length === 1 ? "Duplicate folder deleted." : `${cleanupDeleteRows.length} duplicate folders deleted.`,
      { trackProcess: true }
    );
    setSelectedCleanupFolderKeys([]);
  };

  const toggleCleanupGroupSelection = (groupId) => {
    const key = String(groupId);
    setSelectedCleanupGroupIds((current) => (current.includes(key) ? current.filter((item) => item !== key) : [...current, key]));
  };

  const toggleCleanupFolderSelection = (rowKey) => {
    const key = String(rowKey);
    const row = cleanupFolderRows.find((item) => item.rowKey === key);
    if (!row || !row.is_deletion_candidate) return;
    setSelectedCleanupFolderKeys((current) => (current.includes(key) ? current.filter((item) => item !== key) : [...current, key]));
  };

  const handleCancelCurrentJob = async () => {
    if (!currentJob || currentJob.status !== "running") return;
    setActionLoading("cancel-job");
    try {
      const result = await cancelCurrentProcess();
      setCurrentJob(result.current_job || null);
      await refreshAll();
      message.success("Stop request sent. Waiting for the current step to end safely.");
    } catch (error) {
      message.error(error.message);
    } finally {
      setActionLoading("");
    }
  };

  const handleDryRunFromReview = async () => {
    setPlanReviewOpen(false);
    await runAction("dry-run", () => applyPlan({ execute: false, pruneEmptyDirs }), "Preview finished.", {
      trackProcess: true,
    });
  };

  const handleExecuteFromReview = async () => {
    modal.confirm({
      title: "Apply these changes to your real files now?",
      okText: "Apply Changes",
      okButtonProps: { danger: true },
      onOk: async () => {
        setPlanReviewOpen(false);
        await runAction("execute", () => applyPlan({ execute: true, pruneEmptyDirs }), "Changes applied.", {
          trackProcess: true,
        });
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
      render: (_, record) => (
        <div className="operations-folder-cell">
          <Space size={[4, 4]} wrap className="operations-folder-title">
            {record.is_loading ? <LoadingOutlined spin className="operations-folder-leading-icon" /> : null}
            {record.is_file ? <FileOutlined className="operations-folder-leading-icon" /> : null}
            <Text strong className="operations-folder-name">{stripPriorityLabel(record.label)}</Text>
            {record.kind ? <Tag>{record.kind}</Tag> : null}
            {record.is_root ? <Tag color={rootSourceMeta(record).color}>{rootSourceMeta(record).label}</Tag> : null}
            {record.is_file ? <Tag>File</Tag> : null}
            {record.is_root && cleanupRootErrors.get(record.path)?.isRateLimited ? <Tag color="error">Rate Limited</Tag> : null}
            {record.is_root && cleanupRootErrors.get(record.path) && !cleanupRootErrors.get(record.path)?.isRateLimited ? (
              <Tag color="warning">Scan Issue</Tag>
            ) : null}
          </Space>
          {record.is_root && cleanupRootErrors.get(record.path)?.message ? (
            <Text type="secondary" className="operations-folder-note">{cleanupRootErrors.get(record.path).message}</Text>
          ) : null}
        </div>
      ),
    },
    {
      title: "Path",
      dataIndex: "display_path",
      key: "path",
      width: "45%",
      render: (_, record) => (
        <Text type="secondary" className="mono">
          {compactDisplayPath(record)}
        </Text>
      ),
    },
    {
      title: "",
      key: "actions",
      width: 48,
      align: "right",
      render: (_, record) => renderRowActions(record),
    },
  ];

  const cleanupGroupColumns = [
    {
      title: "Folder",
      key: "folder",
      render: (_value, group) => (
        <Flex vertical gap={4}>
          <Space wrap>
            <Text strong>{stripPriorityLabel(group.folder_name || group.relative_path)}</Text>
            <Tag>{(group.items || []).length} copies</Tag>
            {Number(group.deletion_candidate_count || 0) ? <Tag color="warning">{group.deletion_candidate_count} candidate</Tag> : null}
          </Space>
          {group.relative_path ? <Text type="secondary">{stripPriorityLabel(group.relative_path)}</Text> : null}
          <Text type="secondary">{summarizeLabels(group.items || [])}</Text>
        </Flex>
      ),
    },
    {
      title: "Roots",
      key: "roots",
      width: 240,
      render: (_value, group) => (
        <Space wrap>
          {[...new Set((group.items || []).map((item) => stripPriorityLabel(item.root_label)).filter(Boolean))].map((label) => (
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
        <Button size="small" onClick={() => setSelectedCleanupGroupIds([String(group.id)])}>
          Only This
        </Button>
      ),
    },
  ];

  const cleanupFolderColumns = [
    {
      title: "Folder",
      key: "folder",
      render: (_value, item) => (
        <Flex vertical gap={4}>
          <Space wrap>
            <Text strong>{stripPriorityLabel(String(item.path || "").split("/").pop() || item.groupFolderName)}</Text>
            <Tag color={cleanupFolderStatusMeta(item).color}>{cleanupFolderStatusMeta(item).label}</Tag>
            {item.is_deletion_candidate ? <Tag color="warning">Delete Candidate</Tag> : <Tag color="success">Keep</Tag>}
          </Space>
          <Text type="secondary" className="mono">
            {stripPriorityLabel(item.path)}
          </Text>
        </Flex>
      ),
    },
    {
      title: "Details",
      key: "details",
      width: 240,
      render: (_value, item) => (
        <Space wrap>
          {item.root_kind ? <Tag>{String(item.root_kind).toUpperCase()}</Tag> : null}
          {item.empty_reason ? <Tag>{item.empty_reason}</Tag> : null}
          {item.missing_episode_count ? <Tag color="volcano">missing {item.missing_episode_count}</Tag> : null}
        </Space>
      ),
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
              <Tooltip title="Scan selected folders for duplicate media/files and build a cleanup plan for preview or apply.">
                <span>
                  <Button
                    type="primary"
                    ghost
                    disabled={!duplicateScanSelection.length}
                    loading={actionLoading === "scan" || actionLoading === "plan"}
                    onClick={handleDetectDuplicates}
                  >
                    Plan Media Cleanup
                  </Button>
                </span>
              </Tooltip>
              <Tooltip title="Compare selected roots/folders to find duplicate folder groups across local, SMB, and rclone storage.">
                <span>
                  <Button
                    type="primary"
                    ghost
                    disabled={duplicateScanSelection.length < 2}
                    loading={actionLoading === "scan-folder-cleanup" || actionLoading === "delete-folder-cleanup"}
                    onClick={handleScanDuplicateFolders}
                  >
                    Find Duplicate Folders
                  </Button>
                </span>
              </Tooltip>
              {folderCleanupGroups.length ? <Button onClick={() => setCleanupReviewOpen(true)}>Review Folder Cleanup</Button> : null}
              {planActions.length ? <Button onClick={() => setPlanReviewOpen(true)}>Preview Changes</Button> : null}
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
            <Input
              className="folder-list-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Filter folders by name, path, source, or kind"
              allowClear
              prefix={<SearchOutlined />}
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
            {
              key: "cleanup-groups",
              label: "Duplicate Folder Groups",
              children: Number(folderCleanupReport.summary?.duplicate_groups || 0),
            },
            {
              key: "cleanup-candidates",
              label: "Cleanup Candidates",
              children: Number(folderCleanupReport.summary?.deletion_candidates || 0),
            },
            {
              key: "cleanup-ratelimited",
              label: "Rate Limited Roots",
              children: rateLimitedCleanupRoots.length,
            },
          ]}
        />
        {filteredTableData.length ? (
          <Table
            className="operations-folder-table"
            rowKey="key"
            size="small"
            pagination={false}
            columns={tableColumns}
            dataSource={filteredTableData}
            expandable={{
              childrenColumnName: "children",
              expandedRowKeys,
              expandIconColumnIndex: 1,
              columnWidth: 40,
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
              columnWidth: 44,
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

      <MediaLibraryLogPanel
        scope="operations"
        title="Process Logs"
        stateData={payload}
        currentJobData={currentJob}
        extra={
          <Space wrap>
            {currentJob?.status === "running" ? (
              <Button danger loading={actionLoading === "cancel-job"} onClick={handleCancelCurrentJob}>
                Stop Job
              </Button>
            ) : null}
            {planActions.length ? <Button onClick={() => setPlanReviewOpen(true)}>Open Change Preview</Button> : null}
          </Space>
        }
      />

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
      <PlanReviewModal
        open={planReviewOpen}
        plan={activePlan}
        deleteLowerQuality={deleteLowerQuality}
        pruneEmptyDirs={pruneEmptyDirs}
        actionLoading={actionLoading}
        onClose={() => setPlanReviewOpen(false)}
        onDeleteLowerQualityChange={setDeleteLowerQuality}
        onPruneEmptyDirsChange={setPruneEmptyDirs}
        onDryRun={handleDryRunFromReview}
        onExecute={handleExecuteFromReview}
      />
      <DuplicateFolderCleanupModal
        open={cleanupReviewOpen}
        report={folderCleanupReport}
        selectedRootCount={duplicateScanSelection.length}
        selectedGroups={selectedCleanupGroups}
        selectedGroupIds={selectedCleanupGroupIds}
        selectedGroupSummary={selectedCleanupGroupSummary}
        cleanupFolderRows={cleanupFolderRows}
        cleanupDeleteRows={cleanupDeleteRows}
        cleanupGroupColumns={cleanupGroupColumns}
        cleanupFolderColumns={cleanupFolderColumns}
        selectedCleanupFolderKeys={selectedCleanupFolderKeys}
        actionLoading={actionLoading}
        onClose={() => setCleanupReviewOpen(false)}
        onSelectGroups={setSelectedCleanupGroupIds}
        onSelectFolders={setSelectedCleanupFolderKeys}
        onToggleGroup={toggleCleanupGroupSelection}
        onToggleFolder={toggleCleanupFolderSelection}
        onClearSelection={() => setSelectedCleanupGroupIds([])}
        onDelete={() =>
          modal.confirm({
            title: cleanupDeleteRows.length === 1 ? "Delete this duplicate folder?" : `Delete ${cleanupDeleteRows.length} duplicate folders?`,
            content:
              cleanupDeleteRows.length === 1
                ? cleanupDeleteRows[0]?.path
                : "The selected duplicate folders will be deleted from their current roots.",
            okText: "Delete",
            okButtonProps: { danger: true },
            onOk: async () => {
              await handleDeleteDuplicateFolders();
              setCleanupReviewOpen(false);
            },
          })
        }
      />
    </Flex>
  );
}
