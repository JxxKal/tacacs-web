import {
  Alert,
  Badge,
  Card,
  Group,
  Loader,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { IconAlertCircle, IconInfoCircle } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";

import { useMe } from "@/api/auth";
import { useMyAccess, type MyAccessGroup } from "@/api/effectivePermissions";
import { errorToMessage } from "@/utils/errors";

export function DashboardPage() {
  const { t } = useTranslation();
  const me = useMe();
  const access = useMyAccess();
  if (!me.data) return null;
  return (
    <Stack>
      <Title order={2}>
        {t("dashboard.welcome", { username: me.data.username })}
      </Title>
      <Card withBorder padding="lg" maw={520}>
        <Stack gap="xs">
          <Text>{t("dashboard.role", { role: me.data.role })}</Text>
          <Text>{t("dashboard.authMethod", { method: me.data.auth_method })}</Text>
        </Stack>
      </Card>

      <Card withBorder padding="lg" maw={820}>
        <Stack gap="xs">
          <Title order={4}>{t("dashboard.accessTitle")}</Title>
          <Text c="dimmed" size="sm">
            {t("dashboard.accessSubtitle")}
          </Text>
          {access.isPending && <Loader size="sm" />}
          {access.isError && (
            <Alert
              color="red"
              icon={<IconAlertCircle size={16} />}
              title={t("common.error")}
            >
              {errorToMessage(access.error)}
            </Alert>
          )}
          {access.data && !access.data.tacacs_username && (
            <Alert
              color="blue"
              variant="light"
              icon={<IconInfoCircle size={16} />}
            >
              {t("dashboard.accessNotTacacs")}
            </Alert>
          )}
          {access.data &&
            access.data.tacacs_username &&
            access.data.groups.length === 0 && (
              <Alert color="yellow" variant="light">
                {t("dashboard.accessNoGrants", {
                  username: access.data.tacacs_username,
                })}
              </Alert>
            )}
          {access.data && access.data.groups.length > 0 && (
            <Stack gap="xs">
              {access.data.groups.map((g) => (
                <AccessGroupCard key={g.device_group_id} group={g} />
              ))}
            </Stack>
          )}
        </Stack>
      </Card>
    </Stack>
  );
}

function AccessGroupCard({ group }: { group: MyAccessGroup }) {
  const { t } = useTranslation();
  const moreCount = Math.max(group.device_count - group.devices.length, 0);
  return (
    <Card withBorder padding="md" radius="sm">
      <Stack gap="xs">
        <Group justify="space-between" wrap="nowrap">
          <Group gap="xs" wrap="nowrap">
            <Text fw={500}>{group.device_group_name}</Text>
            <Badge variant="filled" color="indigo" size="sm">
              {t("dashboard.accessPrivLvl", { lvl: group.tacacs_priv_lvl })}
            </Badge>
            <Badge variant="light" size="sm">
              {group.privilege_profile_name}
            </Badge>
            {group.via_ad_group_name && (
              <Badge variant="outline" size="sm">
                {t("dashboard.accessViaGroup", {
                  group: group.via_ad_group_name,
                })}
              </Badge>
            )}
          </Group>
          <Text size="xs" c="dimmed">
            {t("dashboard.accessDeviceCount", { count: group.device_count })}
          </Text>
        </Group>
        {group.devices.length > 0 ? (
          <Group gap={6}>
            {group.devices.map((d) => (
              <Badge key={d.id} variant="default" size="sm">
                {d.name}{" "}
                <Text component="span" c="dimmed" size="xs">
                  ({d.ip_or_cidr})
                </Text>
              </Badge>
            ))}
            {moreCount > 0 && (
              <Text size="xs" c="dimmed">
                {t("dashboard.accessMoreDevices", { count: moreCount })}
              </Text>
            )}
          </Group>
        ) : (
          <Text size="xs" c="dimmed">
            {t("dashboard.accessGroupEmpty")}
          </Text>
        )}
      </Stack>
    </Card>
  );
}
