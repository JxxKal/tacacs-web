import {
  AppShell as MantineAppShell,
  Burger,
  Button,
  Group,
  NavLink,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  IconDashboard,
  IconKey,
  IconNetwork,
  IconServer2,
  IconShieldLock,
} from "@tabler/icons-react";
import { type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { NavLink as RouterNavLink, useNavigate } from "react-router-dom";

import { useLogout, useMe } from "@/api/auth";
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
            disabled
            label={t("nav.privilegeProfiles")}
            leftSection={<IconKey size={16} />}
          />
          <NavLink
            disabled
            label={t("nav.devices")}
            leftSection={<IconServer2 size={16} />}
          />
          <NavLink
            disabled
            label={t("nav.authorizations")}
            leftSection={<IconShieldLock size={16} />}
          />
        </Stack>
      </MantineAppShell.Navbar>
      <MantineAppShell.Main>{children}</MantineAppShell.Main>
    </MantineAppShell>
  );
}
