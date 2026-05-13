import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { RequireSession } from "@/components/RequireSession";
import { DashboardPage } from "@/pages/DashboardPage";
import { DeviceGroupsPage } from "@/pages/DeviceGroupsPage";
import { LoginPage } from "@/pages/LoginPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireSession>
            <AppShell>
              <DashboardPage />
            </AppShell>
          </RequireSession>
        }
      />
      <Route
        path="/device-groups"
        element={
          <RequireSession>
            <AppShell>
              <DeviceGroupsPage />
            </AppShell>
          </RequireSession>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
