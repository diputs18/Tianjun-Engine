import { Button, Dropdown, Layout, Menu, Space, Tag, Typography } from "@arco-design/web-react";
import {
  IconCodeSandbox,
  IconDesktop,
  IconMoon,
  IconRefresh,
  IconRobot,
  IconSun,
} from "@arco-design/web-react/icon";
import clsx from "clsx";
import { useMemo } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { routes } from "../app/routes.jsx";
import { useTheme } from "../theme/ThemeProvider.jsx";
import { shortTime } from "../utils/format.js";
import { useControlPlaneContext } from "./ControlPlaneProvider.jsx";

const { Sider, Header, Content } = Layout;

function ThemeSwitcher() {
  const { mode, setMode, isDark } = useTheme();

  return (
    <Dropdown
      droplist={
        <Menu selectedKeys={[mode]} onClickMenuItem={(key) => setMode(key)}>
          <Menu.Item key="light"><IconSun /> 浅色</Menu.Item>
          <Menu.Item key="dark"><IconMoon /> 暗色</Menu.Item>
          <Menu.Item key="system"><IconDesktop /> 跟随系统</Menu.Item>
        </Menu>
      }
      trigger="click"
    >
      <Button className="tj-theme-button" type="text" icon={isDark ? <IconMoon /> : <IconSun />}>
        {mode === "system" ? "系统" : isDark ? "暗色" : "浅色"}
      </Button>
    </Dropdown>
  );
}

export function ConsoleLayout({ children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { error, refresh, state, updatedAt } = useControlPlaneContext();
  const selectedKey = useMemo(() => {
    return routes.find((route) => route.path === location.pathname)?.key ?? "overview";
  }, [location.pathname]);

  return (
    <Layout className="tj-console">
      <Sider className="tj-sider" width={240}>
        <div className="tj-brand">
          <span className="tj-brand-mark"><IconCodeSandbox /></span>
          <div>
            <Typography.Title heading={5}>天钧</Typography.Title>
            <Typography.Text>算力调度</Typography.Text>
          </div>
        </div>
        <Menu
          className="tj-menu"
          selectedKeys={[selectedKey]}
          onClickMenuItem={(key) => {
            const route = routes.find((item) => item.key === key);
            if (route) navigate(route.path);
          }}
        >
          {routes.map((route) => {
            const Icon = route.icon;
            return (
              <Menu.Item key={route.key}>
                <Icon /> <span>{route.label}</span>
              </Menu.Item>
            );
          })}
        </Menu>
        <button className="tj-sider-collapse" type="button" aria-label="collapse sidebar">‹</button>
      </Sider>
      <Layout className="tj-main-layout">
        <Header className="tj-header">
          <div className="tj-header-center">
            <div className="tj-header-title">
              <span className="tj-header-title-main">天钧算力调度</span>
              <span className="tj-header-title-sub">控制台</span>
            </div>
          </div>
          <Space size={8} className="tj-header-status">
            <ThemeSwitcher />
            <Tag color={error ? "red" : "green"} className={clsx("tj-state-pill", error && "is-error")}>
              <span className="tj-status-dot" />
              <span>{error ? "API 异常" : "API 正常"}</span>
            </Tag>
            <Tag color={state.modelLoaded ? "purple" : "orangered"} className="tj-state-pill tj-model-pill">
              <IconRobot />
              <span>模型 {state.modelLoaded ? "已加载" : state.model?.status ?? "未知"}</span>
            </Tag>
            <Tag color={state.llmEnabled ? "arcoblue" : "orange"} className="tj-state-pill tj-llm-pill">
              <span>LLM {state.llmEnabled ? "Hermes" : "规则回退"}</span>
            </Tag>
            <Button className="tj-sync-button" icon={<IconRefresh />} onClick={() => void refresh()}>
              同步 {shortTime(updatedAt)}
            </Button>
          </Space>
        </Header>
        <Content className="tj-content">{children}</Content>
      </Layout>
    </Layout>
  );
}
