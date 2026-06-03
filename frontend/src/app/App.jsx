import { Navigate, Route, Routes } from "react-router-dom";
import { Spin } from "@arco-design/web-react";
import { Suspense } from "react";
import { SchedulingSessionProvider } from "../features/scheduling/SchedulingSessionProvider.jsx";
import { ControlPlaneProvider } from "../layout/ControlPlaneProvider.jsx";
import { ConsoleLayout } from "../layout/ConsoleLayout.jsx";
import { ThemeProvider } from "../theme/ThemeProvider.jsx";
import { routes } from "./routes.jsx";

export function App() {
  return (
    <ThemeProvider>
      <ControlPlaneProvider>
        <SchedulingSessionProvider>
          <ConsoleLayout>
            <Suspense fallback={<div className="tj-route-loading"><Spin dot /> 加载控制台页面...</div>}>
              <Routes>
                {routes.map((route) => {
                  const Page = route.Component;
                  return <Route key={route.key} path={route.path} element={<Page />} />;
                })}
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </ConsoleLayout>
        </SchedulingSessionProvider>
      </ControlPlaneProvider>
    </ThemeProvider>
  );
}
