import { Navigate, Route, Routes } from "react-router-dom";

import { type ReactNode } from "react";

import { AppShell } from "@/components/AppShell";
import { RequireSession } from "@/components/RequireSession";
import { AuthorizationsPage } from "@/pages/AuthorizationsPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { DeviceGroupsPage } from "@/pages/DeviceGroupsPage";
import { DevicesPage } from "@/pages/DevicesPage";
import { LoginPage } from "@/pages/LoginPage";
import { PrivilegeProfilesPage } from "@/pages/PrivilegeProfilesPage";
import { SettingsPage } from "@/pages/SettingsPage";

const guarded = (page: ReactNode) => (
  <RequireSession>
    <AppShell>{page}</AppShell>
  </RequireSession>
);

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={guarded(<DashboardPage />)} />
      <Route path="/device-groups" element={guarded(<DeviceGroupsPage />)} />
      <Route
        path="/privilege-profiles"
        element={guarded(<PrivilegeProfilesPage />)}
      />
      <Route path="/devices" element={guarded(<DevicesPage />)} />
      <Route path="/authorizations" element={guarded(<AuthorizationsPage />)} />
      <Route path="/settings" element={guarded(<SettingsPage />)} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
