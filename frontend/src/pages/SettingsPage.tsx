import {
  Alert,
  Button,
  Card,
  Group,
  Loader,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { IconAlertCircle } from "@tabler/icons-react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import {
  useLdapSettings,
  useUpdateLdapSettings,
  useUpdateWebSettings,
  useWebSettings,
} from "@/api/settings";
import { errorToMessage } from "@/utils/errors";

export function SettingsPage() {
  const { t } = useTranslation();
  const ldap = useLdapSettings();
  const web = useWebSettings();

  if (ldap.isPending || web.isPending) return <Loader />;
  if (ldap.isError || web.isError) {
    const err = ldap.error ?? web.error;
    return (
      <Alert color="red" icon={<IconAlertCircle size={16} />} title={t("common.error")}>
        {t("common.errorMessage", { message: errorToMessage(err) })}
      </Alert>
    );
  }

  return (
    <Stack>
      <Stack gap={4}>
        <Title order={2}>{t("settings.title")}</Title>
        <Text c="dimmed" size="sm">
          {t("settings.subtitle")}
        </Text>
      </Stack>
      <LdapCard currentValue={ldap.data.url} />
      <WebCard currentValue={web.data.base_url} />
    </Stack>
  );
}

interface LdapCardProps {
  currentValue: string | null;
}

function LdapCard({ currentValue }: LdapCardProps) {
  const { t } = useTranslation();
  const mutate = useUpdateLdapSettings();
  const form = useForm({
    initialValues: { url: currentValue ?? "" },
    validate: {
      url: (v) =>
        /^ldaps?:\/\/.+/.test(v.trim()) ? null : t("settings.ldapUrl"),
    },
  });

  useEffect(() => {
    form.setFieldValue("url", currentValue ?? "");
    // currentValue is the only sync source we want to react to.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentValue]);

  const submit = form.onSubmit((values) => {
    mutate.mutate(values.url.trim(), {
      onSuccess: () =>
        notifications.show({ color: "green", message: t("settings.saved") }),
      onError: (err) =>
        notifications.show({
          color: "red",
          title: t("common.error"),
          message: errorToMessage(err),
        }),
    });
  });

  return (
    <Card withBorder padding="lg">
      <Stack>
        <Stack gap={4}>
          <Title order={4}>{t("settings.ldapTitle")}</Title>
          <Text c="dimmed" size="sm">
            {t("settings.ldapDescription")}
          </Text>
          {currentValue === null && (
            <Alert color="yellow" variant="light" mt="xs">
              {t("settings.ldapEmptyHint")}
            </Alert>
          )}
        </Stack>
        <form onSubmit={submit}>
          <Stack>
            <TextInput
              label={t("settings.ldapUrl")}
              placeholder={t("settings.ldapUrlPlaceholder")}
              required
              {...form.getInputProps("url")}
            />
            <Group justify="flex-end">
              <Button type="submit" loading={mutate.isPending}>
                {t("settings.save")}
              </Button>
            </Group>
          </Stack>
        </form>
      </Stack>
    </Card>
  );
}

interface WebCardProps {
  currentValue: string | null;
}

function WebCard({ currentValue }: WebCardProps) {
  const { t } = useTranslation();
  const mutate = useUpdateWebSettings();
  const form = useForm({
    initialValues: { base_url: currentValue ?? "" },
    validate: {
      base_url: (v) =>
        /^https?:\/\/.+/.test(v.trim()) ? null : t("settings.webBaseUrl"),
    },
  });

  useEffect(() => {
    form.setFieldValue("base_url", currentValue ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentValue]);

  const submit = form.onSubmit((values) => {
    mutate.mutate(values.base_url.trim(), {
      onSuccess: () =>
        notifications.show({ color: "green", message: t("settings.saved") }),
      onError: (err) =>
        notifications.show({
          color: "red",
          title: t("common.error"),
          message: errorToMessage(err),
        }),
    });
  });

  return (
    <Card withBorder padding="lg">
      <Stack>
        <Stack gap={4}>
          <Title order={4}>{t("settings.webTitle")}</Title>
          <Text c="dimmed" size="sm">
            {t("settings.webDescription")}
          </Text>
          {currentValue === null && (
            <Alert color="yellow" variant="light" mt="xs">
              {t("settings.webEmptyHint")}
            </Alert>
          )}
        </Stack>
        <form onSubmit={submit}>
          <Stack>
            <TextInput
              label={t("settings.webBaseUrl")}
              placeholder={t("settings.webBaseUrlPlaceholder")}
              required
              {...form.getInputProps("base_url")}
            />
            <Group justify="flex-end">
              <Button type="submit" loading={mutate.isPending}>
                {t("settings.save")}
              </Button>
            </Group>
          </Stack>
        </form>
      </Stack>
    </Card>
  );
}
