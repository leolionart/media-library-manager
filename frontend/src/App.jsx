import { useMemo, useState } from "react";
import { Layout, Menu, Typography } from "antd";
import { AppstoreOutlined, SettingOutlined } from "@ant-design/icons";
import { OperationsView } from "./components/OperationsView";
import { SettingsView } from "./components/SettingsView";

const { Header, Sider, Content } = Layout;
const { Title, Text } = Typography;

const VIEW_META = {
  operations: {
    title: "Operations",
    description:
      "Scan connected folders, review duplicate suggestions, and move a selected folder into the correct Radarr or Sonarr title."
  },
  settings: {
    title: "Settings",
    description:
      "Manage connected roots, SMB profiles, provider integrations, and sync behavior from the same control surface."
  }
};

export function DashboardApp() {
  const [view, setView] = useState("operations");
  const meta = useMemo(() => VIEW_META[view] || VIEW_META.operations, [view]);

  return (
    <Layout className="app-shell-react">
      <Sider width={248} breakpoint="lg" collapsedWidth={0} theme="dark" className="app-sider">
        <div className="sidebar-brand-react">
          <div className="logo-react">M</div>
          <div>
            <div className="brand-title-react">Media Library Manager</div>
            <div className="brand-subtitle-react">Control Surface</div>
          </div>
        </div>
        <Menu
          mode="inline"
          theme="dark"
          selectedKeys={[view]}
          items={[
            { key: "operations", icon: <AppstoreOutlined />, label: "Operations" },
            { key: "settings", icon: <SettingOutlined />, label: "Settings" }
          ]}
          onClick={({ key }) => setView(key)}
        />
      </Sider>

      <Layout>
        <Header className="topbar-react">
          <div>
            <div className="eyebrow-react">Control Surface</div>
            <Title level={2} className="topbar-title-react">
              {meta.title}
            </Title>
            <Text type="secondary" className="topbar-subtitle-react">
              {meta.description}
            </Text>
          </div>
        </Header>

        <Content className="content-react">
          {view === "operations" ? <OperationsView /> : <SettingsView />}
        </Content>
      </Layout>
    </Layout>
  );
}

export default DashboardApp;
