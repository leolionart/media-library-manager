import { useEffect, useMemo, useState } from "react";
import {
  App as AntApp,
  Card,
  Col,
  Descriptions,
  Empty,
  Flex,
  List,
  Row,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
} from "antd";
import { CloudServerOutlined, FolderOpenOutlined, LinkOutlined, SyncOutlined } from "@ant-design/icons";
import { request } from "../api";

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

function StatusTag({ value }) {
  const status = String(value || "").toLowerCase();
  let color = "default";
  if (["success", "applied", "running", "info"].includes(status)) color = "success";
  if (["error", "failed"].includes(status)) color = "error";
  if (["dry-run", "review"].includes(status)) color = "processing";
  return <Tag color={color}>{value || "unknown"}</Tag>;
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
  const planSummary = state.plan?.summary || {};
  const duplicateGroups = (reportSummary.exact_duplicate_groups || 0) + (reportSummary.media_collision_groups || 0);
  const enabledIntegrations = useMemo(
    () => ["radarr", "sonarr"].filter((name) => state.integrations?.[name]?.enabled),
    [state.integrations]
  );
  const recentActivity = (state.activity_log || []).slice(0, 8);

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
              {reportSummary.exact_duplicate_groups || 0} exact, {reportSummary.media_collision_groups || 0} collision
            </Text>
          </Card>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <Card>
            <Statistic title="Plan Actions" value={(planSummary.move || 0) + (planSummary.delete || 0) + (planSummary.review || 0)} prefix={<SyncOutlined />} />
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

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={14}>
          <Card title="System Snapshot">
            <DescriptionsLike
              items={[
                ["Latest Scan", formatDate(state.last_scan_at)],
                ["Latest Apply", formatDate(state.last_apply_at)],
                ["Latest Sync", formatDate(state.last_sync_at)],
                ["Connected Roots", state.roots.length || 0],
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card title="Current Process">
            {currentJob ? (
              <Flex vertical gap={16}>
                <Space wrap>
                  <StatusTag value={currentJob.status || "running"} />
                  <Tag>{currentJob.kind || "process"}</Tag>
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

      <Card title="Recent Activity">
        <List
          dataSource={recentActivity}
          locale={{ emptyText: <Empty description="No recent activity." /> }}
          renderItem={(item) => (
            <List.Item>
              <List.Item.Meta
                title={
                  <SpaceTitle>
                    <StatusTag value={item.status} />
                    <span>{item.message}</span>
                  </SpaceTitle>
                }
                description={`${item.kind} • ${formatDate(item.created_at)}`}
              />
            </List.Item>
          )}
        />
      </Card>
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

function SpaceTitle({ children }) {
  return (
    <Flex align="center" gap={8} wrap="wrap">
      {children}
    </Flex>
  );
}

export default OverviewView;
