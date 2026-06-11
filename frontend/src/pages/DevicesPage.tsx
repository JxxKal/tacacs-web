import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  PasswordInput,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
  Title,
  Tooltip,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import {
  IconAlertCircle,
  IconKey,
  IconPencil,
  IconPlus,
  IconRotateClockwise,
  IconTrash,
} from "@tabler/icons-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { useDeviceGroups } from "@/api/deviceGroups";
import {
  useCreateDevice,
  useDeleteDevice,
  useDevices,
  useRetirePreviousSecret,
  useRotateDeviceSecret,
  useUpdateDevice,
  type Device,
} from "@/api/devices";
import { errorToMessage } from "@/utils/errors";

interface FormValues {
  name: string;
  ip_or_cidr: string;
  device_group_id: string;
  current_secret: string;
  description: string;
}

function isIpOrCidr(value: string): boolean {
  // Permissive surface: server-side pydantic validator owns the truth.
  // Client-side check just blocks the obvious typos.
  return /^[0-9a-fA-F:.]+(\/[0-9]+)?$/.test(value);
}

export function DevicesPage() {
  const { t } = useTranslation();
  const devices = useDevices();
  const groups = useDeviceGroups();
  const create = useCreateDevice();
  const update = useUpdateDevice();
  const remove = useDeleteDevice();
  const rotate = useRotateDeviceSecret();
  const retire = useRetirePreviousSecret();

  const groupNameById = useMemo(() => {
    const m = new Map<number, string>();
    for (const g of groups.data ?? []) m.set(g.id, g.name);
    return m;
  }, [groups.data]);

  if (devices.isPending || groups.isPending) return <Loader />;
  if (devices.isError) {
    return (
      <Alert color="red" icon={<IconAlertCircle size={16} />} title={t("common.error")}>
        {t("common.errorMessage", { message: errorToMessage(devices.error) })}
      </Alert>
    );
  }

  const groupOptions = (groups.data ?? []).map((g) => ({
    value: String(g.id),
    label: g.name,
  }));

  const openCreate = () => {
    openEditor({
      mode: "create",
      title: t("devices.createTitle"),
      initial: {
        name: "",
        ip_or_cidr: "",
        device_group_id: groupOptions[0]?.value ?? "",
        current_secret: "",
        description: "",
      },
      groupOptions,
      t,
      onSubmit: async (values) => {
        const created = await create.mutateAsync({
          name: values.name.trim(),
          ip_or_cidr: values.ip_or_cidr.trim(),
          device_group_id: Number(values.device_group_id),
          current_secret: values.current_secret.trim() || null,
          description: values.description.trim() || null,
        });
        notifications.show({
          color: "green",
          message: t("common.created", { name: created.name }),
        });
      },
    });
  };

  const openEdit = (row: Device) => {
    openEditor({
      mode: "edit",
      title: t("devices.editTitle"),
      initial: {
        name: row.name,
        ip_or_cidr: row.ip_or_cidr,
        device_group_id: String(row.device_group_id),
        current_secret: "",
        description: row.description ?? "",
      },
      groupOptions,
      t,
      onSubmit: async (values) => {
        await update.mutateAsync({
          id: row.id,
          name: values.name.trim(),
          ip_or_cidr: values.ip_or_cidr.trim(),
          device_group_id: Number(values.device_group_id),
          description: values.description.trim() || null,
          current_secret: values.current_secret.trim() || null,
        });
        notifications.show({
          color: "green",
          message: t("common.updated", { name: values.name }),
        });
      },
    });
  };

  const openRotate = (row: Device) => {
    const modalId = `device-rotate-${row.id}`;
    modals.open({
      modalId,
      title: t("devices.rotateTitle"),
      children: (
        <RotateForm
          deviceName={row.name}
          t={t}
          onCancel={() => modals.close(modalId)}
          onSubmit={async (new_secret) => {
            try {
              await rotate.mutateAsync({ id: row.id, new_secret });
              modals.close(modalId);
              notifications.show({
                color: "green",
                message: t("common.updated", { name: row.name }),
              });
            } catch (err) {
              notifications.show({
                color: "red",
                title: t("common.error"),
                message: errorToMessage(err),
              });
            }
          }}
        />
      ),
    });
  };

  const askRetire = (row: Device) => {
    retire.mutate(row.id, {
      onSuccess: () =>
        notifications.show({
          color: "green",
          message: t("common.updated", { name: row.name }),
        }),
      onError: (err) =>
        notifications.show({
          color: "red",
          title: t("common.error"),
          message: errorToMessage(err),
        }),
    });
  };

  const askDelete = (row: Device) => {
    modals.openConfirmModal({
      title: t("common.confirm"),
      children: <Text>{t("common.deleteConfirm", { name: row.name })}</Text>,
      labels: { confirm: t("common.delete"), cancel: t("common.cancel") },
      confirmProps: { color: "red" },
      onConfirm: () => {
        remove.mutate(row.id, {
          onSuccess: () =>
            notifications.show({
              color: "green",
              message: t("common.deleted", { name: row.name }),
            }),
          onError: (err) =>
            notifications.show({
              color: "red",
              title: t("common.error"),
              message: errorToMessage(err),
            }),
        });
      },
    });
  };

  return (
    <Stack>
      <Group justify="space-between" align="flex-end">
        <Stack gap={4}>
          <Title order={2}>{t("devices.title")}</Title>
          <Text c="dimmed" size="sm">
            {t("devices.subtitle")}
          </Text>
        </Stack>
        <Button
          leftSection={<IconPlus size={16} />}
          onClick={openCreate}
          disabled={groupOptions.length === 0}
        >
          {t("devices.createButton")}
        </Button>
      </Group>

      {devices.data.length === 0 ? (
        <Card withBorder padding="xl">
          <Text c="dimmed">{t("devices.emptyState")}</Text>
        </Card>
      ) : (
        <Card withBorder padding={0}>
          <Table verticalSpacing="sm" striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t("common.name")}</Table.Th>
                <Table.Th>{t("devices.ipOrCidr")}</Table.Th>
                <Table.Th>{t("devices.deviceGroup")}</Table.Th>
                <Table.Th>{t("devices.secretStatus")}</Table.Th>
                <Table.Th>{t("devices.previousSecret")}</Table.Th>
                <Table.Th style={{ width: 200 }}>{t("common.actions")}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {devices.data.map((row) => (
                <Table.Tr key={row.id}>
                  <Table.Td>{row.name}</Table.Td>
                  <Table.Td>
                    <Text ff="monospace" size="sm">
                      {row.ip_or_cidr}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    {groupNameById.get(row.device_group_id) ?? row.device_group_id}
                  </Table.Td>
                  <Table.Td>
                    <Badge color={row.has_current_secret ? "green" : "red"} variant="light">
                      {row.has_current_secret
                        ? t("devices.secretActive")
                        : t("devices.secretMissing")}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    {row.has_previous_secret ? (
                      <Badge color="yellow" variant="light">
                        {t("devices.previousActive")}
                      </Badge>
                    ) : (
                      <Text c="dimmed">{t("devices.previousNone")}</Text>
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Group gap="xs">
                      <Tooltip label={t("devices.rotateButton")}>
                        <ActionIcon variant="subtle" onClick={() => openRotate(row)}>
                          <IconRotateClockwise size={16} />
                        </ActionIcon>
                      </Tooltip>
                      {row.has_previous_secret && (
                        <Tooltip label={t("devices.retirePreviousButton")}>
                          <ActionIcon
                            variant="subtle"
                            color="yellow"
                            onClick={() => askRetire(row)}
                          >
                            <IconKey size={16} />
                          </ActionIcon>
                        </Tooltip>
                      )}
                      <ActionIcon
                        variant="subtle"
                        aria-label={t("common.edit")}
                        onClick={() => openEdit(row)}
                      >
                        <IconPencil size={16} />
                      </ActionIcon>
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        aria-label={t("common.delete")}
                        onClick={() => askDelete(row)}
                      >
                        <IconTrash size={16} />
                      </ActionIcon>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Card>
      )}
    </Stack>
  );
}

interface EditorOptions {
  mode: "create" | "edit";
  title: string;
  initial: FormValues;
  groupOptions: Array<{ value: string; label: string }>;
  onSubmit: (values: FormValues) => Promise<void>;
  t: (key: string, options?: Record<string, unknown>) => string;
}

function openEditor(opts: EditorOptions) {
  const modalId = `device-editor-${Date.now()}`;
  modals.open({
    modalId,
    title: opts.title,
    size: "lg",
    children: (
      <Editor
        {...opts}
        onCancel={() => modals.close(modalId)}
        onSubmit={async (values) => {
          try {
            await opts.onSubmit(values);
            modals.close(modalId);
          } catch (err) {
            notifications.show({
              color: "red",
              title: opts.t("common.error"),
              message: errorToMessage(err),
            });
          }
        }}
      />
    ),
  });
}

interface EditorProps extends EditorOptions {
  onCancel: () => void;
}

function Editor({ mode, initial, groupOptions, t, onCancel, onSubmit }: EditorProps) {
  const form = useForm<FormValues>({
    initialValues: initial,
    validate: {
      name: (v) => (v.trim() === "" ? t("common.name") : null),
      ip_or_cidr: (v) => (isIpOrCidr(v.trim()) ? null : t("devices.ipOrCidr")),
      device_group_id: (v) => (v === "" ? t("devices.deviceGroup") : null),
    },
  });
  return (
    <form
      onSubmit={form.onSubmit(async (values) => {
        await onSubmit(values);
      })}
    >
      <Stack>
        <TextInput label={t("common.name")} required {...form.getInputProps("name")} />
        <TextInput
          label={t("devices.ipOrCidr")}
          placeholder={t("devices.ipOrCidrPlaceholder")}
          required
          {...form.getInputProps("ip_or_cidr")}
        />
        <Select
          label={t("devices.deviceGroup")}
          data={groupOptions}
          required
          searchable
          {...form.getInputProps("device_group_id")}
        />
        <PasswordInput
          label={t("devices.currentSecret")}
          description={
            mode === "create"
              ? t("devices.secretCreateHint")
              : t("devices.secretEditHint")
          }
          {...form.getInputProps("current_secret")}
        />
        <Textarea
          label={t("common.description")}
          autosize
          minRows={2}
          {...form.getInputProps("description")}
        />
        <Group justify="flex-end" mt="sm">
          <Button variant="default" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
          <Button type="submit">{t("common.save")}</Button>
        </Group>
      </Stack>
    </form>
  );
}

interface RotateFormProps {
  deviceName: string;
  t: EditorOptions["t"];
  onCancel: () => void;
  onSubmit: (newSecret: string) => Promise<void>;
}

function RotateForm({ deviceName, t, onCancel, onSubmit }: RotateFormProps) {
  const form = useForm({
    initialValues: { new_secret: "" },
    validate: {
      new_secret: (v) => (v.trim() === "" ? t("devices.newSecret") : null),
    },
  });
  return (
    <form
      onSubmit={form.onSubmit(async (values) => {
        await onSubmit(values.new_secret.trim());
      })}
    >
      <Stack>
        <Text size="sm" c="dimmed">
          {deviceName}
        </Text>
        <Text size="sm">{t("devices.rotateHint")}</Text>
        <PasswordInput
          label={t("devices.newSecret")}
          required
          autoComplete="new-password"
          {...form.getInputProps("new_secret")}
        />
        <Group justify="flex-end" mt="sm">
          <Button variant="default" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
          <Button type="submit">{t("common.save")}</Button>
        </Group>
      </Stack>
    </form>
  );
}
