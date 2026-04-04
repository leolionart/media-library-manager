import { useEffect, useMemo, useState } from "react";
import {
  App as AntApp,
  Badge,
  Card,
  Col,
  Descriptions,
  Empty,
  Flex,
  List,
  Progress,
  Row,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
} from "antd";
import {
  CheckCircleOutlined,
  CloudServerOutlined,
  FolderOpenOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import { request } from "../api";
import { MediaLibraryLogPanel } from "./MediaLibraryLogPanel";

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
  sync_result: null,
  cleanup_report: null,
  path_repair_report: null,
  managed_folders: [],
  activity_log: [],
  last_scan_at: null,
  last_plan_at: null,
  last_apply_at: null,
  last_sync_at: null,
  last_cleanup_at: null,
  last_path_repair_at: null,
};

function formatDate(value) {
  if (!value) return "Never";
  return new Date(value).toLocaleString();
}

function toSafeNumber(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
}

function formatCountLabel(count, noun) {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function getReadableStatusLabel(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "running") return "In progress";
  if (normalized === "success") return "Done";
  if (normalized === "error") return "Error";
  if (normalized === "cancelled") return "Stopped";
  if (normalized === "dry-run") return "Preview";
  if (normalized === "review") return "Check";
  if (normalized === "applied") return "Applied";
  if (normalized === "info") return "Info";
  return value || "unknown";
}

function getReadableJobKindLabel(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "scan") return "Scan";
  if (normalized === "plan") return "Change plan";
  if (normalized === "apply") return "File changes";
  if (normalized === "cleanup-scan") return "Cleanup scan";
  if (normalized === "path-repair") return "Path repair";
  return value || "Process";
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

function countSuccessfulMessages(entries, messages) {
  const messageSet = new Set(messages);
  return (entries || []).filter(
    (entry) => String(entry?.status || "").toLowerCase() === "success" && messageSet.has(String(entry?.message || ""))
  ).length;
}

function getProcessProgress(job) {
  const summary = job?.summary || {};
  const dryRunCount = toSafeNumber(summary["dry-run"] ?? summary.dry_run);
  const completed = Math.max(
    toSafeNumber(summary.completed),
    toSafeNumber(summary.applied) + dryRunCount + toSafeNumber(summary.skipped) + toSafeNumber(summary.error)
  );
  const total = Math.max(completed, toSafeNumber(summary.total));
  return {
    completed,
    total,
    percent: total ? Math.min(100, Math.round((completed / total) * 100)) : 0,
  };
}

function getProgressStatus(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "running") return "active";
  if (normalized === "success") return "success";
  if (normalized === "error") return "exception";
  return "normal";
}

function buildProcessSummaryTags(job) {
  const summary = job?.summary || {};
  const tags = [];
  const applied = toSafeNumber(summary.applied);
  const skipped = toSafeNumber(summary.skipped);
  const errors = toSafeNumber(summary.error);
  const dryRunCount = toSafeNumber(summary["dry-run"] ?? summary.dry_run);

  if (applied > 0) tags.push({ key: "applied", color: "success", label: `${applied} changed` });
  if (dryRunCount > 0) tags.push({ key: "preview", color: "processing", label: `${dryRunCount} previewed` });
  if (skipped > 0) tags.push({ key: "skipped", color: "warning", label: `${skipped} to check` });
  if (errors > 0) tags.push({ key: "errors", color: "error", label: `${errors} issue${errors === 1 ? "" : "s"}` });
  if (job?.cancel_requested) tags.push({ key: "cancel", color: "warning", label: "Stop requested" });

  return tags;
}

function StatusTag({ value }) {
  const status = String(value || "").toLowerCase();
  let color = "default";
  if (["success", "applied", "running", "info"].includes(status)) color = "success";
  if (["error", "failed"].includes(status)) color = "error";
  if (["dry-run", "review"].includes(status)) color = "processing";
  if (["cancelled"].includes(status)) color = "warning";
  return <Tag color={color}>{getReadableStatusLabel(value)}</Tag>;
}

function OverviewMetricCard({ title, value, prefix, note, extra, tags = [] }) {
  return (
    <Card className="overview-metric-card" extra={extra}>
      <Statistic title={title} value={value} prefix={prefix} />
      <Text className="overview-metric-note">{note}</Text>
      {tags.length ? (
        <Space wrap className="overview-metric-tags">
          {tags.map((tag) => (
            <Tag key={tag.key} color={tag.color}>
              {tag.label}
            </Tag>
          ))}
        </Space>
      ) : null}
    </Card>
  );
}

export function OverviewView() {
  const { message } = AntApp.useApp();
  const [loading, setLoading] = useState(true);
  const [state, setState] = useState(emptyState);
  const [currentJob, setCurrentJob] = useState(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [payload, process] = await Promise.all([request("/api/state"), request("/api/process")]);
        if (cancelled) return;
        setState(payload || emptyState);
        setCurrentJob(process.current_job || payload?.current_job || null);
      } catch (error) {
        if (!cancelled) {
          message.error(error.message);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void load();
    const timerId = window.setInterval(load, currentJob?.status === "running" ? 1500 : 10000);
    return () => {
      cancelled = true;
      window.clearInterval(timerId);
    };
  }, [currentJob?.id, currentJob?.status, message]);

  const reportSummary = state.report?.summary || {};
  const cleanupSummary = state.cleanup_report?.summary || {};
  const pathRepairSummary = state.path_repair_report?.summary || {};
  const syncSummary = state.sync_result?.summary || {};
  const activePlan = useMemo(
    () => getPendingPlan(state.plan, state.apply_result, state.last_plan_at, state.last_apply_at),
    [state.plan, state.apply_result, state.last_plan_at, state.last_apply_at]
  );
  const planSummary = activePlan?.summary || {};
  const enabledIntegrations = useMemo(
    () => ["radarr", "sonarr"].filter((name) => state.integrations?.[name]?.enabled),
    [state.integrations]
  );

  const duplicateGroups =
    toSafeNumber(reportSummary.exact_duplicate_groups) +
    toSafeNumber(reportSummary.media_collision_groups) +
    toSafeNumber(cleanupSummary.folder_media_duplicate_groups);
  const plannedChanges =
    toSafeNumber(planSummary.move) + toSafeNumber(planSummary.delete) + toSafeNumber(planSummary.review);
  const cleanupDeletedCount = countSuccessfulMessages(state.activity_log, ["File deleted."]);
  const repairedPathCount = countSuccessfulMessages(state.activity_log, ["Provider path updated."]);
  const removedProviderItemCount = countSuccessfulMessages(state.activity_log, ["Provider item removed."]);
  const providerFixCount = repairedPathCount + removedProviderItemCount;
  const fileChangeCount = toSafeNumber(state.apply_result?.summary?.applied);
  const syncUpdatedCount = toSafeNumber(syncSummary.updated);
  const resolvedCount = fileChangeCount + cleanupDeletedCount + providerFixCount;
  const attentionCount =
    toSafeNumber(planSummary.review) +
    toSafeNumber(cleanupSummary.folder_media_duplicate_groups) +
    toSafeNumber(pathRepairSummary.issues);
  const processProgress = useMemo(() => getProcessProgress(currentJob), [currentJob]);
  const processSummaryTags = useMemo(() => buildProcessSummaryTags(currentJob), [currentJob]);

  const resolutionItems = [
    {
      key: "files",
      label: "File changes applied",
      description: "Successful move and delete actions from the latest saved apply result.",
      value: fileChangeCount,
      status: fileChangeCount ? "success" : "default",
    },
    {
      key: "cleanup",
      label: "Cleanup files deleted",
      description: "Recent duplicate video files removed from provider-managed folders.",
      value: cleanupDeletedCount,
      status: cleanupDeletedCount ? "success" : "default",
    },
    {
      key: "repair-updated",
      label: "Provider paths updated",
      description: "Items remapped to the correct local folder path.",
      value: repairedPathCount,
      status: repairedPathCount ? "processing" : "default",
    },
    {
      key: "repair-removed",
      label: "Provider items removed",
      description: "Broken provider records removed without touching media files.",
      value: removedProviderItemCount,
      status: removedProviderItemCount ? "warning" : "default",
    },
    {
      key: "sync",
      label: "Provider sync updates",
      description: "Radarr or Sonarr entries refreshed after file changes.",
      value: syncUpdatedCount,
      status: syncUpdatedCount ? "processing" : "default",
    },
  ];

  const attentionItems = [
    {
      key: "review",
      label: "Manual review items",
      description: "Planned cases the app could not resolve automatically.",
      value: toSafeNumber(planSummary.review),
      status: toSafeNumber(planSummary.review) ? "warning" : "default",
    },
    {
      key: "cleanup-groups",
      label: "Cleanup duplicate groups",
      description: "Movie folders that still contain multiple candidate video files.",
      value: toSafeNumber(cleanupSummary.folder_media_duplicate_groups),
      status: toSafeNumber(cleanupSummary.folder_media_duplicate_groups) ? "warning" : "default",
    },
    {
      key: "repair-issues",
      label: "Path repair issues",
      description: `${toSafeNumber(pathRepairSummary.with_suggestions)} already have suggested folder matches.`,
      value: toSafeNumber(pathRepairSummary.issues),
      status: toSafeNumber(pathRepairSummary.issues) ? "warning" : "default",
    },
    {
      key: "sync-errors",
      label: "Sync errors",
      description: "Provider sync tasks that need another look.",
      value: toSafeNumber(syncSummary.error),
      status: toSafeNumber(syncSummary.error) ? "error" : "default",
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
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12} xl={6}>
          <OverviewMetricCard
            title="Connected Roots"
            value={state.roots.length || 0}
            prefix={<FolderOpenOutlined />}
            note={`${state.managed_folders?.length || 0} managed SMB folder${state.managed_folders?.length === 1 ? "" : "s"} tracked`}
            extra={<Tag>{enabledIntegrations.length} provider{enabledIntegrations.length === 1 ? "" : "s"}</Tag>}
            tags={enabledIntegrations.map((name) => ({ key: name, color: "processing", label: name }))}
          />
        </Col>
        <Col xs={24} md={12} xl={6}>
          <OverviewMetricCard
            title="Duplicate Findings"
            value={duplicateGroups}
            prefix={<CloudServerOutlined />}
            note={`${toSafeNumber(reportSummary.exact_duplicate_groups)} exact, ${toSafeNumber(reportSummary.media_collision_groups)} collision, ${toSafeNumber(cleanupSummary.folder_media_duplicate_groups)} cleanup`}
            extra={<Tag color={duplicateGroups ? "warning" : "success"}>{duplicateGroups ? "open" : "clear"}</Tag>}
            tags={[
              { key: "indexed", color: "default", label: `${toSafeNumber(reportSummary.files)} indexed` },
              { key: "cleanup", color: "warning", label: `${toSafeNumber(cleanupSummary.skipped)} skipped` },
            ]}
          />
        </Col>
        <Col xs={24} md={12} xl={6}>
          <OverviewMetricCard
            title="Planned Changes"
            value={plannedChanges}
            prefix={<SyncOutlined />}
            note={`${toSafeNumber(planSummary.move)} move, ${toSafeNumber(planSummary.delete)} delete, ${toSafeNumber(planSummary.review)} check manually. Last plan: ${formatDate(state.last_plan_at)}`}
            extra={<Tag color={activePlan ? "processing" : "default"}>{activePlan ? "saved plan" : "no plan"}</Tag>}
            tags={[
              { key: "queue", color: attentionCount ? "warning" : "success", label: `${attentionCount} waiting` },
            ]}
          />
        </Col>
        <Col xs={24} md={12} xl={6}>
          <OverviewMetricCard
            title="Cases Resolved"
            value={resolvedCount}
            prefix={<CheckCircleOutlined />}
            note={`${fileChangeCount} file changes, ${cleanupDeletedCount} cleanup deletions, ${providerFixCount} provider fixes`}
            extra={<Tag color={resolvedCount ? "success" : "default"}>{syncUpdatedCount} synced</Tag>}
            tags={[
              { key: "changed", color: "success", label: `${fileChangeCount} changed` },
              { key: "cleanup-deleted", color: "warning", label: `${cleanupDeletedCount} deleted` },
              { key: "provider-fixed", color: "processing", label: `${providerFixCount} repaired` },
            ]}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]} className="overview-panel-row">
        <Col xs={24} xl={14} className="overview-panel-col">
          <Card
            title="Resolution Breakdown"
            extra={<Tag color={resolvedCount ? "success" : "default"}>{formatCountLabel(resolvedCount, "case")} resolved</Tag>}
            className="overview-panel-card"
          >
            <List
              className="overview-stat-list"
              dataSource={resolutionItems}
              renderItem={(item) => (
                <List.Item className="overview-stat-item">
                  <List.Item.Meta
                    title={
                      <Space size={10} wrap>
                        <Badge status={item.status} />
                        <Text strong>{item.label}</Text>
                      </Space>
                    }
                    description={item.description}
                  />
                  <Text strong className="overview-stat-value">
                    {item.value}
                  </Text>
                </List.Item>
              )}
            />
          </Card>
        </Col>

        <Col xs={24} xl={10} className="overview-panel-col">
          <Card
            title="Current Process"
            extra={
              currentJob ? (
                <Space wrap size={[8, 8]}>
                  <StatusTag value={currentJob.status || "running"} />
                  <Tag>{getReadableJobKindLabel(currentJob.kind)}</Tag>
                </Space>
              ) : (
                <Tag>Idle</Tag>
              )
            }
            className="overview-panel-card"
          >
            {currentJob ? (
              <Flex vertical gap={16}>
                <Text strong className="overview-process-message">
                  {currentJob.message}
                </Text>

                {processProgress.total ? (
                  <Progress
                    className="overview-process-progress"
                    percent={processProgress.percent}
                    status={getProgressStatus(currentJob.status)}
                    format={() => `${processProgress.completed}/${processProgress.total}`}
                  />
                ) : (
                  <Text type="secondary">This process does not report step counts yet.</Text>
                )}

                {processSummaryTags.length ? (
                  <Space wrap>
                    {processSummaryTags.map((tag) => (
                      <Tag key={tag.key} color={tag.color}>
                        {tag.label}
                      </Tag>
                    ))}
                  </Space>
                ) : null}

                <Descriptions
                  size="small"
                  column={1}
                  bordered
                  className="overview-descriptions"
                  items={[
                    {
                      key: "started-at",
                      label: "Started",
                      children: formatDate(currentJob.started_at),
                    },
                    {
                      key: "updated-at",
                      label: currentJob.finished_at ? "Finished" : "Updated",
                      children: formatDate(currentJob.finished_at || currentJob.updated_at),
                    },
                    {
                      key: "progress",
                      label: "Progress",
                      children: processProgress.total
                        ? `${processProgress.completed}/${processProgress.total}`
                        : "No step counter available",
                    },
                  ]}
                />
              </Flex>
            ) : (
              <Empty description="No active process." />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} className="overview-panel-row">
        <Col xs={24} xl={12} className="overview-panel-col">
          <Card title="System Snapshot" className="overview-panel-card">
            <Descriptions
              size="small"
              column={1}
              bordered
              className="overview-descriptions"
              items={[
                ["Latest Scan", formatDate(state.last_scan_at)],
                ["Latest Cleanup Scan", formatDate(state.last_cleanup_at)],
                ["Latest Path Repair", formatDate(state.last_path_repair_at)],
                ["Latest Changes", formatDate(state.last_apply_at)],
                ["Latest Sync", formatDate(state.last_sync_at)],
                ["Enabled Integrations", enabledIntegrations.length ? enabledIntegrations.join(" + ") : "No provider enabled"],
              ].map(([label, children]) => ({
                key: String(label).toLowerCase().replaceAll(" ", "-"),
                label,
                children,
              }))}
            />
          </Card>
        </Col>

        <Col xs={24} xl={12} className="overview-panel-col">
          <Card
            title="Attention Queue"
            extra={<Tag color={attentionCount ? "warning" : "success"}>{attentionCount ? `${attentionCount} waiting` : "all clear"}</Tag>}
            className="overview-panel-card"
          >
            {attentionCount ? (
              <List
                className="overview-stat-list"
                dataSource={attentionItems}
                renderItem={(item) => (
                  <List.Item className="overview-stat-item">
                    <List.Item.Meta
                      title={
                        <Space size={10} wrap>
                          <Badge status={item.status} />
                          <Text strong>{item.label}</Text>
                        </Space>
                      }
                      description={item.description}
                    />
                    <Text strong className="overview-stat-value">
                      {item.value}
                    </Text>
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="No manual review queue right now." />
            )}
          </Card>
        </Col>
      </Row>

      <MediaLibraryLogPanel
        scope="activity"
        title="Recent Activity"
        stateData={state}
        currentJobData={currentJob}
        loading={loading}
      />
    </Flex>
  );
}

export default OverviewView;
