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
    colorTextQuaternary: "#6a6a6a"
  },
  components: {
    Layout: {
      bodyBg: "#111113",
      headerBg: "transparent",
      siderBg: "#18181e",
      triggerBg: "#18181e"
    },
    Menu: {
      darkItemBg: "#18181e",
      darkSubMenuItemBg: "#18181e",
      darkPopupBg: "#18181e",
      darkItemColor: "#a0a0a0",
      darkItemHoverColor: "#eaeaea",
      darkItemHoverBg: "rgba(229, 160, 13, 0.08)",
      darkItemSelectedBg: "#d09329",
      darkItemSelectedColor: "#ffffff"
    },
    Card: {
      headerBg: "transparent"
    },
    Table: {
      headerBg: "#2d2d35",
      headerColor: "#6a6a6a",
      rowHoverBg: "#32323c",
      borderColor: "#3a3a44"
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
      colorPrimaryHover: "#cc8b00"
    },
    Checkbox: {
      colorPrimary: "#e5a00d",
      colorPrimaryHover: "#cc8b00",
      colorBorder: "#55555f",
      colorBgContainer: "#282830"
    }
  }
};
