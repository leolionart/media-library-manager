import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Card, Empty, Flex, Input, Segmented, Space, Spin, Tag, Typography, message } from "antd";
import {
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  PauseCircleOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { request, resumeCurrentProcess, retryCurrentProcess, waitCurrentProcess } from "../api";

const { Paragraph, Text } = Typography;

function formatDate(value) {
  if (!value) return "Never";
  return new Date(value).toLocaleString();
}

function formatLogClock(value) {
  if (!value) return "--:--:--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--:--:--";
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function normalizeSearchText(value) {
  return String(value || "")
    .toLowerCase()
    .replaceAll(/[\._()-]+/g, " ")
    .replaceAll(/\s+/g, " ")
    .trim();
}

function getLogEntryTone(level) {
  const normalized = String(level || "").toLowerCase();
  if (["error", "failed"].includes(normalized)) return "error";
  if (["warning", "warn", "cancelled"].includes(normalized)) return "warning";
  if (["success", "applied"].includes(normalized)) return "success";
  return "info";
}

function getLogEntryFilter(level) {
  const tone = getLogEntryTone(level);
  return tone === "success" ? "info" : tone;
}

function getReadableStatusLabel(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "running") return "In progress";
  if (normalized === "success") return "Done";
  if (normalized === "error") return "Error";
  if (normalized === "cancelled") return "Stopped";
  if (normalized === "waiting") return "Waiting";
  if (normalized === "dry-run") return "Preview";
  if (normalized === "review") return "Check";
  if (normalized === "applied") return "Applied";
  if (normalized === "info") return "Info";
  if (normalized === "warning" || normalized === "warn") return "Warning";
  return value || "unknown";
}

function getReadableModeLabel(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "dry-run" || normalized === "preview") return "preview";
  if (normalized === "execute" || normalized === "apply") return "apply";
  return normalized || String(value || "");
}

function formatLogDetailKey(key) {
  return String(key || "").replaceAll("_", " ");
}

function formatLogDetailValue(key, value) {
  if (value === null || value === undefined || value === "") return null;
  if (key === "mode") return getReadableModeLabel(value);
  if (key === "status") return getReadableStatusLabel(value);
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (Array.isArray(value)) return value.map((item) => formatLogDetailValue(key, item)).filter(Boolean).join(" | ");
  if (typeof value === "object") {
    return Object.entries(value)
      .map(([nestedKey, nestedValue]) => {
        const formattedValue = formatLogDetailValue(nestedKey, nestedValue);
        return formattedValue ? `${formatLogDetailKey(nestedKey)}: ${formattedValue}` : null;
      })
      .filter(Boolean)
      .join(" | ");
  }
  return String(value);
}

function buildLogDetailRows(details) {
  return Object.entries(details || {})
    .map(([key, value]) => ({
      key,
      label: formatLogDetailKey(key),
      value: formatLogDetailValue(key, value),
    }))
    .filter((item) => item.value);
}

function buildLogDetailSummary(detailRows) {
  return detailRows
    .slice(0, 3)
    .map((item) => `${item.label}: ${item.value}`)
    .join(" | ");
}

function buildLogSearchText(entry) {
  const details = Object.entries(entry?.details || {})
    .map(([key, value]) => `${key} ${formatLogDetailValue(key, value) || ""}`)
    .join(" ");
  return normalizeSearchText(`${entry?.level || ""} ${entry?.message || ""} ${details}`);
}

function getLogEntryContext(entry, currentJob) {
  const details = entry?.details || {};
  const jobKind = String(currentJob?.kind || "").toLowerCase();

  if (details.mode) return getReadableModeLabel(details.mode);
  if (details.provider) return String(details.provider).toLowerCase();
  if (jobKind === "apply" && (details.destination || details.source || details.keep_path)) return "changes";
  if (jobKind) return jobKind;
  if (details.path || details.storage_uri) return "filesystem";
  return "media-library";
}

function getProcessLogWindowTitle(scope, currentJob) {
  if (currentJob?.kind === "scan") return "duplicate scan";
  if (currentJob?.kind === "plan") return "change plan";
  if (currentJob?.kind === "apply") return "file changes";
  if (currentJob?.kind) return String(currentJob.kind).toLowerCase();
  if (scope === "activity") return "recent activity";
  if (scope === "operations") return "library finder";
  return scope === "cleanup" ? "library-cleanup" : "path-repair";
}

function getReadableJobKindLabel(kind) {
  const normalized = String(kind || "").toLowerCase();
  if (normalized === "scan") return "Scan";
  if (normalized === "plan") return "Change plan";
  if (normalized === "apply") return "File changes";
  if (normalized === "cleanup-scan") return "Folder cleanup";
  if (normalized === "path-repair") return "Path Repair";
  if (normalized === "folder") return "Folder action";
  if (normalized === "integration") return "Provider action";
  return kind || "Process";
}

function toSafeNumber(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
}

function getEffectiveJobSummary(currentJob, applyResult) {
  const merged = {
    ...(applyResult?.summary || {}),
    ...(currentJob?.details?.summary || {}),
    ...(currentJob?.summary || {}),
  };
  const dryRunCount = toSafeNumber(merged["dry-run"] ?? merged.dry_run);
  const derivedCompleted =
    toSafeNumber(merged.applied) + dryRunCount + toSafeNumber(merged.skipped) + toSafeNumber(merged.error);
  if (derivedCompleted > toSafeNumber(merged.completed)) {
    merged.completed = derivedCompleted;
  }
  merged.total =
    toSafeNumber(merged.total) ||
    toSafeNumber(currentJob?.details?.action_count) ||
    toSafeNumber(applyResult?.results?.length) ||
    toSafeNumber(merged.completed);
  merged["dry-run"] = dryRunCount;
  return merged;
}

function formatCountLabel(count, noun = "item") {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function getApplyProcessHeadline(currentJob, applyResult) {
  const mode = getReadableModeLabel(currentJob?.details?.mode || applyResult?.mode);
  const summary = getEffectiveJobSummary(currentJob, applyResult);
  const applied = toSafeNumber(summary.applied);
  const skipped = toSafeNumber(summary.skipped);
  const errors = toSafeNumber(summary.error);

  if (currentJob?.status === "running") {
    return mode === "preview" ? "Previewing upcoming changes." : "Applying changes to your files.";
  }
  if (currentJob?.status === "cancelled") {
    return mode === "preview" ? "Preview was stopped." : "Applying changes was stopped.";
  }
  if (currentJob?.status === "error") {
    return "Could not finish the requested changes.";
  }
  if (mode === "preview") {
    if (skipped > 0 && applied === 0) {
      return `Preview finished. ${formatCountLabel(skipped)} still need manual check.`;
    }
    return "Preview finished. No real files were changed.";
  }
  if (applied > 0) {
    return `Finished. ${formatCountLabel(applied)} changed.`;
  }
  if (skipped > 0 && errors === 0) {
    return `Finished. No files were changed. ${formatCountLabel(skipped)} still need manual check.`;
  }
  if (errors > 0) {
    return `Finished with ${formatCountLabel(errors, "issue")}.`;
  }
  return "Finished. No files were changed.";
}

function getProcessHeadline(scope, currentJob, applyResult) {
  if (!currentJob) return "";
  if (scope === "operations" && String(currentJob.kind || "").toLowerCase() === "apply") {
    return getApplyProcessHeadline(currentJob, applyResult);
  }
  return currentJob.message;
}

function getProcessSummaryNote(scope, currentJob, applyResult, logStreamPaused) {
  if (!currentJob) return "";
  if (currentJob.status === "waiting") {
    return currentJob?.details?.wait_until
      ? `Retry is deferred until ${formatDate(currentJob.details.wait_until)}.`
      : "Retry is deferred. Resume when you are ready.";
  }
  if (scope === "operations" && String(currentJob.kind || "").toLowerCase() === "apply") {
    const mode = getReadableModeLabel(currentJob?.details?.mode || applyResult?.mode);
    const summary = getEffectiveJobSummary(currentJob, applyResult);
    const applied = toSafeNumber(summary.applied);
    const skipped = toSafeNumber(summary.skipped);
    const errors = toSafeNumber(summary.error);

    if (currentJob.status === "running") {
      if (logStreamPaused) {
        return "The live log is paused locally. The job is still running in the background.";
      }
      return mode === "preview"
        ? "This is only a preview. Your files stay unchanged until you choose Apply Changes."
        : "Real file changes are running now. Follow each step below.";
    }
    if (mode === "preview") {
      return skipped > 0
        ? `Nothing changed yet. ${formatCountLabel(skipped)} still need manual check before you can decide what to do next.`
        : "Nothing changed yet because this run only previewed the changes.";
    }
    if (applied > 0 && skipped > 0) {
      return `${formatCountLabel(applied)} changed. ${formatCountLabel(skipped)} still need manual check.`;
    }
    if (applied > 0) {
      return `${formatCountLabel(applied)} changed successfully.`;
    }
    if (skipped > 0 && errors === 0) {
      return `No files were changed. ${formatCountLabel(skipped)} still need manual check.`;
    }
    if (errors > 0) {
      return `The run ended with ${formatCountLabel(errors, "issue")}. Check the log lines below for details.`;
    }
    return "No files were changed during this run.";
  }
  if (currentJob.status === "running") {
    return logStreamPaused
      ? "Realtime logs are paused locally while the job continues in the background."
      : "Realtime logs are following the current job.";
  }
  return `Stored session snapshot from ${formatDate(currentJob.updated_at)}.`;
}

function jobMatchesScope(scope, job) {
  const kind = String(job?.kind || "").toLowerCase();
  if (scope === "activity") return Boolean(job);
  if (scope === "operations") return ["scan", "plan", "apply", "cleanup-scan"].includes(kind);
  if (scope === "cleanup") return kind === "cleanup-scan";
  if (scope === "repair") return kind === "path-repair";
  return false;
}

function activityMatchesScope(scope, entry) {
  const kind = String(entry?.kind || "").toLowerCase();
  const message = String(entry?.message || "").toLowerCase();
  if (scope === "activity") return true;
  if (scope === "operations") return ["scan", "plan", "apply", "folder"].includes(kind);
  if (scope === "cleanup") {
    return (
      message.includes("cleanup scan") ||
      message.includes("empty duplicate folder") ||
      message.includes("file deleted") ||
      message.includes("file delete failed") ||
      message.includes("folder deleted") ||
      message.includes("folder delete failed")
    );
  }
  if (scope === "repair") {
    return message.includes("path repair") || message.includes("provider path updated") || message.includes("provider item removed");
  }
  return false;
}

export function MediaLibraryLogPanel({ scope, title, extra = null, stateData, currentJobData, loading: loadingOverride = false }) {
  const usesExternalData = stateData !== undefined || currentJobData !== undefined;
  const [loading, setLoading] = useState(!usesExternalData);
  const [state, setState] = useState({ activity_log: [], current_job: null, apply_result: null });
  const [currentJob, setCurrentJob] = useState(currentJobData || null);
  const [logLevelFilter, setLogLevelFilter] = useState("all");
  const [logSearch, setLogSearch] = useState("");
  const [logStreamPaused, setLogStreamPaused] = useState(false);
  const [logPauseMarker, setLogPauseMarker] = useState(null);
  const [logClearMarker, setLogClearMarker] = useState(null);
  const [actionLoading, setActionLoading] = useState("");
  const [processOverride, setProcessOverride] = useState(null);
  const logViewportRef = useRef(null);

  useEffect(() => {
    if (usesExternalData) {
      return undefined;
    }
    let cancelled = false;

    const load = async () => {
      try {
        const [payload, process] = await Promise.all([request("/api/state"), request("/api/process")]);
        if (cancelled) return;
        setState(payload || { activity_log: [], current_job: null, apply_result: null });
        setCurrentJob(process.current_job || payload?.current_job || null);
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void load();
    const timerId = window.setInterval(load, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(timerId);
    };
  }, [usesExternalData]);

  useEffect(() => {
    if (!usesExternalData) return;
    setLoading(false);
    setProcessOverride(null);
  }, [usesExternalData]);

  const effectiveState = usesExternalData ? stateData || { activity_log: [], current_job: null, apply_result: null } : state;
  const effectiveCurrentJob = processOverride || (usesExternalData ? currentJobData || null : currentJob);

  const scopedCurrentJob = jobMatchesScope(scope, effectiveCurrentJob) ? effectiveCurrentJob : null;
  const applyResult = effectiveState?.apply_result || null;
  const scopedActivity = useMemo(
    () => (effectiveState.activity_log || []).filter((entry) => activityMatchesScope(scope, entry)).slice(0, 40),
    [scope, effectiveState.activity_log]
  );

  const rawEntries = useMemo(() => {
    if (scopedCurrentJob?.logs?.length) {
      return scopedCurrentJob.logs;
    }
    return scopedActivity.map((entry) => ({
      ts: entry.created_at,
      level: entry.status || entry.kind || "info",
      message: entry.message,
      details: entry.details || {},
    }));
  }, [scopedActivity, scopedCurrentJob]);

  const visibleEntries = useMemo(
    () =>
      rawEntries.filter((entry) => {
        const timestamp = Date.parse(entry?.ts || "") || 0;
        if (logClearMarker && timestamp <= logClearMarker) return false;
        if (logStreamPaused && logPauseMarker && timestamp > logPauseMarker) return false;
        return true;
      }),
    [rawEntries, logClearMarker, logPauseMarker, logStreamPaused]
  );

  const filteredEntries = useMemo(() => {
    const normalizedQuery = normalizeSearchText(logSearch);
    return visibleEntries.filter((entry) => {
      const filterTone = getLogEntryFilter(entry.level);
      if (logLevelFilter !== "all" && filterTone !== logLevelFilter) return false;
      if (!normalizedQuery) return true;
      return buildLogSearchText(entry).includes(normalizedQuery);
    });
  }, [logLevelFilter, logSearch, visibleEntries]);

  const logCount = useMemo(
    () => ({
      all: visibleEntries.length,
      info: visibleEntries.filter((entry) => getLogEntryFilter(entry.level) === "info").length,
      warning: visibleEntries.filter((entry) => getLogEntryFilter(entry.level) === "warning").length,
      error: visibleEntries.filter((entry) => getLogEntryFilter(entry.level) === "error").length,
    }),
    [visibleEntries]
  );
  const effectiveJobSummary = useMemo(
    () => getEffectiveJobSummary(scopedCurrentJob, applyResult),
    [applyResult, scopedCurrentJob]
  );
  const processHeadline = useMemo(
    () => getProcessHeadline(scope, scopedCurrentJob, applyResult),
    [applyResult, scope, scopedCurrentJob]
  );
  const processSummaryNote = useMemo(
    () => getProcessSummaryNote(scope, scopedCurrentJob, applyResult, logStreamPaused),
    [applyResult, logStreamPaused, scope, scopedCurrentJob]
  );
  const effectiveLoading = loadingOverride || loading;
  const availableActions = scopedCurrentJob?.available_actions || {};

  const refreshProcessSnapshot = async () => {
    const [payload, process] = await Promise.all([request("/api/state"), request("/api/process")]);
    if (!usesExternalData) {
      setState(payload || { activity_log: [], current_job: null, apply_result: null });
      setCurrentJob(process.current_job || payload?.current_job || null);
      return;
    }
    setProcessOverride(process.current_job || payload?.current_job || null);
  };

  const runJobAction = async (mode) => {
    setActionLoading(mode);
    try {
      if (mode === "retry") {
        await retryCurrentProcess();
      } else if (mode === "resume") {
        await resumeCurrentProcess();
      } else if (mode === "wait") {
        await waitCurrentProcess(300);
      }
      await refreshProcessSnapshot();
      message.success(mode === "wait" ? "Job deferred." : `Job ${mode} request finished.`);
    } catch (error) {
      message.error(error.message);
      try {
        await refreshProcessSnapshot();
      } catch (refreshError) {
        console.error(refreshError);
      }
    } finally {
      setActionLoading("");
    }
  };

  useEffect(() => {
    if (scope === "activity") return;
    setLogLevelFilter("all");
    setLogSearch("");
    setLogStreamPaused(false);
    setLogPauseMarker(null);
    setLogClearMarker(null);
  }, [scope, scopedCurrentJob?.id]);

  useEffect(() => {
    const viewport = logViewportRef.current;
    if (!viewport || logStreamPaused) return;
    viewport.scrollTop = viewport.scrollHeight;
  }, [filteredEntries.length, logStreamPaused]);

  if (effectiveLoading) {
    return (
      <Card title={title} extra={extra} className="process-log-card">
        <div className="app-loading">
          <Spin size="large" />
        </div>
      </Card>
    );
  }

  return (
    <Card title={title} extra={extra} className="process-log-card">
      {!scopedCurrentJob && !scopedActivity.length ? (
        <Empty description={scope === "activity" ? "No recent activity yet." : "No action logs for this workspace yet."} />
      ) : (
        <Flex vertical gap={16}>
          {scopedCurrentJob ? (
            <div className="process-log-summary">
              <div className="process-log-summary-main">
                <div className="process-log-meta">
                  <div className="process-log-meta-main">
                    <Space wrap className="process-log-summary-badges">
                      <Tag color={scopedCurrentJob.status === "error" ? "error" : ["cancelled", "waiting"].includes(scopedCurrentJob.status) ? "warning" : "success"}>
                        {getReadableStatusLabel(scopedCurrentJob.status || "running")}
                      </Tag>
                      <Tag>{getReadableJobKindLabel(scopedCurrentJob.kind)}</Tag>
                      {scopedCurrentJob.cancel_requested ? <Tag color="warning">Stop Requested</Tag> : null}
                      {scopedCurrentJob.status === "running" && !logStreamPaused ? <Tag color="processing">Live</Tag> : null}
                      {logStreamPaused ? <Tag>Paused</Tag> : null}
                    </Space>
                    <Text strong className="process-log-headline">
                      {processHeadline}
                    </Text>
                    <Text className="process-log-summary-note">
                      {processSummaryNote}
                    </Text>
                  </div>
                </div>
              </div>
              <div className="process-log-summary-stats">
                <div className="process-log-stat">
                  <span className="process-log-stat-label">Started</span>
                  <strong className="process-log-stat-value">{formatDate(scopedCurrentJob.started_at)}</strong>
                </div>
                <div className="process-log-stat">
                  <span className="process-log-stat-label">{scopedCurrentJob.finished_at ? "Finished" : "Updated"}</span>
                  <strong className="process-log-stat-value">{formatDate(scopedCurrentJob.finished_at || scopedCurrentJob.updated_at)}</strong>
                </div>
                <div className="process-log-stat">
                  <span className="process-log-stat-label">Progress</span>
                  <strong className="process-log-stat-value">
                    {Number(effectiveJobSummary.completed || 0)}/{Number(effectiveJobSummary.total || 0)}
                  </strong>
                </div>
                <div className="process-log-stat">
                  <span className="process-log-stat-label">Visible</span>
                  <strong className="process-log-stat-value">{logCount.all.toLocaleString()} entries</strong>
                </div>
              </div>
            </div>
          ) : null}

          <div className="process-log-toolbar">
            <Segmented
              className="process-log-filter-segmented"
              size="small"
              options={[
                { label: "ALL", value: "all" },
                { label: "INFO", value: "info" },
                { label: "WARN", value: "warning" },
                { label: "ERROR", value: "error" },
              ]}
              value={logLevelFilter}
              onChange={(value) => setLogLevelFilter(String(value))}
            />
            <Input
              className="process-log-search"
              allowClear
              value={logSearch}
              onChange={(event) => setLogSearch(event.target.value)}
              placeholder="Search logs..."
              prefix={<SearchOutlined />}
            />
            <Space wrap className="process-log-controls">
              <Space size={8} className="process-log-control-group">
                <Button
                  size="small"
                  className="process-log-control-button"
                  disabled={!visibleEntries.length}
                  onClick={() => {
                    if (logStreamPaused) {
                      setLogStreamPaused(false);
                      setLogPauseMarker(null);
                    } else {
                      const lastEntry = rawEntries[rawEntries.length - 1];
                      setLogPauseMarker(lastEntry ? Date.parse(lastEntry.ts || "") || Date.now() : Date.now());
                      setLogStreamPaused(true);
                    }
                  }}
                >
                  {logStreamPaused ? "Resume" : "Pause"}
                </Button>
                <Button
                  size="small"
                  className="process-log-control-button"
                  disabled={!visibleEntries.length}
                  onClick={() => {
                    const lastEntry = rawEntries[rawEntries.length - 1];
                    setLogClearMarker(lastEntry ? Date.parse(lastEntry.ts || "") || Date.now() : Date.now());
                  }}
                >
                  Clear
                </Button>
              </Space>
              <Tag
                variant="filled"
                className={`process-log-toolbar-tag ${
                  scopedCurrentJob?.cancel_requested ? "tone-warning" : logStreamPaused ? "tone-muted" : "tone-success"
                }`}
                icon={
                  scopedCurrentJob?.cancel_requested ? (
                    <ExclamationCircleOutlined />
                  ) : logStreamPaused ? (
                    <PauseCircleOutlined />
                  ) : (
                    <ClockCircleOutlined />
                  )
                }
              >
                {scopedCurrentJob?.cancel_requested ? "Stop requested" : logStreamPaused ? "Paused" : "Live"}
              </Tag>
              <Tag variant="filled" className="process-log-toolbar-tag tone-neutral">
                {filteredEntries.length.toLocaleString()} / {logCount.all.toLocaleString()} entries
              </Tag>
              {logCount.warning ? (
                <Tag variant="filled" className="process-log-toolbar-tag tone-warning">
                  {logCount.warning} warn
                </Tag>
              ) : null}
              {logCount.error ? (
                <Tag variant="filled" className="process-log-toolbar-tag tone-error">
                  {logCount.error} error
                </Tag>
              ) : null}
              {availableActions.wait ? (
                <Button size="small" className="process-log-control-button" loading={actionLoading === "wait"} onClick={() => void runJobAction("wait")}>
                  Wait
                </Button>
              ) : null}
              {availableActions.retry ? (
                <Button size="small" className="process-log-control-button" loading={actionLoading === "retry"} onClick={() => void runJobAction("retry")}>
                  Retry
                </Button>
              ) : null}
              {availableActions.resume ? (
                <Button size="small" type="primary" className="process-log-control-button" loading={actionLoading === "resume"} onClick={() => void runJobAction("resume")}>
                  Resume
                </Button>
              ) : null}
            </Space>
          </div>

          <div className="process-log-shell">
            <div className="process-log-shell-head">
              <div className="process-log-shell-lights">
                <span />
                <span />
                <span />
              </div>
              <div className="process-log-shell-title">
                <Text strong className="process-log-shell-title-main">
                  {getProcessLogWindowTitle(scope, scopedCurrentJob)}
                </Text>
                <Text className="process-log-shell-title-sub">
                  {scopedCurrentJob ? `${getReadableJobKindLabel(scopedCurrentJob.kind)} activity` : `${scope} trace`}
                </Text>
              </div>
              <Text className="process-log-shell-state">
                {scopedCurrentJob?.status === "running" ? "Attached to live stream" : "Recent action feed"}
              </Text>
            </div>
            <div ref={logViewportRef} className="process-log-viewport">
              {filteredEntries.length ? (
                <div className="process-log-lines">
                  {filteredEntries.map((entry, index) => {
                    const tone = getLogEntryTone(entry.level);
                    const detailSummary = buildLogDetailSummary(buildLogDetailRows(entry.details || {}));
                    return (
                      <div key={`${entry.ts}-${entry.message}-${index}`} className={`process-log-line tone-${tone}`}>
                        <div className="process-log-line-meta">
                          <Text className="process-log-line-time">{formatLogClock(entry.ts)}</Text>
                          <Tag variant="filled" className={`process-log-line-level tone-${tone}`}>
                            {String(entry.level || "info").toUpperCase()}
                          </Tag>
                          <Tag variant="filled" className="process-log-line-context">
                            {getLogEntryContext(entry, scopedCurrentJob)}
                          </Tag>
                        </div>
                        <div className="process-log-line-body">
                          <Paragraph className="process-log-line-message">{entry.message}</Paragraph>
                          {detailSummary ? <Text className="process-log-line-summary">{detailSummary}</Text> : null}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <Empty className="process-log-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="No logs match the current filter." />
              )}
            </div>
          </div>
        </Flex>
      )}
    </Card>
  );
}

export default MediaLibraryLogPanel;
