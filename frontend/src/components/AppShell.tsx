import {
  Alert,
  AppShell as MantineAppShell,
  Button,
  Burger,
  Group,
  NavLink,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  IconDashboard,
  IconEye,
  IconHistory,
  IconKey,
  IconBook2,
  IconNetwork,
  IconReceipt,
  IconRocket,
  IconServer2,
  IconSettings,
  IconShieldLock,
} from "@tabler/icons-react";
import { type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink as RouterNavLink, useNavigate } from "react-router-dom";

import { useLogout, useMe } from "@/api/auth";
import { useSetupStatus } from "@/api/setup";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";

interface Props {
  children: ReactNode;
}

export function AppShell({ children }: Props) {
  const [opened, { toggle }] = useDisclosure();
  const { t } = useTranslation();
  const me = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const setup = useSetupStatus();
  const setupSteps = setup.data?.steps ?? [];
  const requiredTotal = setupSteps.filter((s) => s.required).length;
  const requiredDone = setupSteps.filter((s) => s.required && s.done).length;
  const showSetupBanner = Boolean(setup.data && !setup.data.completed);

  const handleLogout = () => {
    logout.mutate(undefined, {
      onSettled: () => navigate("/login", { replace: true }),
    });
  };

  return (
    <MantineAppShell
      header={{ height: 56 }}
      navbar={{ width: 240, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding="md"
    >
      <MantineAppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group>
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <Title order={4}>{t("app.title")}</Title>
          </Group>
          <Group gap="xs">
            {me.data && (
              <Text size="sm" c="dimmed">
                {me.data.username}
              </Text>
            )}
            <LanguageSwitcher />
            <Button variant="subtle" size="xs" onClick={handleLogout}>
              {t("nav.logout")}
            </Button>
          </Group>
        </Group>
      </MantineAppShell.Header>
      <MantineAppShell.Navbar p="sm">
        <Stack gap={4}>
          <NavLink
            component={RouterNavLink}
            to="/"
            end
            label={t("nav.dashboard")}
            leftSection={<IconDashboard size={16} />}
          />
          <NavLink
            component={RouterNavLink}
            to="/device-groups"
            label={t("nav.deviceGroups")}
            leftSection={<IconNetwork size={16} />}
          />
          <NavLink
            component={RouterNavLink}
            to="/privilege-profiles"
            label={t("nav.privilegeProfiles")}
            leftSection={<IconKey size={16} />}
          />
          <NavLink
            component={RouterNavLink}
            to="/devices"
            label={t("nav.devices")}
            leftSection={<IconServer2 size={16} />}
          />
          <NavLink
            component={RouterNavLink}
            to="/device-templates"
            label={t("nav.deviceTemplates")}
            leftSection={<IconBook2 size={16} />}
          />
          <NavLink
            component={RouterNavLink}
            to="/authorizations"
            label={t("nav.authorizations")}
            leftSection={<IconShieldLock size={16} />}
          />
          <NavLink
            component={RouterNavLink}
            to="/effective-permissions"
            label={t("nav.effectivePermissions")}
            leftSection={<IconEye size={16} />}
          />
          <NavLink
            component={RouterNavLink}
            to="/accounting"
            label={t("nav.accounting")}
            leftSection={<IconReceipt size={16} />}
            mt="md"
          />
          <NavLink
            component={RouterNavLink}
            to="/audit-log"
            label={t("nav.auditLog")}
            leftSection={<IconHistory size={16} />}
          />
          <NavLink
            component={RouterNavLink}
            to="/settings"
            label={t("nav.settings")}
            leftSection={<IconSettings size={16} />}
          />
          <NavLink
            component={RouterNavLink}
            to="/setup"
            label={t("nav.setup")}
            leftSection={<IconRocket size={16} />}
          />
        </Stack>
      </MantineAppShell.Navbar>
      <MantineAppShell.Main>
        {showSetupBanner && (
          <Alert
            color="yellow"
            variant="light"
            title={t("setup.bannerTitle")}
            mb="md"
            withCloseButton={false}
          >
            <Group justify="space-between" wrap="nowrap">
              <Text size="sm">
                {t("setup.bannerBody", {
                  done: requiredDone,
                  required: requiredTotal,
                })}
              </Text>
              <Button component={Link} to="/setup" size="xs" variant="filled">
                {t("setup.bannerCta")}
              </Button>
            </Group>
          </Alert>
        )}
        {children}
      </MantineAppShell.Main>
    </MantineAppShell>
  );
}
