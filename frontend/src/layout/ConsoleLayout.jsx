import { Button, Layout, Menu, Space, Tag, Typography } from "@arco-design/web-react";
import {
  IconBranch,
  IconCodeSandbox,
  IconRefresh,
  IconRobot,
} from "@arco-design/web-react/icon";
import clsx from "clsx";
import { useMemo } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { routes } from "../app/routes.jsx";
import { shortTime } from "../utils/format.js";
import { useControlPlaneContext } from "./ControlPlaneProvider.jsx";

const { Sider, Header, Content } = Layout;

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
            <Typography.Text>算力控制</Typography.Text>
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
            <div className="tj-product-pill">
              <IconBranch />
              <span>算力网络资源调度智能体</span>
            </div>
            <div className="tj-console-title">
              <IconCodeSandbox />
              <span>企业控制台</span>
            </div>
          </div>
          <Space size={14} className="tj-header-status">
            <Tag color={error ? "red" : "green"} className={clsx("tj-status-tag", error && "is-error")}>
              <span className="tj-status-dot" />
              {error ? "API 异常" : "API 正常"}
            </Tag>
            <Tag color={state.modelLoaded ? "purple" : "orangered"} className="tj-model-tag">
              <IconRobot />
              <span><b>模型 {state.modelLoaded ? "已加载" : state.model?.status ?? "未知"}</b><small>Hermes LLM</small></span>
            </Tag>
            <span className="tj-header-divider" />
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
