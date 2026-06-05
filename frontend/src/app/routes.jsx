import {
  IconApps,
  IconBranch,
  IconDashboard,
  IconRobot,
  IconSafe,
  IconStorage,
} from "@arco-design/web-react/icon";
import { lazy } from "react";

const OverviewPage = lazy(() => import("../pages/OverviewPage.jsx").then((module) => ({ default: module.OverviewPage })));
const SchedulingPage = lazy(() => import("../pages/SchedulingPage.jsx").then((module) => ({ default: module.SchedulingPage })));
const WorkloadsPage = lazy(() => import("../pages/WorkloadsPage.jsx").then((module) => ({ default: module.WorkloadsPage })));
const InfrastructurePage = lazy(() => import("../pages/InfrastructurePage.jsx").then((module) => ({ default: module.InfrastructurePage })));
const ModelPolicyPage = lazy(() => import("../pages/ModelPolicyPage.jsx").then((module) => ({ default: module.ModelPolicyPage })));
const AuditSettingsPage = lazy(() => import("../pages/AuditSettingsPage.jsx").then((module) => ({ default: module.AuditSettingsPage })));

export const routes = [
  { path: "/", key: "overview", label: "概述", icon: IconDashboard, Component: OverviewPage },
  { path: "/scheduling", key: "scheduling", label: "调度工作台", icon: IconRobot, Component: SchedulingPage },
  { path: "/workloads", key: "workloads", label: "任务执行", icon: IconApps, Component: WorkloadsPage },
  { path: "/infrastructure", key: "infrastructure", label: "基础设施", icon: IconBranch, Component: InfrastructurePage },
  { path: "/model-policy", key: "model-policy", label: "模型与策略", icon: IconStorage, Component: ModelPolicyPage },
  { path: "/audit-settings", key: "audit-settings", label: "审计与设置", icon: IconSafe, Component: AuditSettingsPage },
];
