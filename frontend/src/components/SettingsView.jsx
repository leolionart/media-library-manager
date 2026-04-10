import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Col,
  Divider,
  Empty,
  Flex,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography
} from "antd";
import {
  ApiOutlined,
  EditOutlined,
  FolderOpenOutlined,
  LinkOutlined,
  PlusOutlined,
  RadarChartOutlined,
  SaveOutlined
} from "@ant-design/icons";
import {
  addRoot,
  browseLocalPath,
  browseSmbPath,
  deleteLanConnection,
  discoverLanDevices,
  fetchRcloneRemotes,
  fetchSettingsState,
  mountRclone,
  removeRoot,
  runManualSync,
  saveIntegrations,
  saveLanConnection,
  saveRcloneConnection,
  syncRcloneConfig,
  testIntegrations,
  testLanConnection,
  unmountRclone,
  updateRoot
} from "../api";

const { Text } = Typography;
const { TextArea } = Input;

const ROOT_KIND_OPTIONS = [
  { label: "Mixed", value: "mixed" },
  { label: "Movies", value: "movie" },
  { label: "Series", value: "series" },
  { label: "Review", value: "review" }
];

const SMB_VERSION_OPTIONS = ["3.0", "2.1", "2.0", "1.0"].map((value) => ({ label: `SMB ${value}`, value }));

const emptyState = {
  roots: [],
  integrations: {
    radarr: { enabled: false, base_url: "", api_key: "", root_folder_path: "" },
    sonarr: { enabled: false, base_url: "", api_key: "", root_folder_path: "" },
    sync_options: {
      sync_after_apply: true,
      rescan_after_update: true,
      create_root_folder_if_missing: true
    }
  },
  lan_connections: { smb: [], rclone: [] },
  sync_result: null,
  activity_log: []
};

function formatDate(value) {
  if (!value) return "Never";
  return new Date(value).toLocaleString();
}

function stripPriorityLabel(value) {
  return String(value || "").replace(/\s+P\d+$/, "").trim();
}

function buildSmbPath(value) {
  const text = String(value || "").trim();
  if (!text || text === "/") return "/";
  return `/${text.replace(/^\/+/, "").replace(/\/+$/, "")}`;
}

function encodeSmbUriPath(value) {
  const normalized = buildSmbPath(value);
  if (normalized === "/") return "/";
  return `/${normalized
    .slice(1)
    .split("/")
    .filter(Boolean)
    .map((part) => encodeURIComponent(part))
    .join("/")}`;
}

function toSmbPseudoSegment(value, fallback) {
  const text = String(value || "").trim().replaceAll("/", "_");
  return text || fallback;
}

function createSmbRootPayload(values, connection) {
  const shareName = String(values.share_name || connection?.share_name || "").trim().replace(/^\/+|\/+$/g, "");
  const connectionId = String(connection?.id || values.connection_id || "").trim();
  if (!shareName || !connectionId) return null;

  const rootPath = buildSmbPath(values.share_path);
  const storageUri = `smb://${encodeURIComponent(shareName)}${encodeSmbUriPath(rootPath)}?connection_id=${encodeURIComponent(connectionId)}`;
  const pseudoBase = `/smb/${toSmbPseudoSegment(connectionId, "connection")}/${toSmbPseudoSegment(shareName, "share")}`;
  const path = rootPath === "/" ? pseudoBase : `${pseudoBase}${rootPath}`;

  return {
    path,
    storage_uri: storageUri,
    share_name: shareName,
    label: String(values.label || "").trim() || shareName,
    priority: Number(values.priority || 50),
    kind: values.kind || "mixed",
    connection_id: connectionId,
    connection_label: connection?.label || ""
  };
}

function buildRclonePath(value) {
  const text = String(value || "").trim();
  if (!text || text === "/") return "/";
  return `/${text.replace(/^\/+/, "").replace(/\/+$/, "")}`;
}

function encodeRcloneUriPath(value) {
  const normalized = buildRclonePath(value);
  if (normalized === "/") return "/";
  return `/${normalized
    .slice(1)
    .split("/")
    .filter(Boolean)
    .map((part) => encodeURIComponent(part))
    .join("/")}`;
}

function createRcloneRootPayload(values) {
  const remoteName = String(values.rclone_remote || "").trim().replace(/^\/+|\/+$/g, "");
  if (!remoteName) return null;

  const rootPath = buildRclonePath(values.rclone_path);
  const storageUri = `rclone://${encodeURIComponent(remoteName)}${encodeRcloneUriPath(rootPath)}`;
  const mountBase = String(values.rclone_mount_path || "").trim();
  const normalizedMountBase = mountBase ? buildRclonePath(mountBase) : `/rclone/${toSmbPseudoSegment(remoteName, "remote")}`;
  const path = rootPath === "/" ? normalizedMountBase : `${normalizedMountBase}${rootPath}`;

  return {
    path,
    storage_uri: storageUri,
    share_name: "",
    label: String(values.label || "").trim() || remoteName,
    priority: Number(values.priority || 50),
    kind: values.kind || "mixed",
    connection_id: "",
    connection_label: `rclone:${remoteName}`
  };
}

function buildRootFormValues(root) {
  if (!root) {
    return { mode: "local", priority: 50, kind: "mixed", share_path: "/", rclone_path: "/", rclone_mount_path: "" };
  }

  if (root.storage_uri) {
    try {
      const parsed = new URL(root.storage_uri);
      if (parsed.protocol === "rclone:") {
        return {
          mode: "rclone",
          original_path: root.path,
          rclone_remote: decodeURIComponent(parsed.hostname || ""),
          rclone_path: decodeURIComponent(parsed.pathname || "/"),
          rclone_mount_path: root.path || "",
          label: root.label || "",
          priority: Number(root.priority || 50),
          kind: root.kind || "mixed",
        };
      }
      return {
        mode: "smb",
        original_path: root.path,
        connection_id: root.connection_id || "",
        share_name: root.share_name || decodeURIComponent(parsed.hostname || ""),
        share_path: decodeURIComponent(parsed.pathname || "/"),
        label: root.label || "",
        priority: Number(root.priority || 50),
        kind: root.kind || "mixed",
      };
    } catch {
      return {
        mode: "local",
        original_path: root.path,
        path: root.path,
        label: root.label || "",
        priority: Number(root.priority || 50),
        kind: root.kind || "mixed",
        share_path: "/",
        rclone_path: "/",
        rclone_mount_path: "",
      };
    }
  }

  return {
    mode: "local",
    original_path: root.path,
    path: root.path,
    label: root.label || "",
    priority: Number(root.priority || 50),
    kind: root.kind || "mixed",
    share_path: "/",
    rclone_path: "/",
    rclone_mount_path: "",
  };
}

function rootTypeLabel(record) {
  const uri = String(record?.storage_uri || "");
  if (uri.startsWith("rclone://")) return "Rclone";
  if (uri.startsWith("smb://")) return "SMB";
  return "Local";
}

function parsePseudoSmbPath(value) {
  const parts = String(value || "")
    .split("/")
    .filter(Boolean);
  if (parts.length < 3 || parts[0] !== "smb") return null;
  return {
    connectionId: parts[1],
    shareName: parts[2],
    path: parts.length > 3 ? `/${parts.slice(3).join("/")}` : "/",
  };
}

function ProviderSettingsCard({ provider, testResult, onSave, onTest, saving, testing }) {
  const title = provider === "radarr" ? "Radarr" : "Sonarr";

  return (
    <Card
      className="integration-provider-card-react"
      title={
        <Space>
          <RadarChartOutlined />
          <span>{title}</span>
        </Space>
      }
      extra={
        <Form.Item name={[provider, "enabled"]} valuePropName="checked" noStyle>
          <Switch />
        </Form.Item>
      }
    >
      <Flex vertical gap={16}>
        <Form.Item name={[provider, "base_url"]} noStyle>
          <Input placeholder={provider === "radarr" ? "http://radarr.local:7878" : "http://sonarr.local:8989"} />
        </Form.Item>
        <Form.Item name={[provider, "api_key"]} noStyle>
          <Input.Password placeholder="API key" />
        </Form.Item>
        <Form.Item name={[provider, "root_folder_path"]} noStyle>
          <Input placeholder="Provider root folder path" />
        </Form.Item>

        {testResult ? (
          <Alert
            type={testResult.status === "error" ? "error" : testResult.status === "disabled" ? "warning" : "success"}
            showIcon
            message={`${title}: ${testResult.status || "unknown"}`}
            description={testResult.error || testResult.api_root || testResult.message || "Ready"}
          />
        ) : null}

        <Space wrap>
          <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={onSave}>
            Save {title}
          </Button>
          <Button loading={testing} onClick={onTest}>
            Test Connection
          </Button>
        </Space>
      </Flex>
    </Card>
  );
}

function PathBrowserModal({ state, onCancel, onBrowse, onUseCurrent }) {
  return (
    <Modal
      open={state.open}
      title={state.mode === "smb" ? "Choose SMB Folder" : "Choose Folder"}
      okText="Use Current Folder"
      okButtonProps={{ disabled: state.loading || !state.path }}
      onCancel={onCancel}
      onOk={onUseCurrent}
      width={760}
    >
      <Flex vertical gap={16}>
        {state.error ? <Alert type="error" showIcon message={state.error} /> : null}
        <Flex justify="space-between" align="center" gap={12} wrap>
          <Text type="secondary" className="mono">
            {state.mode === "smb"
              ? `${state.shareName ? `${state.shareName}:` : ""}${state.path || "/"}`
              : state.path || "/"}
          </Text>
          {state.parent ? (
            <Button onClick={() => onBrowse({ path: state.parent, shareName: state.shareName })}>Up One Level</Button>
          ) : null}
        </Flex>

        {state.breadcrumbs?.length ? (
          <Space size={[8, 8]} wrap>
            {state.breadcrumbs.map((crumb) => (
              <Button
                key={`${crumb.share_name || ""}:${crumb.path || "/"}`}
                size="small"
                onClick={() => onBrowse({ path: crumb.path || "/", shareName: crumb.share_name || state.shareName })}
              >
                {crumb.name || "/"}
              </Button>
            ))}
          </Space>
        ) : null}

        {state.mode === "local" && state.favorites?.length ? (
          <Space size={[8, 8]} wrap>
            {state.favorites.map((favorite) => (
              <Button key={favorite.mount_point} size="small" onClick={() => onBrowse({ path: favorite.mount_point })}>
                {favorite.label}
              </Button>
            ))}
          </Space>
        ) : null}

        <List
          bordered
          loading={state.loading}
          dataSource={state.entries || []}
          locale={{ emptyText: <Empty description="No folders available here." /> }}
          renderItem={(entry) => (
            <List.Item
              actions={[
                <Button
                  key="open"
                  onClick={() =>
                    onBrowse({
                      path: entry.path || "/",
                      shareName: entry.share_name || state.shareName,
                      scope: entry.type === "share" ? "" : undefined,
                    })
                  }
                >
                  Open
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={entry.name}
                description={
                  state.mode === "smb"
                    ? `${entry.type === "share" ? "Share" : "Folder"}${entry.comment ? ` • ${entry.comment}` : ""}`
                    : entry.path
                }
              />
            </List.Item>
          )}
        />
      </Flex>
    </Modal>
  );
}

export function SettingsView() {
  const { message } = AntApp.useApp();
  const [loading, setLoading] = useState(true);
  const [state, setState] = useState(emptyState);
  const [discovering, setDiscovering] = useState(false);
  const [lanDevices, setLanDevices] = useState([]);
  const [integrationTestResults, setIntegrationTestResults] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [rootModalOpen, setRootModalOpen] = useState(false);
  const [editingRoot, setEditingRoot] = useState(null);
  const [connectionModalOpen, setConnectionModalOpen] = useState(false);
  const [editingConnection, setEditingConnection] = useState(null);
  const [rcloneModalOpen, setRcloneModalOpen] = useState(false);
  const [editingRclone, setEditingRclone] = useState(null);
  const [rcloneRemotes, setRcloneRemotes] = useState([]);
  const [loadingRcloneRemotes, setLoadingRcloneRemotes] = useState(false);
  const [syncingRclone, setSyncingRclone] = useState(false);
  const [savingRclone, setSavingRclone] = useState(false);
  const [deletingRcloneId, setDeletingRcloneId] = useState("");
  const [mountingRcloneId, setMountingRcloneId] = useState("");
  const [savingIntegrations, setSavingIntegrations] = useState(false);
  const [testingIntegration, setTestingIntegration] = useState("");
  const [testingConnectionId, setTestingConnectionId] = useState("");
  const [savingConnection, setSavingConnection] = useState(false);
  const [deletingConnectionId, setDeletingConnectionId] = useState("");
  const [removingRootPath, setRemovingRootPath] = useState("");
  const [pathBrowser, setPathBrowser] = useState({
    open: false,
    mode: "local",
    loading: false,
    error: "",
    path: "",
    parent: null,
    breadcrumbs: [],
    entries: [],
    favorites: [],
    connectionId: "",
    shareName: "",
  });
  const [rootForm] = Form.useForm();
  const [connectionForm] = Form.useForm();
  const [rcloneForm] = Form.useForm();
  const [integrationsForm] = Form.useForm();
  const [lanTestResults, setLanTestResults] = useState({});

  const connections = state.lan_connections?.smb || [];
  const rcloneConnections = state.lan_connections?.rclone || [];
  const selectedConnectionId = Form.useWatch("connection_id", rootForm);
  const selectedRootConnection = useMemo(
    () => connections.find((item) => item.id === selectedConnectionId) || null,
    [connections, selectedConnectionId]
  );

  const refreshSettings = async () => {
    const payload = await fetchSettingsState();
    setState(payload || emptyState);
    integrationsForm.setFieldsValue(payload?.integrations || emptyState.integrations);
  };

  const loadRcloneRemotes = async () => {
    setLoadingRcloneRemotes(true);
    try {
      const result = await fetchRcloneRemotes();
      setRcloneRemotes(result.remotes || []);
    } catch (error) {
      message.error(error.message);
    } finally {
      setLoadingRcloneRemotes(false);
    }
  };

  useEffect(() => {
    refreshSettings()
      .catch((error) => message.error(error.message))
      .finally(() => setLoading(false));
    loadRcloneRemotes().catch(() => {});
  }, [message, integrationsForm]);

  const providerCards = ["radarr", "sonarr"].map((provider) => ({
    provider,
    testResult: integrationTestResults?.[provider] || null
  }));

  const loadLocalPathBrowser = async (path) => {
    const smbPath = parsePseudoSmbPath(path);
    if (smbPath) {
      return loadSmbPathBrowser(smbPath);
    }
    setPathBrowser((current) => ({ ...current, open: true, mode: "local", loading: true, error: "" }));
    try {
      const result = await browseLocalPath(path);
      setPathBrowser((current) => ({
        ...current,
        open: true,
        mode: "local",
        loading: false,
        error: "",
        path: result.path || path || "/",
        parent: result.parent || null,
        breadcrumbs: result.breadcrumbs || [],
        entries: (result.entries || []).filter((entry) => entry.type === "directory"),
        favorites: result.favorites || [],
      }));
    } catch (error) {
      setPathBrowser((current) => ({ ...current, open: true, mode: "local", loading: false, error: error.message }));
    }
  };

  const loadSmbPathBrowser = async ({ connectionId, shareName, path, scope }) => {
    setPathBrowser((current) => ({
      ...current,
      open: true,
      mode: "smb",
      loading: true,
      error: "",
      connectionId,
      shareName: shareName || "",
    }));
    try {
      const result = await browseSmbPath({
        connectionId,
        shareName,
        path,
        scope: scope || (!shareName ? "host" : ""),
      });
      setPathBrowser((current) => ({
        ...current,
        open: true,
        mode: "smb",
        loading: false,
        error: "",
        connectionId,
        shareName: result.connection?.share_name || shareName || "",
        path: result.path || "/",
        parent: result.parent || null,
        breadcrumbs: result.breadcrumbs || [],
        entries: result.entries || [],
        favorites: [],
      }));
    } catch (error) {
      setPathBrowser((current) => ({ ...current, open: true, mode: "smb", loading: false, error: error.message }));
    }
  };

  const rootColumns = [
    {
      title: "Label",
      dataIndex: "label",
      key: "label",
      render: (value, record) => (
        <Space direction="vertical" size={4}>
          <Text strong>{stripPriorityLabel(value)}</Text>
          <Space size={[4, 4]} wrap>
            <Tag>{record.kind}</Tag>
            {rootTypeLabel(record) === "SMB" ? (
              <Tag color="processing">SMB</Tag>
            ) : rootTypeLabel(record) === "Rclone" ? (
              <Tag color="geekblue">Rclone</Tag>
            ) : (
              <Tag>Local</Tag>
            )}
          </Space>
        </Space>
      )
    },
    {
      title: "Path",
      key: "path",
      render: (_, record) => (
        <Flex vertical gap={4}>
          <Text className="mono">{record.path}</Text>
          {record.storage_uri ? (
            <Text type="secondary" className="mono">
              {record.storage_uri}
            </Text>
          ) : null}
        </Flex>
      )
    },
    {
      title: "Source",
      key: "source",
      width: 220,
      render: (_, record) => (
        <Text type="secondary">
          {rootTypeLabel(record) === "Rclone"
            ? record.connection_label || "Rclone remote"
            : record.connection_label || record.share_name || "Direct filesystem path"}
        </Text>
      )
    },
    {
      title: "",
      key: "actions",
      width: 220,
      render: (_, record) => (
        <Space wrap>
          <Button
            icon={<EditOutlined />}
            onClick={() => {
              setEditingRoot(record);
              rootForm.setFieldsValue(buildRootFormValues(record));
              setRootModalOpen(true);
            }}
          >
            Edit
          </Button>
          <Popconfirm
            title="Remove connected folder?"
            description={record.label}
            okText="Remove"
            onConfirm={async () => {
              setRemovingRootPath(record.path);
              try {
                await removeRoot(record.path);
                await refreshSettings();
                message.success("Connected folder removed.");
              } catch (error) {
                message.error(error.message);
              } finally {
                setRemovingRootPath("");
              }
            }}
          >
            <Button danger loading={removingRootPath === record.path}>
              Remove
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ];

  const connectionColumns = [
    {
      title: "Connection",
      key: "label",
      render: (_, record) => (
        <Space direction="vertical" size={4}>
          <Text strong>{record.label}</Text>
          <Space size={[4, 4]} wrap>
            <Tag color={record.enabled ? "success" : "default"}>{record.enabled ? "Enabled" : "Disabled"}</Tag>
            <Tag>{`SMB ${record.version}`}</Tag>
            {record.has_password ? <Tag color="processing">Saved password</Tag> : null}
          </Space>
        </Space>
      )
    },
    {
      title: "Endpoint",
      key: "endpoint",
      render: (_, record) => (
        <Flex vertical gap={4}>
          <Text className="mono">{`//${record.host}${record.share_name ? `/${record.share_name}` : ""}`}</Text>
          <Text type="secondary" className="mono">
            {record.base_path || "/"}
          </Text>
        </Flex>
      )
    },
    {
      title: "Account",
      key: "account",
      width: 220,
      render: (_, record) => <Text type="secondary">{record.username || "Anonymous"}</Text>
    },
    {
      title: "",
      key: "actions",
      width: 280,
      render: (_, record) => (
        <Space wrap>
          <Button
            onClick={() => {
              setEditingConnection(record);
              connectionForm.setFieldsValue({
                ...record,
                password: ""
              });
              setConnectionModalOpen(true);
            }}
          >
            Edit
          </Button>
          <Button
            loading={testingConnectionId === record.id}
            onClick={async () => {
              setTestingConnectionId(record.id);
              try {
                const result = await testLanConnection({ id: record.id });
                setLanTestResults((current) => ({ ...current, [record.id]: result }));
                message.success("SMB connection test passed.");
              } catch (error) {
                setLanTestResults((current) => ({
                  ...current,
                  [record.id]: { status: "error", message: error.message }
                }));
                message.error(error.message);
              } finally {
                setTestingConnectionId("");
              }
            }}
          >
            Test
          </Button>
          <Popconfirm
            title="Delete SMB connection?"
            description={record.label}
            okText="Delete"
            okButtonProps={{ danger: true }}
            onConfirm={async () => {
              setDeletingConnectionId(record.id);
              try {
                await deleteLanConnection(record.id);
                await refreshSettings();
                message.success("SMB connection removed.");
              } catch (error) {
                message.error(error.message);
              } finally {
                setDeletingConnectionId("");
              }
            }}
          >
            <Button danger loading={deletingConnectionId === record.id}>
              Delete
            </Button>
          </Popconfirm>
        </Space>
      )
    }
  ];

  const rcloneColumns = [
    {
      title: "Remote",
      key: "label",
      render: (_, record) => (
        <Space direction="vertical" size={4}>
          <Text strong>{record.label}</Text>
          <Space size={[4, 4]} wrap>
            <Tag color={record.enabled ? "success" : "default"}>{record.enabled ? "Enabled" : "Disabled"}</Tag>
            <Tag color="geekblue">{record.rclone_name}</Tag>
            {record.has_config ? <Tag color="processing">Config stored</Tag> : null}
          </Space>
        </Space>
      )
    },
    {
      title: "Type",
      key: "type",
      render: (_, record) => <Text type="secondary">{record.config?.type || "unknown"}</Text>
    },
    {
      title: "",
      key: "actions",
      width: 280,
      render: (_, record) => (
        <Space wrap>
          <Button
            onClick={() => {
              setEditingRclone(record);
              rcloneForm.setFieldsValue({
                ...record,
                config_json: JSON.stringify(record.config, null, 2)
              });
              setRcloneModalOpen(true);
            }}
          >
            Edit
          </Button>
          <Popconfirm
            title="Delete Rclone connection?"
            description={record.label}
            okText="Delete"
            okButtonProps={{ danger: true }}
            onConfirm={async () => {
              setDeletingRcloneId(record.id);
              try {
                await deleteLanConnection(record.id); // This now handles rclone- prefix
                await refreshSettings();
                message.success("Rclone connection removed.");
              } catch (error) {
                message.error(error.message);
              } finally {
                setDeletingRcloneId("");
              }
            }}
          >
            <Button danger loading={deletingRcloneId === record.id}>
              Delete
            </Button>
          </Popconfirm>
        </Space>
      )
    }
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
      <Tabs
        items={[
          {
            key: "library",
            label: "Library",
            children: (
              <Flex vertical gap={16}>
                <Card
                  title={
                    <Space>
                      <FolderOpenOutlined />
                      <span>Connected Folders</span>
                    </Space>
                  }
                  extra={
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={() => {
                        setEditingRoot(null);
                        rootForm.setFieldsValue(buildRootFormValues(null));
                        setRootModalOpen(true);
                      }}
                    >
                      Add Root
                    </Button>
                  }
                >
                  <Table
                    rowKey="path"
                    columns={rootColumns}
                    dataSource={state.roots}
                    pagination={false}
                    scroll={{ x: 960 }}
                    locale={{ emptyText: <Empty description="No connected folders configured." /> }}
                  />
                </Card>
              </Flex>
            )
          },
          {
            key: "network",
            label: "Network",
            children: (
              <Flex vertical gap={16}>
                <Card
                  title={
                    <Space>
                      <LinkOutlined />
                      <span>SMB Connections</span>
                    </Space>
                  }
                  extra={
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={() => {
                        setEditingConnection(null);
                        connectionForm.setFieldsValue({
                          id: "",
                          label: "",
                          host: "",
                          port: 445,
                          share_name: "",
                          base_path: "",
                          username: "",
                          password: "",
                          domain: "",
                          version: "3.0",
                          enabled: true
                        });
                        setConnectionModalOpen(true);
                      }}
                    >
                      New Connection
                    </Button>
                  }
                >
                  <Table
                    rowKey="id"
                    columns={connectionColumns}
                    dataSource={connections}
                    pagination={false}
                    scroll={{ x: 1080 }}
                    expandable={{
                      expandedRowRender: (record) => {
                        const lastResult = lanTestResults[record.id];
                        return lastResult ? (
                          <Alert
                            type={lastResult.status === "error" ? "error" : "success"}
                            showIcon
                            message={lastResult.status === "error" ? "Connection test failed" : "Connection test passed"}
                            description={lastResult.message || lastResult.target || "Connection is ready"}
                          />
                        ) : (
                          <Text type="secondary">Run Test to validate this connection from the current runtime.</Text>
                        );
                      }
                    }}
                    locale={{ emptyText: <Empty description="No SMB connections saved." /> }}
                  />
                </Card>

                <Card
                  title={
                    <Space>
                      <RadarChartOutlined />
                      <span>Rclone Connections</span>
                    </Space>
                  }
                  extra={
                    <Space>
                      <Button
                        loading={syncingRclone}
                        onClick={async () => {
                          setSyncingRclone(true);
                          try {
                            await syncRcloneConfig();
                            await loadRcloneRemotes();
                            message.success("Rclone config synced with system.");
                          } catch (error) {
                            message.error(error.message);
                          } finally {
                            setSyncingRclone(false);
                          }
                        }}
                      >
                        Sync With System
                      </Button>
                      <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={() => {
                          setEditingRclone(null);
                          rcloneForm.setFieldsValue({
                            id: "",
                            label: "",
                            rclone_name: "",
                            config_json: "{}",
                            enabled: true
                          });
                          setRcloneModalOpen(true);
                        }}
                      >
                        New Rclone Connection
                      </Button>
                    </Space>
                  }
                >
                  <Table
                    rowKey="id"
                    columns={rcloneColumns}
                    dataSource={rcloneConnections}
                    pagination={false}
                    scroll={{ x: 1080 }}
                    locale={{ emptyText: <Empty description="No Rclone connections saved." /> }}
                  />
                </Card>

                <Card
                  title="Rclone System Remotes"
                  extra={
                    <Button loading={loadingRcloneRemotes} onClick={loadRcloneRemotes}>
                      Refresh Remotes
                    </Button>
                  }
                >
                  <List
                    dataSource={rcloneRemotes}
                    loading={loadingRcloneRemotes}
                    locale={{ emptyText: "No Rclone remotes found in system config." }}
                    renderItem={(remote) => (
                      <List.Item
                        actions={[
                          <Button
                            key="use"
                            onClick={() => {
                              setEditingRclone(null);
                              rcloneForm.setFieldsValue({
                                id: "",
                                label: remote.name,
                                rclone_name: remote.name,
                                config_json: JSON.stringify({ type: remote.type }, null, 2),
                                enabled: true
                              });
                              setRcloneModalOpen(true);
                            }}
                          >
                            Use As Template
                          </Button>
                        ]}
                      >
                        <List.Item.Meta
                          title={remote.name}
                          description={<Tag color="geekblue">{remote.type}</Tag>}
                        />
                      </List.Item>
                    )}
                  />
                </Card>

                <Card
                  title="LAN Discovery"
                  extra={
                    <Button
                      loading={discovering}
                      onClick={async () => {
                        setDiscovering(true);
                        try {
                          const result = await discoverLanDevices();
                          setLanDevices(result.devices || []);
                          message.success("LAN discovery finished.");
                        } catch (error) {
                          message.error(error.message);
                        } finally {
                          setDiscovering(false);
                        }
                      }}
                    >
                      Discover Devices
                    </Button>
                  }
                >
                  <List
                    dataSource={lanDevices}
                    locale={{ emptyText: "No discovery run yet." }}
                    renderItem={(device) => (
                      <List.Item
                        actions={[
                          <Button
                            key="use"
                            onClick={() => {
                              setEditingConnection(null);
                              connectionForm.setFieldsValue({
                                id: "",
                                label: device.hostname || device.display_name || device.ip_address || "",
                                host: device.hostname || device.ip_address || "",
                                port: 445,
                                share_name: "",
                                base_path: "",
                                username: "",
                                password: "",
                                domain: "",
                                version: "3.0",
                                enabled: true
                              });
                              setConnectionModalOpen(true);
                            }}
                          >
                            Use As Template
                          </Button>
                        ]}
                      >
                        <List.Item.Meta
                          title={device.hostname || device.display_name || device.ip_address || "Unknown device"}
                          description={
                            <Space size={[8, 8]} wrap>
                              {device.ip_address ? <Text className="mono">{device.ip_address}</Text> : null}
                              {device.mac_address ? <Text type="secondary" className="mono">{device.mac_address}</Text> : null}
                              {(device.connect_urls || []).map((url) => (
                                <Tag key={url}>{url}</Tag>
                              ))}
                            </Space>
                          }
                        />
                      </List.Item>
                    )}
                  />
                </Card>
              </Flex>
            )
          },
          {
            key: "integrations",
            label: "Integrations",
            children: (
              <Flex vertical gap={16}>
                <Form form={integrationsForm} layout="vertical" className="integrations-form-react">
                  <Row gutter={[16, 16]}>
                    {providerCards.map(({ provider, testResult }) => (
                      <Col key={provider} xs={24} xl={12}>
                        <ProviderSettingsCard
                          provider={provider}
                          testResult={testResult}
                          saving={savingIntegrations}
                          testing={testingIntegration === provider}
                          onSave={async () => {
                            setSavingIntegrations(true);
                            try {
                              const payload = integrationsForm.getFieldsValue(true);
                              await saveIntegrations(payload);
                              await refreshSettings();
                              message.success(`${provider === "radarr" ? "Radarr" : "Sonarr"} settings saved.`);
                            } catch (error) {
                              message.error(error.message);
                            } finally {
                              setSavingIntegrations(false);
                            }
                          }}
                          onTest={async () => {
                            setTestingIntegration(provider);
                            try {
                              const payload = integrationsForm.getFieldsValue(true);
                              const result = await testIntegrations(payload);
                              setIntegrationTestResults(result.results || null);
                              const providerResult = result.results?.[provider];
                              if (providerResult?.status === "error") {
                                throw new Error(providerResult.error || `${provider} test failed`);
                              }
                              message.success(`${provider === "radarr" ? "Radarr" : "Sonarr"} connection test passed.`);
                            } catch (error) {
                              message.error(error.message);
                            } finally {
                              setTestingIntegration("");
                            }
                          }}
                        />
                      </Col>
                    ))}
                  </Row>

                  <Card
                    className="integration-sync-card-react"
                    title={
                      <Space>
                        <ApiOutlined />
                        <span>Sync Options</span>
                      </Space>
                    }
                    extra={
                      <Space wrap>
                        <Button
                          icon={<SaveOutlined />}
                          loading={savingIntegrations}
                          onClick={async () => {
                            setSavingIntegrations(true);
                            try {
                              await saveIntegrations(integrationsForm.getFieldsValue(true));
                              await refreshSettings();
                              message.success("Integration settings saved.");
                            } catch (error) {
                              message.error(error.message);
                            } finally {
                              setSavingIntegrations(false);
                            }
                          }}
                        >
                          Save All
                        </Button>
                        <Button
                          loading={syncing}
                          onClick={async () => {
                            setSyncing(true);
                            try {
                              await runManualSync();
                              await refreshSettings();
                              message.success("Manual sync completed.");
                            } catch (error) {
                              message.error(error.message);
                            } finally {
                              setSyncing(false);
                            }
                          }}
                        >
                          Run Manual Sync
                        </Button>
                      </Space>
                    }
                  >
                    <Row gutter={[16, 16]}>
                      <Col xs={24} xl={8}>
                        <Card size="small" className="sync-option-card-react">
                          <div className="sync-option-head-react">
                            <Form.Item name={["sync_options", "sync_after_apply"]} valuePropName="checked" noStyle>
                              <Switch />
                            </Form.Item>
                          </div>
                          <Divider />
                          <Text strong>Sync after apply</Text>
                          <div>
                            <Text type="secondary">Run provider update after an apply result is executed.</Text>
                          </div>
                        </Card>
                      </Col>
                      <Col xs={24} xl={8}>
                        <Card size="small" className="sync-option-card-react">
                          <div className="sync-option-head-react">
                            <Form.Item name={["sync_options", "rescan_after_update"]} valuePropName="checked" noStyle>
                              <Switch />
                            </Form.Item>
                          </div>
                          <Divider />
                          <Text strong>Rescan after update</Text>
                          <div>
                            <Text type="secondary">Trigger Radarr or Sonarr rescan after the path changes.</Text>
                          </div>
                        </Card>
                      </Col>
                      <Col xs={24} xl={8}>
                        <Card size="small" className="sync-option-card-react">
                          <div className="sync-option-head-react">
                            <Form.Item
                              name={["sync_options", "create_root_folder_if_missing"]}
                              valuePropName="checked"
                              noStyle
                            >
                              <Switch />
                            </Form.Item>
                          </div>
                          <Divider />
                          <Text strong>Create missing provider roots</Text>
                          <div>
                            <Text type="secondary">Ensure configured root folders exist before provider updates.</Text>
                          </div>
                        </Card>
                      </Col>
                    </Row>

                  {state.sync_result ? (
                    <Alert
                      style={{ marginTop: 16 }}
                      type={state.sync_result.status === "error" ? "error" : "info"}
                      showIcon
                      message={`Last sync: ${state.sync_result.status || "unknown"}`}
                      description={formatDate(state.sync_result.generated_at)}
                    />
                  ) : null}
                  </Card>
                </Form>
              </Flex>
            )
          }
        ]}
      />

      <Modal
        open={rootModalOpen}
        title={editingRoot ? "Edit Connected Folder" : "Add Connected Folder"}
        okText={editingRoot ? "Save Changes" : "Add Root"}
        onCancel={() => {
          setRootModalOpen(false);
          setEditingRoot(null);
          rootForm.resetFields();
        }}
        onOk={() => rootForm.submit()}
      >
        <Form
          form={rootForm}
          layout="vertical"
          initialValues={{ mode: "local", priority: 50, kind: "mixed", share_path: "/", rclone_path: "/", rclone_mount_path: "" }}
          onFinish={async (values) => {
            try {
              const originalPath = String(values.original_path || editingRoot?.path || "").trim();
              let payload = null;
              if (values.mode === "smb") {
                payload = createSmbRootPayload(values, selectedRootConnection);
              } else if (values.mode === "rclone") {
                payload = createRcloneRootPayload(values);
              } else {
                payload = {
                  path: String(values.path || "").trim(),
                  label: String(values.label || "").trim(),
                  priority: Number(values.priority || 50),
                  kind: values.kind || "mixed"
                };
              }

              if (!payload) {
                throw new Error(values.mode === "rclone" ? "Rclone root requires a remote name." : "SMB root requires a connection and share name.");
              }

              if (originalPath) {
                await updateRoot({ ...payload, original_path: originalPath });
              } else {
                await addRoot(payload);
              }
              await refreshSettings();
              setRootModalOpen(false);
              setEditingRoot(null);
              rootForm.resetFields();
              message.success(originalPath ? "Connected folder updated." : "Connected folder added.");
            } catch (error) {
              message.error(error.message);
            }
          }}
        >
          <Form.Item name="original_path" hidden>
            <Input />
          </Form.Item>
          <Form.Item name="mode" label="Source Type">
            <Select
              options={[
                { label: "Local filesystem", value: "local" },
                { label: "SMB connection", value: "smb" },
                { label: "Rclone remote", value: "rclone" }
              ]}
            />
          </Form.Item>

          <Form.Item noStyle shouldUpdate={(prev, next) => prev.mode !== next.mode}>
            {({ getFieldValue }) =>
              getFieldValue("mode") === "smb" ? (
                <>
                  <Form.Item name="connection_id" label="SMB Connection" rules={[{ required: true }]}>
                    <Select
                      placeholder="Choose a saved SMB connection"
                      options={connections.map((item) => ({ label: item.label, value: item.id }))}
                    />
                  </Form.Item>
                  <Form.Item name="share_name" label="Share Name">
                    <Input placeholder={selectedRootConnection?.share_name || "DATA"} />
                  </Form.Item>
                  <Form.Item name="share_path" label="Folder Path Inside Share">
                    <Input placeholder="/Movies" />
                  </Form.Item>
                </>
              ) : getFieldValue("mode") === "rclone" ? (
                <>
                  <Form.Item name="rclone_remote" label="Rclone Remote" rules={[{ required: true }]}>
                    <Select placeholder="Choose a saved Rclone connection">
                      {rcloneConnections.map((conn) => (
                        <Select.Option key={conn.id} value={conn.rclone_name}>
                          {conn.label} ({conn.rclone_name})
                        </Select.Option>
                      ))}
                    </Select>
                  </Form.Item>
                  <Form.Item name="rclone_mount_path" label="Mounted Path Alias">
                    <Input placeholder="/volume2/DATA/rclone/gdrive" />
                  </Form.Item>
                  <Form.Item label="Folder Picker">
                    <Space.Compact style={{ width: "100%" }}>
                      <Form.Item name="rclone_path" noStyle>
                        <Input placeholder="/Movies" />
                      </Form.Item>
                      <Button
                        onClick={() => {
                          const remote = getFieldValue("rclone_remote");
                          if (!remote) {
                            message.error("Choose a remote first.");
                            return;
                          }
                          setPathBrowser({
                            open: true,
                            mode: "rclone",
                            loading: false,
                            error: "",
                            path: getFieldValue("rclone_path") || "/",
                            parent: null,
                            breadcrumbs: [],
                            entries: [],
                            favorites: [],
                            connectionId: remote,
                            shareName: "",
                          });
                        }}
                      >
                        Browse
                      </Button>
                    </Space.Compact>
                  </Form.Item>
                </>
              ) : (
                <Form.Item label="Filesystem Path" required>
                  <Space.Compact style={{ width: "100%" }}>
                    <Form.Item name="path" noStyle rules={[{ required: true }]}>
                      <Input placeholder="/mnt/library/incoming" />
                    </Form.Item>
                    <Button onClick={() => loadLocalPathBrowser(rootForm.getFieldValue("path"))}>Choose Folder</Button>
                  </Space.Compact>
                </Form.Item>
              )
            }
          </Form.Item>

          <Form.Item noStyle shouldUpdate={(prev, next) => prev.mode !== next.mode || prev.connection_id !== next.connection_id}>
            {({ getFieldValue }) =>
              getFieldValue("mode") === "smb" ? (
                <Form.Item label="Folder Picker">
                  <Button
                    onClick={() => {
                      const connectionId = getFieldValue("connection_id");
                      if (!connectionId) {
                        message.error("Choose an SMB connection first.");
                        return;
                      }
                      loadSmbPathBrowser({
                        connectionId,
                        shareName: getFieldValue("share_name"),
                        path: getFieldValue("share_path") || "/",
                      });
                    }}
                  >
                    Choose Folder
                  </Button>
                </Form.Item>
              ) : null
            }
          </Form.Item>

          <Form.Item name="label" label="Label">
            <Input placeholder="Incoming Movies" />
          </Form.Item>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="priority" label="Priority">
                <InputNumber min={0} max={999} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="kind" label="Kind">
                <Select options={ROOT_KIND_OPTIONS} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      <Modal
        open={connectionModalOpen}
        title={editingConnection ? "Edit SMB Connection" : "New SMB Connection"}
        okText={editingConnection ? "Save Changes" : "Save Connection"}
        confirmLoading={savingConnection}
        onCancel={() => setConnectionModalOpen(false)}
        onOk={() => connectionForm.submit()}
      >
        <Form
          form={connectionForm}
          layout="vertical"
          onFinish={async (values) => {
            setSavingConnection(true);
            try {
              const payload = { ...values };
              if (editingConnection?.has_password && !String(payload.password || "").trim()) {
                delete payload.password;
              }

              await saveLanConnection(payload);
              await refreshSettings();
              setConnectionModalOpen(false);
              setEditingConnection(null);
              connectionForm.resetFields();
              message.success("SMB connection saved.");
            } catch (error) {
              message.error(error.message);
            } finally {
              setSavingConnection(false);
            }
          }}
        >
          <Form.Item name="id" hidden>
            <Input />
          </Form.Item>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item name="label" label="Label">
                <Input placeholder="NAS Download Share" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="host" label="Host" rules={[{ required: true }]}>
                <Input placeholder="nas.local" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item name="port" label="Port">
                <InputNumber min={1} max={65535} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="version" label="SMB Version">
                <Select options={SMB_VERSION_OPTIONS} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item name="share_name" label="Default Share Name">
                <Input placeholder="Download" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="base_path" label="Base Path">
                <Input placeholder="/Movies" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item name="username" label="Username" rules={[{ required: true }]}>
                <Input placeholder="media" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="domain" label="Domain">
                <Input placeholder="WORKGROUP" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item
            name="password"
            label={editingConnection?.has_password ? "Password (leave blank to keep current)" : "Password"}
          >
            <Input.Password placeholder="Password" />
          </Form.Item>
          <Form.Item name="enabled" label="Enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={rcloneModalOpen}
        title={editingRclone ? "Edit Rclone Connection" : "New Rclone Connection"}
        okText={editingRclone ? "Save Changes" : "Save Connection"}
        confirmLoading={savingRclone}
        onCancel={() => setRcloneModalOpen(false)}
        onOk={() => rcloneForm.submit()}
      >
        <Form
          form={rcloneForm}
          layout="vertical"
          onFinish={async (values) => {
            setSavingRclone(true);
            try {
              let config = {};
              try {
                config = JSON.parse(values.config_json || "{}");
              } catch {
                throw new Error("Invalid JSON in Config field.");
              }

              const payload = {
                id: values.id,
                label: values.label,
                rclone_name: values.rclone_name,
                config,
                enabled: values.enabled
              };

              await saveRcloneConnection(payload);
              await refreshSettings();
              setRcloneModalOpen(false);
              setEditingRclone(null);
              rcloneForm.resetFields();
              message.success("Rclone connection saved.");
            } catch (error) {
              message.error(error.message);
            } finally {
              setSavingRclone(false);
            }
          }}
        >
          <Form.Item name="id" hidden>
            <Input />
          </Form.Item>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item name="label" label="Label" rules={[{ required: true }]}>
                <Input placeholder="Google Drive Personal" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="rclone_name" label="Rclone Remote Name" rules={[{ required: true }]}>
                <Input placeholder="gdrive" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="config_json" label="Config (JSON)" rules={[{ required: true }]}>
            <TextArea rows={8} placeholder={'{\n  "type": "drive",\n  "client_id": "...",\n  "client_secret": "...",\n  "scope": "drive",\n  "token": "..."\n}'} />
          </Form.Item>
          <Alert
            type="info"
            showIcon
            message="Configuration Guide"
            description={
              <div style={{ fontSize: "12px" }}>
                <p>Rclone is a tool to sync files with cloud storage. You have two ways to get this JSON:</p>
                
                <div style={{ fontWeight: 'bold', marginTop: '8px' }}>Option A: Export from your local machine</div>
                <p>If you already have Rclone installed, run this command to get the JSON:</p>
                <div style={{ margin: '4px 0' }}>
                  <Text code copyable>rclone config show YOUR_NAME --dump json</Text>
                </div>

                <div style={{ fontWeight: 'bold', marginTop: '12px' }}>Option B: Use a template</div>
                <p>If you are new to Rclone, pick a template below and fill in your credentials:</p>
                <Space wrap style={{ marginTop: '4px' }}>
                  <Button size="small" onClick={() => {
                    rcloneForm.setFieldsValue({
                      config_json: JSON.stringify({
                        type: "drive",
                        scope: "drive",
                        client_id: "YOUR_CLIENT_ID",
                        client_secret: "YOUR_CLIENT_SECRET",
                        token: '{"access_token":"...","token_type":"Bearer","refresh_token":"...","expiry":"..."}'
                      }, null, 2)
                    });
                  }}>Google Drive</Button>
                  <Button size="small" onClick={() => {
                    rcloneForm.setFieldsValue({
                      config_json: JSON.stringify({
                        type: "onedrive",
                        client_id: "YOUR_CLIENT_ID",
                        client_secret: "YOUR_CLIENT_SECRET",
                        token: '{"access_token":"...","token_type":"Bearer","refresh_token":"...","expiry":"..."}'
                      }, null, 2)
                    });
                  }}>OneDrive</Button>
                  <Button size="small" type="link" href="https://rclone.org/downloads/" target="_blank">Download Rclone</Button>
                </Space>
                
                <p style={{ marginTop: "12px" }}>
                  <b>Note:</b> For cloud services (Drive, OneDrive), you usually need to run <code>rclone config</code> once on a machine with a browser to get the <code>token</code>.
                </p>
              </div>
            }
          />
          <Form.Item name="enabled" label="Enabled" valuePropName="checked" style={{ marginTop: 16 }}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <PathBrowserModal
        state={pathBrowser}
        onCancel={() =>
          setPathBrowser({
            open: false,
            mode: "local",
            loading: false,
            error: "",
            path: "",
            parent: null,
            breadcrumbs: [],
            entries: [],
            favorites: [],
            connectionId: "",
            shareName: "",
          })
        }
        onBrowse={({ path, shareName, scope }) => {
          if (pathBrowser.mode === "smb") {
            return loadSmbPathBrowser({
              connectionId: pathBrowser.connectionId,
              shareName,
              path,
              scope,
            });
          }
          return loadLocalPathBrowser(path);
        }}
        onUseCurrent={() => {
          if (pathBrowser.mode === "smb") {
            rootForm.setFieldsValue({
              connection_id: pathBrowser.connectionId,
              share_name: pathBrowser.shareName || rootForm.getFieldValue("share_name"),
              share_path: pathBrowser.path || "/",
            });
          } else {
            rootForm.setFieldsValue({ path: pathBrowser.path });
          }
          setPathBrowser({
            open: false,
            mode: "local",
            loading: false,
            error: "",
            path: "",
            parent: null,
            breadcrumbs: [],
            entries: [],
            favorites: [],
            connectionId: "",
            shareName: "",
          });
        }}
      />
    </Flex>
  );
}
