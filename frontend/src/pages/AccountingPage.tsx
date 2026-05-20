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

import { useAccounting, type AccountingEntry } from "@/api/accounting";
import { errorToMessage } from "@/utils/errors";

const PAGE_SIZE = 50;

const ACTIONS = ["start", "stop", "update"] as const;

export function AccountingPage() {
  const { t } = useTranslation();
  const [action, setAction] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [nasIp, setNasIp] = useState("");
  const [taskId, setTaskId] = useState("");
  const [cmd, setCmd] = useState("");
  const [offset, setOffset] = useState(0);

  const filter = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset,
      action,
      username: username.trim() || null,
      nas_ip: nasIp.trim() || null,
      task_id: taskId.trim() || null,
      cmd: cmd.trim() || null,
    }),
    [action, username, nasIp, taskId, cmd, offset],
  );

  const page = useAccounting(filter);

  const actionOptions = [
    { value: "", label: t("accounting.actionAll") },
    ...ACTIONS.map((a) => ({ value: a, label: a })),
  ];

  const resetOffset = () => setOffset(0);
  const onChange = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
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
        <Title order={2}>{t("accounting.title")}</Title>
        <Text c="dimmed" size="sm">
          {t("accounting.subtitle")}
        </Text>
      </Stack>

      <Card withBorder padding="md">
        <Group align="flex-end" wrap="wrap">
          <Select
            label={t("accounting.filterAction")}
            data={actionOptions}
            value={action ?? ""}
            onChange={(v) => onChange(setAction)(v && v.length > 0 ? v : null)}
            w={160}
          />
          <TextInput
            label={t("accounting.filterUsername")}
            value={username}
            onChange={(e) => onChange(setUsername)(e.currentTarget.value)}
            placeholder="jakaluza.ra"
            w={200}
          />
          <TextInput
            label={t("accounting.filterNasIp")}
            value={nasIp}
            onChange={(e) => onChange(setNasIp)(e.currentTarget.value)}
            placeholder="10.0.0.1"
            w={160}
          />
          <TextInput
            label={t("accounting.filterTaskId")}
            value={taskId}
            onChange={(e) => onChange(setTaskId)(e.currentTarget.value)}
            placeholder="0a00b00c"
            w={160}
          />
          <TextInput
            label={t("accounting.filterCmd")}
            value={cmd}
            onChange={(e) => onChange(setCmd)(e.currentTarget.value)}
            placeholder="show running-config"
            w={260}
          />
          <Button
            variant="default"
            onClick={() => {
              setAction(null);
              setUsername("");
              setNasIp("");
              setTaskId("");
              setCmd("");
              setOffset(0);
            }}
          >
            {t("accounting.filterClear")}
          </Button>
        </Group>
      </Card>

      {page.isPending || !page.data ? (
        <Card withBorder padding="xl">
          <Loader />
        </Card>
      ) : page.data.entries.length === 0 ? (
        <Card withBorder padding="xl">
          <Text c="dimmed">{t("accounting.empty")}</Text>
        </Card>
      ) : (
        <Card withBorder padding={0}>
          <Table verticalSpacing="sm" striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th style={{ width: 165 }}>{t("accounting.tsHeader")}</Table.Th>
                <Table.Th style={{ width: 80 }}>{t("accounting.actionHeader")}</Table.Th>
                <Table.Th>{t("accounting.userHeader")}</Table.Th>
                <Table.Th>{t("accounting.deviceHeader")}</Table.Th>
                <Table.Th style={{ width: 80 }}>{t("accounting.portHeader")}</Table.Th>
                <Table.Th>{t("accounting.cmdHeader")}</Table.Th>
                <Table.Th style={{ width: 70 }}>{t("accounting.privHeader")}</Table.Th>
                <Table.Th style={{ width: 70 }}>{t("accounting.elapsedHeader")}</Table.Th>
                <Table.Th>{t("accounting.taskHeader")}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {page.data.entries.map((row) => (
                <Row key={row.id} row={row} />
              ))}
            </Table.Tbody>
          </Table>
        </Card>
      )}

      {page.data && page.data.total > 0 && (
        <Group justify="space-between">
          <Text size="sm" c="dimmed">
            {t("accounting.showing", {
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
              {t("accounting.newer")}
            </Button>
            <Button
              variant="default"
              size="xs"
              disabled={
                page.data.offset + page.data.entries.length >= page.data.total
              }
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              {t("accounting.older")}
            </Button>
          </Group>
        </Group>
      )}
    </Stack>
  );
}

function Row({ row }: { row: AccountingEntry }) {
  const { t } = useTranslation();
  const when = new Date(row.ts).toLocaleString();
  return (
    <Table.Tr>
      <Table.Td>
        <Text size="xs" ff="monospace">
          {when}
        </Text>
      </Table.Td>
      <Table.Td>
        <Badge variant="light" color={actionColor(row.action)}>
          {row.action}
        </Badge>
      </Table.Td>
      <Table.Td>
        <Text size="sm">{row.username ?? "—"}</Text>
        {row.nac_ip && (
          <Text size="xs" c="dimmed" ff="monospace">
            from {row.nac_ip}
          </Text>
        )}
      </Table.Td>
      <Table.Td>
        <Text size="xs" ff="monospace">
          {row.nas_ip ?? "—"}
        </Text>
      </Table.Td>
      <Table.Td>
        <Text size="xs" ff="monospace">
          {row.port ?? "—"}
        </Text>
      </Table.Td>
      <Table.Td>
        <Text size="xs" ff="monospace" style={{ wordBreak: "break-word" }}>
          {row.cmd ?? (row.service ? `service=${row.service}` : "—")}
        </Text>
      </Table.Td>
      <Table.Td>
        {row.priv_lvl !== null ? (
          <Badge variant="light" color={privColor(row.priv_lvl)}>
            {row.priv_lvl}
          </Badge>
        ) : (
          <Text c="dimmed">—</Text>
        )}
      </Table.Td>
      <Table.Td>
        <Text size="xs" c="dimmed">
          {row.elapsed_seconds !== null
            ? t("accounting.elapsedSeconds", { count: row.elapsed_seconds })
            : "—"}
        </Text>
      </Table.Td>
      <Table.Td>
        <Text size="xs" ff="monospace" c="dimmed">
          {row.task_id ?? "—"}
        </Text>
      </Table.Td>
    </Table.Tr>
  );
}

function actionColor(action: string): string {
  switch (action) {
    case "start":
      return "blue";
    case "stop":
      return "gray";
    case "update":
      return "yellow";
    default:
      return "gray";
  }
}

function privColor(lvl: number): string {
  if (lvl >= 15) return "red";
  if (lvl >= 7) return "orange";
  if (lvl >= 1) return "yellow";
  return "gray";
}
