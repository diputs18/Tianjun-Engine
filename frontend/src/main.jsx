import React from "react";
import { createRoot } from "react-dom/client";
import { DashboardPage } from "./components/DashboardPage.jsx";
import * as api from "./api.js";
import "./dashboard.css";

window.tianjunApi = api;

createRoot(document.getElementById("root")).render(
  <DashboardPage />,
);
