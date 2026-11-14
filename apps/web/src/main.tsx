import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Analytics from "./app/Analytics";
import Inbox from "./app/Inbox";
import JobDetail from "./app/JobDetail";
import Login from "./app/Login";
import Messages from "./app/Messages";
import Onboarding from "./app/Onboarding";
import Panel from "./app/Panel";
import Pipeline from "./app/Pipeline";
import { RunList, RunView } from "./app/Runs";
import Settings from "./app/Settings";
import Studio from "./app/Studio";
import Layout from "./components/Layout";
import { getToken } from "./lib/api/client";
import "./styles.css";

function Private({ children }: { children: React.ReactElement }) {
  return getToken() ? children : <Navigate to="/login" replace />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/panel" element={<Panel />} />
        <Route path="/onboarding" element={<Private><Onboarding /></Private>} />
        <Route element={<Private><Layout /></Private>}>
          <Route path="/inbox" element={<Inbox />} />
          <Route path="/jobs/:id" element={<JobDetail />} />
          <Route path="/studio/:id" element={<Studio />} />
          <Route path="/pipeline" element={<Pipeline />} />
          <Route path="/messages" element={<Messages />} />
          <Route path="/runs" element={<RunList />} />
          <Route path="/runs/:id" element={<RunView />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<Navigate to="/inbox" replace />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
