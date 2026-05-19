import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { IconAlertCircle } from "@tabler/icons-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  useAuditLog,
  useAuditLogActions,
  type AuditEntry,
} from "@/api/auditLog";
import { errorToMessage } from "@/utils/errors";

const PAGE_SIZE = 50;

const AUTH_METHODS = ["local", "saml", "tacacs"] as const;

export function AuditLogPage() {
  const { t } = useTranslation();
  const [actionFilter, setActionFilter] = useState<string | null>(null);
  const [authMethod, setAuthMethod] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [offset, setOffset] = useState(0);

  const filter = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset,
      action: actionFilter,
      auth_method: authMethod,
      username: username.trim() || null,
    }),
    [actionFilter, authMethod, username, offset],
  );

  const page = useAuditLog(filter);
  const actions = useAuditLogActions();

  const actionOptions = useMemo(() => {
    const all = actions.data?.actions ?? [];
    return [
      { value: "", label: t("audit.actionAll") },
      ...all.map((a) => ({ value: a, label: a })),
    ];
  }, [actions.data, t]);
  const authMethodOptions = useMemo(
    () => [
      { value: "", label: t("audit.authMethodAll") },
      ...AUTH_METHODS.map((m) => ({ value: m, label: m })),
    ],
    [t],
  );

  const resetOffset = () => setOffset(0);
  const onChangeAction = (v: string | null) => {
    setActionFilter(v && v.length > 0 ? v : null);
    resetOffset();
  };
  const onChangeAuthMethod = (v: string | null) => {
    setAuthMethod(v && v.length > 0 ? v : null);
    resetOffset();
  };

  if (page.isError) {
    return (
      <Card withBorder padding="lg">
        <Alert color="red" icon={<IconAlertCircle size={16} />} title={t("common.error")}>
          {t("common.errorMessage", { message: errorToMessage(page.error) })}
        </Alert>
      </Card>
    );
  }

  return (
    <Stack>
      <Stack gap={4}>
        <Title order={2}>{t("audit.title")}</Title>
        <Text c="dimmed" size="sm">
          {t("audit.subtitle")}
        </Text>
      </Stack>

      <Card withBorder padding="md">
        <Group align="flex-end" wrap="wrap">
          <Select
            label={t("audit.filterAction")}
            data={actionOptions}
            value={actionFilter ?? ""}
            onChange={onChangeAction}
            searchable
            clearable
            w={280}
          />
          <Select
            label={t("audit.filterAuthMethod")}
            data={authMethodOptions}
            value={authMethod ?? ""}
            onChange={onChangeAuthMethod}
            w={180}
          />
          <TextInput
            label={t("audit.filterUsername")}
            value={username}
            onChange={(e) => {
              setUsername(e.currentTarget.value);
              resetOffset();
            }}
            placeholder="alice / jakaluza.ra"
            w={240}
          />
          <Button
            variant="default"
            onClick={() => {
              setActionFilter(null);
              setAuthMethod(null);
              setUsername("");
              setOffset(0);
            }}
          >
            {t("audit.filterClear")}
          </Button>
        </Group>
      </Card>

      {page.isPending || !page.data ? (
        <Card withBorder padding="xl">
          <Loader />
        </Card>
      ) : page.data.entries.length === 0 ? (
        <Card withBorder padding="xl">
          <Text c="dimmed">{t("audit.empty")}</Text>
        </Card>
      ) : (
        <Card withBorder padding={0}>
          <Table verticalSpacing="sm" striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th style={{ width: 175 }}>{t("audit.tsHeader")}</Table.Th>
                <Table.Th>{t("audit.actionHeader")}</Table.Th>
                <Table.Th>{t("audit.actorHeader")}</Table.Th>
                <Table.Th>{t("audit.targetHeader")}</Table.Th>
                <Table.Th>{t("audit.summaryHeader")}</Table.Th>
                <Table.Th>{t("audit.clientIpHeader")}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {page.data.entries.map((row) => (
                <AuditRow key={row.id} row={row} />
              ))}
            </Table.Tbody>
          </Table>
        </Card>
      )}

      {page.data && page.data.total > 0 && (
        <Group justify="space-between">
          <Text size="sm" c="dimmed">
            {t("audit.showing", {
              from: page.data.offset + 1,
              to: Math.min(page.data.offset + page.data.entries.length, page.data.total),
              total: page.data.total,
            })}
          </Text>
          <Group gap="xs">
            <Button
              variant="default"
              size="xs"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              {t("audit.newer")}
            </Button>
            <Button
              variant="default"
              size="xs"
              disabled={
                page.data.offset + page.data.entries.length >= page.data.total
              }
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              {t("audit.older")}
            </Button>
          </Group>
        </Group>
      )}
    </Stack>
  );
}

function AuditRow({ row }: { row: AuditEntry }) {
  const when = new Date(row.ts).toLocaleString();
  const isFailure =
    row.action.endsWith("_failed") || row.action.endsWith("_unreachable");
  const isAuth = row.action.startsWith("auth.") || row.action.startsWith("tacacs.");
  return (
    <Table.Tr>
      <Table.Td>
        <Text size="xs" ff="monospace">
          {when}
        </Text>
      </Table.Td>
      <Table.Td>
        <Badge
          variant="light"
          color={isFailure ? "red" : isAuth ? "blue" : "gray"}
          style={{ textTransform: "none" }}
        >
          {row.action}
        </Badge>
      </Table.Td>
      <Table.Td>
        <Stack gap={0}>
          <Text size="sm">{row.actor_username_snapshot}</Text>
          <Text size="xs" c="dimmed">
            {row.actor_role} · {row.auth_method}
          </Text>
        </Stack>
      </Table.Td>
      <Table.Td>
        {row.target_type ? (
          <Text size="xs" c="dimmed">
            {row.target_type}
            {row.target_id !== null ? ` #${row.target_id}` : ""}
          </Text>
        ) : (
          <Text size="xs" c="dimmed">
            —
          </Text>
        )}
      </Table.Td>
      <Table.Td>
        <Text size="xs" style={{ wordBreak: "break-word" }}>
          {row.summary ?? "—"}
        </Text>
      </Table.Td>
      <Table.Td>
        <Text size="xs" ff="monospace" c="dimmed">
          {row.client_ip ?? "—"}
        </Text>
      </Table.Td>
    </Table.Tr>
  );
}
