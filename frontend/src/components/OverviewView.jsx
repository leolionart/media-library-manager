import { useEffect, useMemo, useState } from "react";
import {
  App as AntApp,
  Card,
  Col,
  Descriptions,
  Empty,
  Flex,
  Row,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
} from "antd";
import { CloudServerOutlined, FolderOpenOutlined, LinkOutlined, SyncOutlined } from "@ant-design/icons";
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
  activity_log: [],
  last_scan_at: null,
  last_plan_at: null,
  last_apply_at: null,
  last_sync_at: null,
};

function formatDate(value) {
  if (!value) return "Never";
  return new Date(value).toLocaleString();
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

function StatusTag({ value }) {
  const status = String(value || "").toLowerCase();
  let color = "default";
  if (["success", "applied", "running", "info"].includes(status)) color = "success";
  if (["error", "failed"].includes(status)) color = "error";
  if (["dry-run", "review"].includes(status)) color = "processing";
  return <Tag color={color}>{getReadableStatusLabel(value)}</Tag>;
}

export function OverviewView() {
  const { message } = AntApp.useApp();
  const [loading, setLoading] = useState(true);
  const [state, setState] = useState(emptyState);
  const [currentJob, setCurrentJob] = useState(null);

  useEffect(() => {
    Promise.all([request("/api/state"), request("/api/process")])
      .then(([payload, process]) => {
        setState(payload || emptyState);
        setCurrentJob(process.current_job || payload?.current_job || null);
      })
      .catch((error) => message.error(error.message))
      .finally(() => setLoading(false));
  }, [message]);

  const reportSummary = state.report?.summary || {};
  const cleanupSummary = state.cleanup_report?.summary || {};
  const activePlan = useMemo(
    () => getPendingPlan(state.plan, state.apply_result, state.last_plan_at, state.last_apply_at),
    [state.plan, state.apply_result, state.last_plan_at, state.last_apply_at]
  );
  const planSummary = activePlan?.summary || {};
  const duplicateGroups =
    (reportSummary.exact_duplicate_groups || 0) +
    (reportSummary.media_collision_groups || 0) +
    (cleanupSummary.folder_media_duplicate_groups || 0);
  const enabledIntegrations = useMemo(
    () => ["radarr", "sonarr"].filter((name) => state.integrations?.[name]?.enabled),
    [state.integrations]
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
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12} xl={6}>
          <Card>
            <Statistic title="Connected Roots" value={state.roots.length || 0} prefix={<FolderOpenOutlined />} />
            <Text type="secondary">Active library sources configured</Text>
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card>
            <Statistic title="Duplicate Groups" value={duplicateGroups} prefix={<CloudServerOutlined />} />
            <Text type="secondary">
              {reportSummary.exact_duplicate_groups || 0} exact, {reportSummary.media_collision_groups || 0} collision,{" "}
              {cleanupSummary.folder_media_duplicate_groups || 0} cleanup
            </Text>
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card>
            <Statistic title="Planned Changes" value={(planSummary.move || 0) + (planSummary.delete || 0) + (planSummary.review || 0)} prefix={<SyncOutlined />} />
            <Text type="secondary">Last plan: {formatDate(state.last_plan_at)}</Text>
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card>
            <Statistic title="Integrations" value={enabledIntegrations.length} prefix={<LinkOutlined />} />
            <Text type="secondary">{enabledIntegrations.length ? enabledIntegrations.join(" + ") : "No provider enabled"}</Text>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} className="overview-panel-row">
        <Col xs={24} xl={14} className="overview-panel-col">
          <Card title="System Snapshot" className="overview-panel-card">
            <DescriptionsLike
              items={[
                ["Latest Scan", formatDate(state.last_scan_at)],
                ["Latest Changes", formatDate(state.last_apply_at)],
                ["Latest Sync", formatDate(state.last_sync_at)],
                ["Connected Roots", state.roots.length || 0],
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} xl={10} className="overview-panel-col">
          <Card title="Current Process" className="overview-panel-card">
            {currentJob ? (
              <Flex vertical gap={16}>
                <Space wrap>
                  <StatusTag value={currentJob.status || "running"} />
                  <Tag>{getReadableJobKindLabel(currentJob.kind)}</Tag>
                </Space>
                <Text strong style={{ fontSize: 18 }}>
                  {currentJob.message}
                </Text>
                <Descriptions
                  size="small"
                  column={1}
                  items={[
                    {
                      key: "started-at",
                      label: "Started",
                      children: formatDate(currentJob.started_at),
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

      <MediaLibraryLogPanel scope="activity" title="Recent Activity" />
    </Flex>
  );
}

function DescriptionsLike({ items }) {
  return (
    <Flex vertical gap={12}>
      {items.map(([label, value]) => (
        <Flex key={label} justify="space-between" align="center" gap={16}>
          <Text type="secondary">{label}</Text>
          <Text>{value}</Text>
        </Flex>
      ))}
    </Flex>
  );
}

export default OverviewView;
