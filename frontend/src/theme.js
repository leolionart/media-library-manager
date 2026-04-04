import { theme } from "antd";

export const antTheme = {
  algorithm: theme.darkAlgorithm,
  hashed: false,
  token: {
    colorPrimary: "#e5a00d",
    colorInfo: "#e5a00d",
    colorSuccess: "#4caf50",
    colorWarning: "#e5a00d",
    colorError: "#f44336",
    colorBgBase: "#111113",
    colorBgContainer: "#282830",
    colorBgElevated: "#2f2f37",
    colorBgLayout: "#111113",
    colorFillAlter: "#32323c",
    colorFillSecondary: "#32323c",
    colorBorder: "#44444e",
    colorBorderSecondary: "#3a3a44",
    colorText: "#eaeaea",
    colorTextSecondary: "#a0a0a0",
    colorTextTertiary: "#6a6a6a",
    colorTextQuaternary: "#6a6a6a",
    borderRadius: 12,
    borderRadiusSM: 10,
    borderRadiusLG: 16,
    controlHeight: 40,
    controlHeightLG: 44,
    controlHeightSM: 34,
    wireframe: false,
    fontFamily: "\"IBM Plex Sans\", \"Segoe UI\", sans-serif",
    boxShadow: "0 10px 30px rgba(0, 0, 0, 0.35)"
  },
  components: {
    Layout: {
      bodyBg: "#111113",
      headerBg: "transparent",
      siderBg: "#18181e",
      triggerBg: "#18181e"
    },
    Card: {
      bodyPadding: 24,
      headerBg: "transparent"
    },
    Table: {
      headerBg: "#2d2d35",
      headerColor: "#6a6a6a",
      rowHoverBg: "#32323c",
      borderColor: "#3a3a44",
      headerBorderRadius: 16,
      cellPaddingBlock: 14,
      cellPaddingInline: 16
    },
    Modal: {
      contentBg: "#282830",
      headerBg: "#282830",
      footerBg: "#282830"
    },
    Button: {
      borderColorDisabled: "#3a3a44",
      defaultBorderColor: "#44444e",
      defaultColor: "#eaeaea",
      defaultBg: "#282830"
    },
    Input: {
      activeBg: "#32323c",
      hoverBg: "#32323c",
      activeBorderColor: "#e5a00d",
      hoverBorderColor: "#e5a00d"
    },
    Select: {
      optionSelectedBg: "rgba(229, 160, 13, 0.16)"
    },
    Switch: {
      colorPrimary: "#e5a00d",
      colorPrimaryHover: "#cc8b00",
      colorTextQuaternary: "#44444e",
      trackHeight: 28,
      trackMinWidth: 48,
      trackPadding: 3
    },
    Checkbox: {
      colorPrimary: "#e5a00d",
      colorPrimaryHover: "#cc8b00",
      colorBorder: "#55555f",
      borderRadiusSM: 8
    }
  }
};
