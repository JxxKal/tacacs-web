import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconAlertCircle, IconCheck, IconCircleDashed } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import {
  type SetupStep,
  useCompleteSetup,
  useReopenSetup,
  useSetupStatus,
} from "@/api/setup";
import { useMe } from "@/api/auth";
import { errorToMessage } from "@/utils/errors";

// Each wizard step deep-links to the relevant settings card or CRUD page.
const STEP_LINKS: Record<string, string | null> = {
  local_admin: null,
  web_base_url: "/settings",
  tls: "/settings",
  ldap_url: "/settings",
  ldap_sync: "/settings",
  saml: "/settings",
  first_device_group: "/device-groups",
  first_privilege_profile: "/privilege-profiles",
  first_device: "/devices",
  first_authorization: "/authorizations",
  syslog_forwarder: "/settings",
};

export function SetupWizardPage() {
  const { t } = useTranslation();
  const status = useSetupStatus();
  const me = useMe();
  const complete = useCompleteSetup();
  const reopen = useReopenSetup();

  if (status.isPending) return <Loader />;
  if (status.isError || !status.data) {
    return (
      <Alert color="red" icon={<IconAlertCircle size={16} />} title={t("common.error")}>
        {errorToMessage(status.error)}
      </Alert>
    );
  }

  const s = status.data;
  const isAdmin = me.data?.role === "admin";

  const requiredOpen = s.steps.filter((step) => step.required && !step.done);

  return (
    <Stack>
      <Title order={2}>{t("setup.title")}</Title>
      <Text c="dimmed" maw={780}>
        {t("setup.intro")}
      </Text>

      {s.completed && (
        <Alert
          color="green"
          icon={<IconCheck size={16} />}
          title={t("setup.title")}
        >
          {s.completed_by
            ? t("setup.completed", { user: s.completed_by })
            : t("setup.completedNoUser")}
        </Alert>
      )}

      <Stack gap="xs">
        {s.steps.map((step) => (
          <StepCard key={step.key} step={step} />
        ))}
      </Stack>

      <Card withBorder padding="lg">
        <Stack>
          {!s.can_complete && requiredOpen.length > 0 && (
            <Alert color="yellow" variant="light">
              {t("setup.completeUnavailableHint")}
            </Alert>
          )}
          <Group>
            <Button
              disabled={!s.can_complete || s.completed || !isAdmin}
              loading={complete.isPending}
              onClick={() =>
                complete.mutate(undefined, {
                  onSuccess: () =>
                    notifications.show({
                      color: "green",
                      message: t("setup.completeSucceeded"),
                    }),
                  onError: (err) =>
                    notifications.show({
                      color: "red",
                      title: t("common.error"),
                      message: errorToMessage(err),
                    }),
                })
              }
            >
              {t("setup.completeButton")}
            </Button>
            {s.completed && isAdmin && (
              <Button
                variant="default"
                loading={reopen.isPending}
                onClick={() =>
                  reopen.mutate(undefined, {
                    onSuccess: () =>
                      notifications.show({
                        color: "green",
                        message: t("setup.reopened"),
                      }),
                  })
                }
              >
                {t("setup.reopen")}
              </Button>
            )}
          </Group>
        </Stack>
      </Card>
    </Stack>
  );
}

function StepCard({ step }: { step: SetupStep }) {
  const { t } = useTranslation();
  const link = STEP_LINKS[step.key];

  return (
    <Card withBorder padding="md">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Group align="flex-start" wrap="nowrap">
          {step.done ? (
            <IconCheck color="var(--mantine-color-green-6)" />
          ) : (
            <IconCircleDashed color="var(--mantine-color-gray-6)" />
          )}
          <Stack gap={2}>
            <Group gap="xs">
              <Text fw={500}>{t(`setup.steps.${step.key}.title`)}</Text>
              <Badge color={step.required ? "red" : "blue"} variant="light" size="sm">
                {step.required ? t("setup.stepRequired") : t("setup.stepOptional")}
              </Badge>
              <Badge color={step.done ? "green" : "gray"} variant="filled" size="sm">
                {step.done ? t("setup.stepDone") : t("setup.stepOpen")}
              </Badge>
            </Group>
            <Text size="sm" c="dimmed">
              {t(`setup.steps.${step.key}.hint`)}
            </Text>
            {step.detail && (
              <Text size="xs" c="dimmed" ff="monospace">
                {step.detail}
              </Text>
            )}
          </Stack>
        </Group>
        {link && (
          <Button
            component={Link}
            to={link}
            variant={step.done ? "default" : "filled"}
            size="xs"
          >
            {t("setup.open")}
          </Button>
        )}
      </Group>
    </Card>
  );
}
