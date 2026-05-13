import {
  ActionIcon,
  Alert,
  Button,
  Card,
  Group,
  Loader,
  NumberInput,
  Stack,
  Table,
  TagsInput,
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

import {
  useCreatePrivilegeProfile,
  useDeletePrivilegeProfile,
  usePrivilegeProfiles,
  useUpdatePrivilegeProfile,
  type PrivilegeProfile,
  type PrivilegeProfileInput,
} from "@/api/privilegeProfiles";
import { errorToMessage } from "@/utils/errors";

interface AvPairRow {
  key: string;
  value: string;
}

interface FormValues {
  name: string;
  tacacs_priv_lvl: number;
  permit_commands_regex: string[];
  deny_commands_regex: string[];
  extra_av_pairs: AvPairRow[];
  description: string;
}

function toInput(values: FormValues): PrivilegeProfileInput {
  const pairs: Record<string, string> = {};
  for (const row of values.extra_av_pairs) {
    const key = row.key.trim();
    if (key) pairs[key] = row.value;
  }
  return {
    name: values.name.trim(),
    tacacs_priv_lvl: values.tacacs_priv_lvl,
    permit_commands_regex: values.permit_commands_regex,
    deny_commands_regex: values.deny_commands_regex,
    extra_av_pairs: pairs,
    description: values.description.trim() || null,
  };
}

function toFormValues(row: PrivilegeProfile | null): FormValues {
  if (row === null) {
    return {
      name: "",
      tacacs_priv_lvl: 1,
      permit_commands_regex: [],
      deny_commands_regex: [],
      extra_av_pairs: [],
      description: "",
    };
  }
  return {
    name: row.name,
    tacacs_priv_lvl: row.tacacs_priv_lvl,
    permit_commands_regex: row.permit_commands_regex,
    deny_commands_regex: row.deny_commands_regex,
    extra_av_pairs: Object.entries(row.extra_av_pairs).map(([key, value]) => ({
      key,
      value,
    })),
    description: row.description ?? "",
  };
}

export function PrivilegeProfilesPage() {
  const { t } = useTranslation();
  const list = usePrivilegeProfiles();
  const create = useCreatePrivilegeProfile();
  const update = useUpdatePrivilegeProfile();
  const remove = useDeletePrivilegeProfile();

  if (list.isPending) return <Loader />;
  if (list.isError) {
    return (
      <Alert color="red" icon={<IconAlertCircle size={16} />} title={t("common.error")}>
        {t("common.errorMessage", { message: errorToMessage(list.error) })}
      </Alert>
    );
  }

  const openCreateModal = () => {
    openEditor({
      title: t("privilegeProfiles.createTitle"),
      initial: toFormValues(null),
      onSubmit: async (values) => {
        const created = await create.mutateAsync(toInput(values));
        notifications.show({
          color: "green",
          message: t("common.created", { name: created.name }),
        });
      },
      t,
    });
  };

  const openEditModal = (row: PrivilegeProfile) => {
    openEditor({
      title: t("privilegeProfiles.editTitle"),
      initial: toFormValues(row),
      onSubmit: async (values) => {
        await update.mutateAsync({ id: row.id, ...toInput(values) });
        notifications.show({
          color: "green",
          message: t("common.updated", { name: values.name }),
        });
      },
      t,
    });
  };

  const askDelete = (row: PrivilegeProfile) => {
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
          <Title order={2}>{t("privilegeProfiles.title")}</Title>
          <Text c="dimmed" size="sm">
            {t("privilegeProfiles.subtitle")}
          </Text>
        </Stack>
        <Button leftSection={<IconPlus size={16} />} onClick={openCreateModal}>
          {t("privilegeProfiles.createButton")}
        </Button>
      </Group>

      {list.data.length === 0 ? (
        <Card withBorder padding="xl">
          <Text c="dimmed">{t("privilegeProfiles.emptyState")}</Text>
        </Card>
      ) : (
        <Card withBorder padding={0}>
          <Table verticalSpacing="sm" striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t("common.id")}</Table.Th>
                <Table.Th>{t("common.name")}</Table.Th>
                <Table.Th>{t("privilegeProfiles.privLvl")}</Table.Th>
                <Table.Th>{t("privilegeProfiles.permitCommands")}</Table.Th>
                <Table.Th>{t("privilegeProfiles.denyCommands")}</Table.Th>
                <Table.Th style={{ width: 120 }}>{t("common.actions")}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {list.data.map((row) => (
                <Table.Tr key={row.id}>
                  <Table.Td>{row.id}</Table.Td>
                  <Table.Td>{row.name}</Table.Td>
                  <Table.Td>{row.tacacs_priv_lvl}</Table.Td>
                  <Table.Td>{row.permit_commands_regex.join(", ") || "—"}</Table.Td>
                  <Table.Td>{row.deny_commands_regex.join(", ") || "—"}</Table.Td>
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
  initial: FormValues;
  onSubmit: (values: FormValues) => Promise<void>;
  t: (key: string, options?: Record<string, unknown>) => string;
}

function openEditor({ title, initial, onSubmit, t }: EditorOptions) {
  const modalId = `pp-editor-${Date.now()}`;
  modals.open({
    modalId,
    title,
    size: "lg",
    children: (
      <Editor
        initial={initial}
        t={t}
        onCancel={() => modals.close(modalId)}
        onSubmit={async (values) => {
          try {
            await onSubmit(values);
            modals.close(modalId);
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
}

interface EditorProps {
  initial: FormValues;
  t: EditorOptions["t"];
  onCancel: () => void;
  onSubmit: (values: FormValues) => Promise<void>;
}

function Editor({ initial, t, onCancel, onSubmit }: EditorProps) {
  const form = useForm<FormValues>({
    initialValues: initial,
    validate: {
      name: (v) => (v.trim() === "" ? t("common.name") : null),
      tacacs_priv_lvl: (v) =>
        Number.isInteger(v) && v >= 0 && v <= 15 ? null : t("privilegeProfiles.privLvl"),
    },
  });

  const addAvPair = () =>
    form.setFieldValue("extra_av_pairs", [
      ...form.values.extra_av_pairs,
      { key: "", value: "" },
    ]);
  const removeAvPair = (idx: number) =>
    form.setFieldValue(
      "extra_av_pairs",
      form.values.extra_av_pairs.filter((_, i) => i !== idx),
    );

  return (
    <form
      onSubmit={form.onSubmit(async (values) => {
        await onSubmit(values);
      })}
    >
      <Stack>
        <TextInput label={t("common.name")} required {...form.getInputProps("name")} />
        <NumberInput
          label={t("privilegeProfiles.privLvl")}
          min={0}
          max={15}
          required
          {...form.getInputProps("tacacs_priv_lvl")}
        />
        <TagsInput
          label={t("privilegeProfiles.permitCommands")}
          placeholder="^show "
          splitChars={[","]}
          clearable
          value={form.values.permit_commands_regex}
          onChange={(v) => form.setFieldValue("permit_commands_regex", v)}
        />
        <TagsInput
          label={t("privilegeProfiles.denyCommands")}
          placeholder="^configure "
          splitChars={[","]}
          clearable
          value={form.values.deny_commands_regex}
          onChange={(v) => form.setFieldValue("deny_commands_regex", v)}
          description={t("privilegeProfiles.denyWinsHint")}
        />
        <Stack gap={6}>
          <Group justify="space-between">
            <Text size="sm" fw={500}>
              {t("privilegeProfiles.extraAvPairs")}
            </Text>
            <Button variant="subtle" size="xs" onClick={addAvPair}>
              {t("privilegeProfiles.addAv")}
            </Button>
          </Group>
          <Text size="xs" c="dimmed">
            {t("privilegeProfiles.extraAvPairsHint")}
          </Text>
          {form.values.extra_av_pairs.map((row, idx) => (
            <Group key={idx} gap="xs" align="flex-end">
              <TextInput
                label={idx === 0 ? t("privilegeProfiles.key") : undefined}
                placeholder="idletime"
                value={row.key}
                onChange={(e) => {
                  const next = [...form.values.extra_av_pairs];
                  next[idx] = { ...row, key: e.currentTarget.value };
                  form.setFieldValue("extra_av_pairs", next);
                }}
                flex={1}
              />
              <TextInput
                label={idx === 0 ? t("privilegeProfiles.value") : undefined}
                placeholder="30"
                value={row.value}
                onChange={(e) => {
                  const next = [...form.values.extra_av_pairs];
                  next[idx] = { ...row, value: e.currentTarget.value };
                  form.setFieldValue("extra_av_pairs", next);
                }}
                flex={1}
              />
              <ActionIcon
                variant="subtle"
                color="red"
                onClick={() => removeAvPair(idx)}
                aria-label={t("common.delete")}
              >
                <IconTrash size={16} />
              </ActionIcon>
            </Group>
          ))}
        </Stack>
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
