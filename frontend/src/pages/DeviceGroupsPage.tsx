import {
  ActionIcon,
  Alert,
  Button,
  Card,
  Group,
  Loader,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import {
  IconAlertCircle,
  IconPencil,
  IconPlus,
  IconTrash,
} from "@tabler/icons-react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/api/client";
import {
  useCreateDeviceGroup,
  useDeleteDeviceGroup,
  useDeviceGroups,
  useUpdateDeviceGroup,
  type DeviceGroup,
  type DeviceGroupInput,
} from "@/api/deviceGroups";

export function DeviceGroupsPage() {
  const { t } = useTranslation();
  const list = useDeviceGroups();
  const create = useCreateDeviceGroup();
  const update = useUpdateDeviceGroup();
  const remove = useDeleteDeviceGroup();

  if (list.isPending) return <Loader />;
  if (list.isError) {
    const message =
      list.error instanceof Error ? list.error.message : String(list.error);
    return (
      <Alert color="red" icon={<IconAlertCircle size={16} />} title={t("common.error")}>
        {t("common.errorMessage", { message })}
      </Alert>
    );
  }

  const openCreateModal = () => {
    openEditor({
      title: t("deviceGroups.createTitle"),
      initial: { name: "", description: null },
      onSubmit: (values) =>
        create.mutateAsync(values).then((row) => {
          notifications.show({
            color: "green",
            message: t("common.created", { name: row.name }),
          });
        }),
      t,
    });
  };

  const openEditModal = (row: DeviceGroup) => {
    openEditor({
      title: t("deviceGroups.editTitle"),
      initial: { name: row.name, description: row.description ?? "" },
      onSubmit: (values) =>
        update.mutateAsync({ id: row.id, ...values }).then(() => {
          notifications.show({
            color: "green",
            message: t("common.updated", { name: values.name }),
          });
        }),
      t,
    });
  };

  const askDelete = (row: DeviceGroup) => {
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
              message:
                err instanceof ApiError && err.detail
                  ? err.detail
                  : err instanceof Error
                    ? err.message
                    : String(err),
            }),
        });
      },
    });
  };

  return (
    <Stack>
      <Group justify="space-between" align="flex-end">
        <Stack gap={4}>
          <Title order={2}>{t("deviceGroups.title")}</Title>
          <Text c="dimmed" size="sm">
            {t("deviceGroups.subtitle")}
          </Text>
        </Stack>
        <Button leftSection={<IconPlus size={16} />} onClick={openCreateModal}>
          {t("deviceGroups.createButton")}
        </Button>
      </Group>

      {list.data.length === 0 ? (
        <Card withBorder padding="xl">
          <Text c="dimmed">{t("deviceGroups.emptyState")}</Text>
        </Card>
      ) : (
        <Card withBorder padding={0}>
          <Table verticalSpacing="sm" striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t("common.id")}</Table.Th>
                <Table.Th>{t("common.name")}</Table.Th>
                <Table.Th>{t("common.description")}</Table.Th>
                <Table.Th style={{ width: 120 }}>{t("common.actions")}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {list.data.map((row) => (
                <Table.Tr key={row.id}>
                  <Table.Td>{row.id}</Table.Td>
                  <Table.Td>{row.name}</Table.Td>
                  <Table.Td>
                    <Text c={row.description ? undefined : "dimmed"}>
                      {row.description ?? "—"}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap="xs">
                      <ActionIcon
                        variant="subtle"
                        aria-label={t("common.edit")}
                        onClick={() => openEditModal(row)}
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
  title: string;
  initial: { name: string; description: string | null };
  onSubmit: (values: DeviceGroupInput) => Promise<unknown>;
  t: (key: string, options?: Record<string, unknown>) => string;
}

function openEditor({ title, initial, onSubmit, t }: EditorOptions) {
  const modalId = `device-group-editor-${Date.now()}`;
  const initialName = initial.name;
  const initialDescription = initial.description ?? "";
  modals.open({
    modalId,
    title,
    children: (
      <Editor
        initialName={initialName}
        initialDescription={initialDescription}
        t={t}
        onCancel={() => modals.close(modalId)}
        onSubmit={async (values) => {
          try {
            await onSubmit({
              name: values.name.trim(),
              description: values.description.trim() || null,
            });
            modals.close(modalId);
          } catch (err) {
            const message =
              err instanceof ApiError && err.detail
                ? err.detail
                : err instanceof Error
                  ? err.message
                  : String(err);
            notifications.show({
              color: "red",
              title: t("common.error"),
              message,
            });
          }
        }}
      />
    ),
  });
}

interface EditorProps {
  initialName: string;
  initialDescription: string;
  t: EditorOptions["t"];
  onCancel: () => void;
  onSubmit: (values: { name: string; description: string }) => Promise<void>;
}

function Editor({
  initialName,
  initialDescription,
  t,
  onCancel,
  onSubmit,
}: EditorProps) {
  const form = useForm({
    initialValues: { name: initialName, description: initialDescription },
    validate: {
      name: (v) => (v.trim() === "" ? t("common.name") : null),
    },
  });
  return (
    <form
      onSubmit={form.onSubmit(async (values) => {
        await onSubmit(values);
      })}
    >
      <Stack>
        <TextInput
          label={t("common.name")}
          placeholder={t("deviceGroups.namePlaceholder")}
          required
          {...form.getInputProps("name")}
        />
        <Textarea
          label={t("common.description")}
          placeholder={t("deviceGroups.descriptionPlaceholder")}
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
