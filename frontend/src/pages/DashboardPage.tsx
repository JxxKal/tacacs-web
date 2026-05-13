import { Card, Stack, Text, Title } from "@mantine/core";
import { useTranslation } from "react-i18next";

import { useMe } from "@/api/auth";

export function DashboardPage() {
  const { t } = useTranslation();
  const me = useMe();
  if (!me.data) return null;
  return (
    <Stack>
      <Title order={2}>{t("dashboard.welcome", { username: me.data.username })}</Title>
      <Card withBorder padding="lg" maw={520}>
        <Stack gap="xs">
          <Text>{t("dashboard.role", { role: me.data.role })}</Text>
          <Text>{t("dashboard.authMethod", { method: me.data.auth_method })}</Text>
        </Stack>
      </Card>
    </Stack>
  );
}
