import { Button, Layout, Menu, Space, Tag, Typography } from "@arco-design/web-react";
import { IconRefresh, IconThunderbolt } from "@arco-design/web-react/icon";
import clsx from "clsx";
import { useMemo } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { routes } from "../app/routes.jsx";
import { useControlPlaneContext } from "./ControlPlaneProvider.jsx";
import { shortTime } from "../utils/format.js";

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
      <Sider className="tj-sider" width={232}>
        <div className="tj-brand">
          <span className="tj-brand-mark"><IconThunderbolt /></span>
          <div>
            <Typography.Title heading={5}>Tianjun</Typography.Title>
            <Typography.Text>Compute Control</Typography.Text>
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
                <Icon /> {route.label}
              </Menu.Item>
            );
          })}
        </Menu>
      </Sider>
      <Layout>
        <Header className="tj-header">
          <div>
            <Typography.Text className="tj-kicker">算力网络资源调度智能体</Typography.Text>
            <Typography.Title heading={4}>企业控制台</Typography.Title>
          </div>
          <Space size={12}>
            <Tag color={error ? "red" : "green"} className={clsx("tj-status-tag", error && "is-error")}>
              {error ? "API 连接异常" : "API 正常"}
            </Tag>
            <Tag color={state.modelLoaded ? "arcoblue" : "orangered"}>
              模型 {state.model?.status ?? "unknown"}
            </Tag>
            <Tag color={state.llmEnabled ? "green" : "gray"}>
              Hermes {state.llmEnabled ? "LLM" : "规则"}
            </Tag>
            <Typography.Text type="secondary">同步 {shortTime(updatedAt)}</Typography.Text>
            <Button icon={<IconRefresh />} onClick={() => void refresh()}>
              刷新
            </Button>
          </Space>
        </Header>
        <Content className="tj-content">{children}</Content>
      </Layout>
    </Layout>
  );
}
