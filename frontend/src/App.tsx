import { Navigate, Route, Routes } from "react-router-dom";

import { type ReactNode } from "react";

import { AppShell } from "@/components/AppShell";
import { RequireSession } from "@/components/RequireSession";
import { AccountingPage } from "@/pages/AccountingPage";
import { AuditLogPage } from "@/pages/AuditLogPage";
import { AuthorizationsPage } from "@/pages/AuthorizationsPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { DeviceGroupsPage } from "@/pages/DeviceGroupsPage";
import { DevicesPage } from "@/pages/DevicesPage";
import { DeviceTemplatesPage } from "@/pages/DeviceTemplatesPage";
import { EffectivePermissionsPage } from "@/pages/EffectivePermissionsPage";
import { LoginPage } from "@/pages/LoginPage";
import { PrivilegeProfilesPage } from "@/pages/PrivilegeProfilesPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { SetupWizardPage } from "@/pages/SetupWizardPage";

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
      <Route
        path="/device-templates"
        element={guarded(<DeviceTemplatesPage />)}
      />
      <Route path="/authorizations" element={guarded(<AuthorizationsPage />)} />
      <Route
        path="/effective-permissions"
        element={guarded(<EffectivePermissionsPage />)}
      />
      <Route path="/accounting" element={guarded(<AccountingPage />)} />
      <Route path="/audit-log" element={guarded(<AuditLogPage />)} />
      <Route path="/settings" element={guarded(<SettingsPage />)} />
      <Route path="/setup" element={guarded(<SetupWizardPage />)} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
