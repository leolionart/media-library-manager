import React from "react";
import ReactDOM from "react-dom/client";
import { App, ConfigProvider } from "antd";
import "antd/dist/reset.css";
import { antTheme } from "./theme";
import DashboardApp from "./App.jsx";
import "./styles.css";

class RootErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error) {
    console.error("Root render failed", error);
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 24, color: "#fff", fontFamily: "\"IBM Plex Sans\", sans-serif" }}>
          <h1 style={{ marginTop: 0 }}>Dashboard failed to render</h1>
          <pre style={{ whiteSpace: "pre-wrap" }}>{String(this.state.error?.stack || this.state.error)}</pre>
        </div>
      );
    }

    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <RootErrorBoundary>
      <ConfigProvider theme={antTheme}>
        <App>
          <DashboardApp />
        </App>
      </ConfigProvider>
    </RootErrorBoundary>
  </React.StrictMode>
);
