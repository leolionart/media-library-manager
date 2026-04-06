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
  DatabaseOutlined,
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
  empty_folder_cleanup_report: null,
  path_repair_report: null,
  managed_folders: [],
  activity_log: [],
  last_scan_at: null,
  last_plan_at: null,
  last_apply_at: null,
  last_sync_at: null,
  last_cleanup_at: null,
  last_empty_folder_cleanup_at: null,
  last_path_repair_at: null,
  last_folder_index_at: null,
  folder_index_summary: null,
};

const emptyProviderStats = {
  movies: 0,
  series: 0,
  movieFiles: 0,
  episodeFiles: 0,
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
  if (normalized === "folder-index") return "Folder index";
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

function getActivityEntryTime(entry) {
  return String(entry?.created_at || entry?.timestamp || "").trim();
}

function getLatestSuccessfulActivityAt(entries, messages) {
  const messageSet = new Set(messages);
  const values = (entries || [])
    .filter(
      (entry) =>
        String(entry?.status || "").toLowerCase() === "success" && messageSet.has(String(entry?.message || ""))
    )
    .map((entry) => getActivityEntryTime(entry))
    .filter(Boolean);
  if (!values.length) return null;
  values.sort((left, right) => Date.parse(right) - Date.parse(left));
  return values[0] || null;
}

function getLatestDate(...values) {
  return values
    .filter(Boolean)
    .reduce((latest, value) => {
      if (!latest) return value;
      return Date.parse(value) > Date.parse(latest) ? value : latest;
    }, null);
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
  const [providerStats, setProviderStats] = useState(emptyProviderStats);

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

  useEffect(() => {
    let cancelled = false;

    const loadProviderStats = async () => {
      const integrations = state.integrations || {};
      const enabledProviders = ["radarr", "sonarr"].filter((name) => integrations?.[name]?.enabled);
      if (!enabledProviders.length) {
        if (!cancelled) setProviderStats(emptyProviderStats);
        return;
      }

      try {
        const results = await Promise.all(
          enabledProviders.map((provider) => request(`/api/integrations/${provider}/items`))
        );
        if (cancelled) return;

        const nextStats = { ...emptyProviderStats };
        enabledProviders.forEach((provider, index) => {
          const items = Array.isArray(results[index]) ? results[index] : [];
          if (provider === "radarr") {
            nextStats.movies = items.length;
            nextStats.movieFiles = items.filter((item) => Boolean(item?.hasFile)).length;
            return;
          }
          nextStats.series = items.length;
          nextStats.episodeFiles = items.reduce(
            (total, item) => total + toSafeNumber(item?.statistics?.episodeFileCount),
            0
          );
        });
        setProviderStats(nextStats);
      } catch (error) {
        if (!cancelled) {
          console.error(error);
        }
      }
    };

    void loadProviderStats();
    const timerId = window.setInterval(loadProviderStats, 60000);
    return () => {
      cancelled = true;
      window.clearInterval(timerId);
    };
  }, [state.integrations]);

  const reportSummary = state.report?.summary || {};
  const cleanupSummary = state.cleanup_report?.summary || {};
  const emptyFolderCleanupSummary = state.empty_folder_cleanup_report?.summary || {};
  const pathRepairSummary = state.path_repair_report?.summary || {};
  const folderIndexSummary = state.folder_index_summary || {};
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
    toSafeNumber(cleanupSummary.folder_media_duplicate_groups) +
    toSafeNumber(emptyFolderCleanupSummary.duplicate_groups);
  const plannedChanges =
    toSafeNumber(planSummary.move) + toSafeNumber(planSummary.delete) + toSafeNumber(planSummary.review);
  const cleanupDeletedCount = countSuccessfulMessages(state.activity_log, ["File deleted.", "Folder deleted."]);
  const repairedPathCount = countSuccessfulMessages(state.activity_log, ["Provider path updated."]);
  const removedProviderItemCount = countSuccessfulMessages(state.activity_log, ["Provider item removed."]);
  const providerFixCount = repairedPathCount + removedProviderItemCount;
  const fileChangeCount = toSafeNumber(state.apply_result?.summary?.applied);
  const syncUpdatedCount = toSafeNumber(syncSummary.updated);
  const resolvedCount = fileChangeCount + cleanupDeletedCount + providerFixCount;
  const attentionCount =
    toSafeNumber(planSummary.review) +
    toSafeNumber(cleanupSummary.folder_media_duplicate_groups) +
    toSafeNumber(emptyFolderCleanupSummary.duplicate_groups) +
    toSafeNumber(pathRepairSummary.issues);
  const latestCleanupAt = getLatestDate(state.last_cleanup_at, state.last_empty_folder_cleanup_at);
  const latestResolutionActivityAt = getLatestDate(
    getLatestSuccessfulActivityAt(state.activity_log, ["File deleted.", "Folder deleted."]),
    getLatestSuccessfulActivityAt(state.activity_log, ["Provider path updated.", "Provider item removed."])
  );
  const latestResolvedAt = getLatestDate(state.last_apply_at, state.last_empty_folder_cleanup_at, latestResolutionActivityAt);
  const processProgress = useMemo(() => getProcessProgress(currentJob), [currentJob]);
  const processSummaryTags = useMemo(() => buildProcessSummaryTags(currentJob), [currentJob]);
  const rootKinds = useMemo(() => {
    const counts = { movie: 0, series: 0, mixed: 0 };
    (state.roots || []).forEach((root) => {
      const key = String(root?.kind || "mixed").toLowerCase();
      if (Object.hasOwn(counts, key)) {
        counts[key] += 1;
      }
    });
    return counts;
  }, [state.roots]);
  const totalProviderItems = providerStats.movies + providerStats.series;
  const totalTrackedMediaFiles = providerStats.movieFiles + providerStats.episodeFiles;

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
      label: "Cleanup deletions",
      description: "Recent duplicate files or duplicate folders removed by cleanup workflows.",
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
      description: "Provider duplicate-file groups and root-folder duplicate groups still waiting for cleanup.",
      value:
        toSafeNumber(cleanupSummary.folder_media_duplicate_groups) +
        toSafeNumber(emptyFolderCleanupSummary.duplicate_groups),
      status:
        toSafeNumber(cleanupSummary.folder_media_duplicate_groups) +
          toSafeNumber(emptyFolderCleanupSummary.duplicate_groups)
        ? "warning"
        : "default",
    },
    {
      key: "repair-issues",
      label: "Path repair issues",
      description: "Provider items whose saved folder path needs manual search and relink.",
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
            note={`${state.managed_folders?.length || 0} managed SMB folder${state.managed_folders?.length === 1 ? "" : "s"} tracked. ${enabledIntegrations.length} provider${enabledIntegrations.length === 1 ? "" : "s"} enabled.`}
            extra={<Tag>{enabledIntegrations.length} provider{enabledIntegrations.length === 1 ? "" : "s"}</Tag>}
            tags={[
              { key: "movie-roots", color: "default", label: `${rootKinds.movie} movie` },
              { key: "series-roots", color: "processing", label: `${rootKinds.series} series` },
              { key: "mixed-roots", color: "purple", label: `${rootKinds.mixed} mixed` },
            ]}
          />
        </Col>
        <Col xs={24} md={12} xl={6}>
          <OverviewMetricCard
            title="Indexed Folders"
            value={toSafeNumber(folderIndexSummary.folders)}
            prefix={<DatabaseOutlined />}
            note={`Cached folder metadata from connected roots. Last refresh: ${formatDate(state.last_folder_index_at)}`}
            extra={<Tag color={state.last_folder_index_at ? "success" : "warning"}>{state.last_folder_index_at ? "cached" : "not built"}</Tag>}
            tags={[
              { key: "cache-roots", color: "default", label: `${toSafeNumber(folderIndexSummary.roots)} roots` },
              { key: "cache-depth", color: "processing", label: `depth ${toSafeNumber(folderIndexSummary.max_depth)}` },
              { key: "cache-errors", color: toSafeNumber(folderIndexSummary.errors) ? "error" : "success", label: `${toSafeNumber(folderIndexSummary.errors)} errors` },
            ]}
          />
        </Col>
        <Col xs={24} md={12} xl={6}>
          <OverviewMetricCard
            title="Provider Library"
            value={totalProviderItems}
            prefix={<CloudServerOutlined />}
            note={`${providerStats.movies} movies and ${providerStats.series} series currently tracked by enabled providers.`}
            extra={<Tag color={enabledIntegrations.length ? "processing" : "default"}>{enabledIntegrations.length ? "provider inventory" : "no provider"}</Tag>}
            tags={[
              { key: "provider-movies", color: "default", label: `${providerStats.movies} movies` },
              { key: "provider-series", color: "processing", label: `${providerStats.series} series` },
            ]}
          />
        </Col>
        <Col xs={24} md={12} xl={6}>
          <OverviewMetricCard
            title="Tracked Media Files"
            value={totalTrackedMediaFiles}
            prefix={<CheckCircleOutlined />}
            note={`${providerStats.movieFiles} movie folders with files and ${providerStats.episodeFiles} Sonarr episode files currently recognized.`}
            extra={<Tag color={toSafeNumber(pathRepairSummary.issues) ? "warning" : "success"}>{toSafeNumber(pathRepairSummary.issues)} repair issues</Tag>}
            tags={[
              { key: "movie-files", color: "success", label: `${providerStats.movieFiles} movie titles` },
              { key: "episode-files", color: "processing", label: `${providerStats.episodeFiles} episodes` },
              { key: "sync-updated", color: "default", label: `${syncUpdatedCount} synced` },
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
                ["Latest Cleanup Scan", formatDate(latestCleanupAt)],
                ["Latest Path Repair", formatDate(state.last_path_repair_at)],
                ["Latest Changes", formatDate(latestResolvedAt)],
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
