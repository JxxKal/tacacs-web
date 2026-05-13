import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  SegmentedControl,
  Select,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import { IconAlertCircle, IconPlus, IconTrash } from "@tabler/icons-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import {
  useAuthorizations,
  useCreateAuthorization,
  useDeleteAuthorization,
  type Authorization,
} from "@/api/authorizations";
import { useDeviceGroups } from "@/api/deviceGroups";
import { useADGroups, useUsers } from "@/api/principals";
import { usePrivilegeProfiles } from "@/api/privilegeProfiles";
import { errorToMessage } from "@/utils/errors";

type PrincipalKind = "user" | "ad_group";

interface FormValues {
  kind: PrincipalKind;
  principal_id: string;
  device_group_id: string;
  privilege_profile_id: string;
}

export function AuthorizationsPage() {
  const { t } = useTranslation();
  const list = useAuthorizations();
  const users = useUsers();
  const adGroups = useADGroups();
  const deviceGroups = useDeviceGroups();
  const profiles = usePrivilegeProfiles();
  const create = useCreateAuthorization();
  const remove = useDeleteAuthorization();

  const userLabelById = useMemo(() => {
    const m = new Map<number, string>();
    for (const u of users.data ?? [])
      m.set(u.id, u.display_name ?? u.sam_account_name);
    return m;
  }, [users.data]);
  const adGroupLabelById = useMemo(() => {
    const m = new Map<number, string>();
    for (const g of adGroups.data ?? []) m.set(g.id, g.name ?? g.distinguished_name);
    return m;
  }, [adGroups.data]);
  const dgNameById = useMemo(() => {
    const m = new Map<number, string>();
    for (const g of deviceGroups.data ?? []) m.set(g.id, g.name);
    return m;
  }, [deviceGroups.data]);
  const profileLabelById = useMemo(() => {
    const m = new Map<number, string>();
    for (const p of profiles.data ?? [])
      m.set(p.id, `${p.name} (priv-lvl ${p.tacacs_priv_lvl})`);
    return m;
  }, [profiles.data]);

  const isLoading =
    list.isPending ||
    users.isPending ||
    adGroups.isPending ||
    deviceGroups.isPending ||
    profiles.isPending;
  if (isLoading) return <Loader />;
  if (list.isError) {
    return (
      <Alert color="red" icon={<IconAlertCircle size={16} />} title={t("common.error")}>
        {t("common.errorMessage", { message: errorToMessage(list.error) })}
      </Alert>
    );
  }

  const userOptions = (users.data ?? []).map((u) => ({
    value: String(u.id),
    label: `${u.sam_account_name}${u.display_name ? ` — ${u.display_name}` : ""}`,
  }));
  const adGroupOptions = (adGroups.data ?? []).map((g) => ({
    value: String(g.id),
    label: g.name ?? g.distinguished_name,
  }));
  const deviceGroupOptions = (deviceGroups.data ?? []).map((g) => ({
    value: String(g.id),
    label: g.name,
  }));
  const profileOptions = (profiles.data ?? []).map((p) => ({
    value: String(p.id),
    label: `${p.name} (priv-lvl ${p.tacacs_priv_lvl})`,
  }));

  const openCreateModal = () => {
    const modalId = `authz-create-${Date.now()}`;
    modals.open({
      modalId,
      title: t("authorizations.createTitle"),
      size: "lg",
      children: (
        <Editor
          t={t}
          userOptions={userOptions}
          adGroupOptions={adGroupOptions}
          deviceGroupOptions={deviceGroupOptions}
          profileOptions={profileOptions}
          onCancel={() => modals.close(modalId)}
          onSubmit={async (values) => {
            try {
              await create.mutateAsync({
                principal_user_id:
                  values.kind === "user" ? Number(values.principal_id) : null,
                principal_ad_group_id:
                  values.kind === "ad_group" ? Number(values.principal_id) : null,
                device_group_id: Number(values.device_group_id),
                privilege_profile_id: Number(values.privilege_profile_id),
              });
              modals.close(modalId);
              notifications.show({
                color: "green",
                message: t("common.created", { name: t("authorizations.title") }),
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

  const askDelete = (row: Authorization) => {
    modals.openConfirmModal({
      title: t("common.confirm"),
      children: (
        <Text>
          {t("common.deleteConfirm", { name: `#${row.id}` })}
        </Text>
      ),
      labels: { confirm: t("common.delete"), cancel: t("common.cancel") },
      confirmProps: { color: "red" },
      onConfirm: () => {
        remove.mutate(row.id, {
          onSuccess: () =>
            notifications.show({
              color: "green",
              message: t("common.deleted", { name: `#${row.id}` }),
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
          <Title order={2}>{t("authorizations.title")}</Title>
          <Text c="dimmed" size="sm">
            {t("authorizations.subtitle")}
          </Text>
        </Stack>
        <Button
          leftSection={<IconPlus size={16} />}
          onClick={openCreateModal}
          disabled={deviceGroupOptions.length === 0 || profileOptions.length === 0}
        >
          {t("authorizations.createButton")}
        </Button>
      </Group>

      {list.data.length === 0 ? (
        <Card withBorder padding="xl">
          <Text c="dimmed">{t("authorizations.emptyState")}</Text>
        </Card>
      ) : (
        <Card withBorder padding={0}>
          <Table verticalSpacing="sm" striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t("common.id")}</Table.Th>
                <Table.Th>{t("authorizations.principal")}</Table.Th>
                <Table.Th>{t("authorizations.deviceGroup")}</Table.Th>
                <Table.Th>{t("authorizations.privilegeProfile")}</Table.Th>
                <Table.Th style={{ width: 80 }}>{t("common.actions")}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {list.data.map((row) => (
                <Table.Tr key={row.id}>
                  <Table.Td>{row.id}</Table.Td>
                  <Table.Td>
                    <Group gap="xs">
                      {row.principal_user_id !== null ? (
                        <>
                          <Badge color="blue" variant="light">
                            {t("authorizations.directBadge")}
                          </Badge>
                          <Text>
                            {userLabelById.get(row.principal_user_id) ??
                              `user#${row.principal_user_id}`}
                          </Text>
                        </>
                      ) : (
                        <>
                          <Badge color="grape" variant="light">
                            {t("authorizations.groupBadge")}
                          </Badge>
                          <Text>
                            {adGroupLabelById.get(row.principal_ad_group_id ?? -1) ??
                              `group#${row.principal_ad_group_id}`}
                          </Text>
                        </>
                      )}
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    {dgNameById.get(row.device_group_id) ?? row.device_group_id}
                  </Table.Td>
                  <Table.Td>
                    {profileLabelById.get(row.privilege_profile_id) ?? row.privilege_profile_id}
                  </Table.Td>
                  <Table.Td>
                    <ActionIcon
                      variant="subtle"
                      color="red"
                      aria-label={t("common.delete")}
                      onClick={() => askDelete(row)}
                    >
                      <IconTrash size={16} />
                    </ActionIcon>
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

interface EditorProps {
  userOptions: Array<{ value: string; label: string }>;
  adGroupOptions: Array<{ value: string; label: string }>;
  deviceGroupOptions: Array<{ value: string; label: string }>;
  profileOptions: Array<{ value: string; label: string }>;
  t: (key: string, options?: Record<string, unknown>) => string;
  onCancel: () => void;
  onSubmit: (values: FormValues) => Promise<void>;
}

function Editor({
  userOptions,
  adGroupOptions,
  deviceGroupOptions,
  profileOptions,
  t,
  onCancel,
  onSubmit,
}: EditorProps) {
  const form = useForm<FormValues>({
    initialValues: {
      kind: "user",
      principal_id: userOptions[0]?.value ?? "",
      device_group_id: deviceGroupOptions[0]?.value ?? "",
      privilege_profile_id: profileOptions[0]?.value ?? "",
    },
    validate: {
      principal_id: (v) => (v === "" ? t("authorizations.principal") : null),
      device_group_id: (v) =>
        v === "" ? t("authorizations.deviceGroup") : null,
      privilege_profile_id: (v) =>
        v === "" ? t("authorizations.privilegeProfile") : null,
    },
  });

  const principalOptions =
    form.values.kind === "user" ? userOptions : adGroupOptions;

  return (
    <form
      onSubmit={form.onSubmit(async (values) => {
        await onSubmit(values);
      })}
    >
      <Stack>
        <Stack gap={6}>
          <Text size="sm" fw={500}>
            {t("authorizations.principalKind")}
          </Text>
          <SegmentedControl
            data={[
              { value: "user", label: t("authorizations.principalUser") },
              { value: "ad_group", label: t("authorizations.principalGroup") },
            ]}
            value={form.values.kind}
            onChange={(v) => {
              const kind = v as PrincipalKind;
              form.setFieldValue("kind", kind);
              const next =
                kind === "user" ? userOptions[0]?.value : adGroupOptions[0]?.value;
              form.setFieldValue("principal_id", next ?? "");
            }}
          />
        </Stack>
        <Select
          label={t("authorizations.principal")}
          data={principalOptions}
          searchable
          required
          {...form.getInputProps("principal_id")}
        />
        <Select
          label={t("authorizations.deviceGroup")}
          data={deviceGroupOptions}
          searchable
          required
          {...form.getInputProps("device_group_id")}
        />
        <Select
          label={t("authorizations.privilegeProfile")}
          data={profileOptions}
          searchable
          required
          {...form.getInputProps("privilege_profile_id")}
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
