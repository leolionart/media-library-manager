import { useMemo, useState } from "react";
import { Layout, Menu, Typography } from "antd";
import { AppstoreOutlined, ClearOutlined, DashboardOutlined, LinkOutlined, SettingOutlined } from "@ant-design/icons";
import { FileCleanupView } from "./components/FileCleanupView";
import { PathRepairView } from "./components/PathRepairView";
import { OverviewView } from "./components/OverviewView";
import { OperationsView } from "./components/OperationsView";
import { SettingsView } from "./components/SettingsView";

const VIEW_STORAGE_KEY = "media-library-manager.active-view";

const { Header, Sider, Content } = Layout;
const { Title, Text } = Typography;

const VIEW_META = {
  overview: {
    title: "Overview",
    description:
      "Monitor library health, provider status, current processing, and recent activity from a single dashboard."
  },
  operations: {
    title: "Media Management",
    description:
      "Scan connected folders, review duplicate suggestions, and move a selected folder into the correct Radarr or Sonarr title."
  },
  cleanup: {
    title: "Duplication Clean",
    description:
      "Review movie folders that contain multiple candidate video files and delete the extras without leaving the dashboard."
  },
  repair: {
    title: "Library Path Repair",
    description:
      "Detect Radarr or Sonarr items whose stored paths no longer exist and remap them to matching folders from connected roots."
  },
  settings: {
    title: "Settings",
    description:
      "Manage connected roots, SMB profiles, provider integrations, and sync behavior from the same control surface."
  }
};

export function DashboardApp() {
  const [view, setView] = useState(() => {
    if (typeof window === "undefined") return "overview";
    const savedView = window.localStorage.getItem(VIEW_STORAGE_KEY);
    return savedView && VIEW_META[savedView] ? savedView : "overview";
  });
  const meta = useMemo(() => VIEW_META[view] || VIEW_META.operations, [view]);

  const handleViewChange = (nextView) => {
    setView(nextView);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(VIEW_STORAGE_KEY, nextView);
    }
  };

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
            { key: "overview", icon: <DashboardOutlined />, label: "Overview" },
            { key: "operations", icon: <AppstoreOutlined />, label: "Media Management" },
            { key: "cleanup", icon: <ClearOutlined />, label: "Duplication Clean" },
            { key: "repair", icon: <LinkOutlined />, label: "Library Path Repair" },
            { key: "settings", icon: <SettingOutlined />, label: "Settings" }
          ]}
          onClick={({ key }) => handleViewChange(key)}
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
          {view === "overview" ? (
            <OverviewView />
          ) : view === "operations" ? (
            <OperationsView />
          ) : view === "cleanup" ? (
            <FileCleanupView />
          ) : view === "repair" ? (
            <PathRepairView />
          ) : (
            <SettingsView />
          )}
        </Content>
      </Layout>
    </Layout>
  );
}

export default DashboardApp;
