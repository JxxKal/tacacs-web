import {
  Alert,
  Badge,
  Card,
  Group,
  Loader,
  Select,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { IconAlertCircle, IconInfoCircle } from "@tabler/icons-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  useEffectivePermissions,
  type EffectivePermissionCandidate,
  type EffectivePermissionEntry,
} from "@/api/effectivePermissions";
import { useUsers } from "@/api/principals";
import { errorToMessage } from "@/utils/errors";

export function EffectivePermissionsPage() {
  const { t } = useTranslation();
  const users = useUsers();
  const [userId, setUserId] = useState<number | null>(null);
  const perms = useEffectivePermissions(userId);

  const userOptions = useMemo(() => {
    return (users.data ?? []).map((u) => ({
      value: String(u.id),
      label: u.display_name
        ? `${u.sam_account_name} — ${u.display_name}`
        : u.sam_account_name,
    }));
  }, [users.data]);

  return (
    <Stack>
      <Stack gap={4}>
        <Title order={2}>{t("effective.title")}</Title>
        <Text c="dimmed" size="sm">
          {t("effective.subtitle")}
        </Text>
      </Stack>

      <Card withBorder padding="md">
        <Select
          label={t("effective.userPicker")}
          placeholder={t("effective.userPickerPlaceholder")}
          data={userOptions}
          value={userId === null ? null : String(userId)}
          onChange={(v) => setUserId(v ? Number(v) : null)}
          searchable
          clearable
          maxDropdownHeight={400}
          disabled={users.isPending}
        />
      </Card>

      {userId === null ? (
        <Card withBorder padding="xl">
          <Text c="dimmed">{t("effective.noUserSelected")}</Text>
        </Card>
      ) : perms.isPending ? (
        <Card withBorder padding="xl">
          <Loader />
        </Card>
      ) : perms.isError ? (
        <Alert color="red" icon={<IconAlertCircle size={16} />} title={t("common.error")}>
          {t("common.errorMessage", { message: errorToMessage(perms.error) })}
        </Alert>
      ) : perms.data && perms.data.length > 0 ? (
        <ResultsTable entries={perms.data} />
      ) : (
        <Card withBorder padding="xl">
          <Text c="dimmed">{t("effective.emptyState")}</Text>
        </Card>
      )}
    </Stack>
  );
}

function ResultsTable({ entries }: { entries: EffectivePermissionEntry[] }) {
  const { t } = useTranslation();
  return (
    <Card withBorder padding={0}>
      <Table verticalSpacing="sm" striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>{t("effective.deviceGroupHeader")}</Table.Th>
            <Table.Th>{t("effective.winningHeader")}</Table.Th>
            <Table.Th style={{ width: 110 }}>{t("effective.privLvlHeader")}</Table.Th>
            <Table.Th style={{ width: 140 }}>{t("effective.viaHeader")}</Table.Th>
            <Table.Th style={{ width: 200 }}>{t("effective.overriddenHeader")}</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {entries.map((row) => (
            <Row key={row.device_group_id} row={row} />
          ))}
        </Table.Tbody>
      </Table>
    </Card>
  );
}

function Row({ row }: { row: EffectivePermissionEntry }) {
  const { t } = useTranslation();
  const viaDirect = row.winning.principal_user_id !== null;
  return (
    <Table.Tr>
      <Table.Td>{row.device_group_name}</Table.Td>
      <Table.Td>
        <Text size="sm">profile #{row.winning.privilege_profile_id}</Text>
        <Text size="xs" c="dimmed">
          authz #{row.winning.authorization_id}
        </Text>
      </Table.Td>
      <Table.Td>
        <Badge size="lg" variant="light" color={privColor(row.winning.tacacs_priv_lvl)}>
          {row.winning.tacacs_priv_lvl}
        </Badge>
      </Table.Td>
      <Table.Td>
        <Badge variant="light" color={viaDirect ? "blue" : "grape"}>
          {viaDirect ? t("effective.viaDirect") : t("effective.viaAdGroup")}
        </Badge>
      </Table.Td>
      <Table.Td>
        {row.overridden.length === 0 ? (
          <Text c="dimmed">{t("effective.overriddenNone")}</Text>
        ) : (
          <OverriddenSummary candidates={row.overridden} />
        )}
      </Table.Td>
    </Table.Tr>
  );
}

function OverriddenSummary({
  candidates,
}: {
  candidates: EffectivePermissionCandidate[];
}) {
  const { t } = useTranslation();
  const lines = candidates.map((c) => {
    const kind = c.principal_user_id !== null
      ? t("effective.viaDirect")
      : t("effective.viaAdGroup");
    return `authz #${c.authorization_id}: priv-lvl ${c.tacacs_priv_lvl} (${kind})`;
  });
  return (
    <Tooltip label={lines.join(" / ")} multiline w={400} withArrow>
      <Group gap={4}>
        <Text size="sm">{t("effective.overriddenSummary", { count: candidates.length })}</Text>
        <IconInfoCircle size={14} />
      </Group>
    </Tooltip>
  );
}

function privColor(lvl: number): string {
  if (lvl >= 15) return "red";
  if (lvl >= 7) return "orange";
  if (lvl >= 1) return "yellow";
  return "gray";
}
