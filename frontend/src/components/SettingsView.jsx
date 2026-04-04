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
  deleteLanConnection,
  discoverLanDevices,
  fetchSettingsState,
  removeRoot,
  runManualSync,
  saveIntegrations,
  saveLanConnection,
  testIntegrations,
  testLanConnection,
  updateRoot
} from "../api";

const { Text } = Typography;

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
  lan_connections: { smb: [] },
  sync_result: null,
  activity_log: []
};

function formatDate(value) {
  if (!value) return "Never";
  return new Date(value).toLocaleString();
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

function buildRootFormValues(root) {
  if (!root) {
    return { mode: "local", priority: 50, kind: "mixed", share_path: "/" };
  }

  if (root.storage_uri) {
    const parsed = new URL(root.storage_uri);
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
  }

  return {
    mode: "local",
    original_path: root.path,
    path: root.path,
    label: root.label || "",
    priority: Number(root.priority || 50),
    kind: root.kind || "mixed",
    share_path: "/",
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
  const [savingIntegrations, setSavingIntegrations] = useState(false);
  const [testingIntegration, setTestingIntegration] = useState("");
  const [testingConnectionId, setTestingConnectionId] = useState("");
  const [savingConnection, setSavingConnection] = useState(false);
  const [deletingConnectionId, setDeletingConnectionId] = useState("");
  const [removingRootPath, setRemovingRootPath] = useState("");
  const [rootForm] = Form.useForm();
  const [connectionForm] = Form.useForm();
  const [integrationsForm] = Form.useForm();
  const [lanTestResults, setLanTestResults] = useState({});

  const connections = state.lan_connections?.smb || [];
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

  useEffect(() => {
    refreshSettings()
      .catch((error) => message.error(error.message))
      .finally(() => setLoading(false));
  }, [message, integrationsForm]);

  const providerCards = ["radarr", "sonarr"].map((provider) => ({
    provider,
    testResult: integrationTestResults?.[provider] || null
  }));

  const rootColumns = [
    {
      title: "Label",
      dataIndex: "label",
      key: "label",
      render: (value, record) => (
        <Space direction="vertical" size={4}>
          <Text strong>{value}</Text>
          <Space size={[4, 4]} wrap>
            <Tag color="gold" bordered={false}>
              P{record.priority}
            </Tag>
            <Tag>{record.kind}</Tag>
            {record.storage_uri ? <Tag color="processing">SMB</Tag> : <Tag>Local</Tag>}
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
        <Text type="secondary">{record.connection_label || record.share_name || "Direct filesystem path"}</Text>
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
                                label: device.hostname || device.address || "",
                                host: device.hostname || device.address || "",
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
                          title={device.hostname || device.address || "Unknown device"}
                          description={
                            <Space size={[8, 8]} wrap>
                              {device.address ? <Text className="mono">{device.address}</Text> : null}
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
          initialValues={{ mode: "local", priority: 50, kind: "mixed", share_path: "/" }}
          onFinish={async (values) => {
            try {
              const originalPath = String(values.original_path || editingRoot?.path || "").trim();
              const payload =
                values.mode === "smb"
                  ? createSmbRootPayload(values, selectedRootConnection)
                  : {
                      path: String(values.path || "").trim(),
                      label: String(values.label || "").trim(),
                      priority: Number(values.priority || 50),
                      kind: values.kind || "mixed"
                    };

              if (!payload) {
                throw new Error("SMB root requires a connection and share name.");
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
                { label: "SMB connection", value: "smb" }
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
              ) : (
                <Form.Item name="path" label="Filesystem Path" rules={[{ required: true }]}>
                  <Input placeholder="/mnt/library/incoming" />
                </Form.Item>
              )
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
    </Flex>
  );
}
