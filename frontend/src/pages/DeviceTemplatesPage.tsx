import {
  Alert,
  Button,
  Code,
  Group,
  Loader,
  Stack,
  Tabs,
  Text,
  Title,
} from "@mantine/core";
import { useClipboard } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconCopy } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";

import { useDeviceTemplateHints } from "@/api/deviceTemplates";

const SECRET_PLACEHOLDER = "<SHARED_SECRET>";
const SOURCE_IFACE_PLACEHOLDER = "<SOURCE_INTERFACE>";

interface SnippetContext {
  serverHost: string;
  port: number;
}

const ciscoTemplate = ({ serverHost, port }: SnippetContext) => `! Cisco IOS / IOS-XE — TACACS+ AAA
! Replace ${SECRET_PLACEHOLDER} with the device's shared secret from the
! Devices page, and ${SOURCE_IFACE_PLACEHOLDER} with the management interface
! the NAS should source TACACS+ traffic from (e.g. Loopback0 / Vlan1).

aaa new-model
!
tacacs server tacacs-web
 address ipv4 ${serverHost}
 key ${SECRET_PLACEHOLDER}
 timeout 5
 single-connection
!
aaa group server tacacs+ tacacs-web-grp
 server name tacacs-web
 ip vrf forwarding default
 ip tacacs source-interface ${SOURCE_IFACE_PLACEHOLDER}
!
aaa authentication login default group tacacs-web-grp local
aaa authentication enable default group tacacs-web-grp enable
aaa authorization config-commands
aaa authorization exec default group tacacs-web-grp local if-authenticated
aaa authorization commands 1 default group tacacs-web-grp local if-authenticated
aaa authorization commands 15 default group tacacs-web-grp local if-authenticated
aaa accounting exec default start-stop group tacacs-web-grp
aaa accounting commands 1 default start-stop group tacacs-web-grp
aaa accounting commands 15 default start-stop group tacacs-web-grp
!
line vty 0 15
 transport input ssh
 authorization commands 15 default
 authorization exec default
 login authentication default

! TACACS+ TCP port is the hard-coded ${port}/tcp — do not change it on the NAS.
! 'single-connection' is recommended for tac_plus-ng to reuse one TCP socket.`;

const comwareTemplate = ({ serverHost, port }: SnippetContext) => `# HPE Comware (5900 / 5950 / FlexFabric, H3C heritage)
# Replace ${SECRET_PLACEHOLDER} with the device's shared secret from the
# Devices page. Comware calls TACACS+ "hwtacacs"; classic ProCurve uses
# "tacacs" instead — check the platform reference before pasting.

hwtacacs scheme tacacs-web
 primary authentication ${serverHost} ${port}
 primary authorization ${serverHost} ${port}
 primary accounting ${serverHost} ${port}
 key authentication simple ${SECRET_PLACEHOLDER}
 key authorization simple ${SECRET_PLACEHOLDER}
 key accounting simple ${SECRET_PLACEHOLDER}
 user-name-format without-domain
quit

domain tacacs
 authentication login hwtacacs-scheme tacacs-web local
 authorization login hwtacacs-scheme tacacs-web local
 accounting login hwtacacs-scheme tacacs-web
 authorization command hwtacacs-scheme tacacs-web
 accounting command hwtacacs-scheme tacacs-web
quit

domain default enable tacacs

line vty 0 63
 authentication-mode scheme
 user-role network-admin
quit

# 'user-name-format without-domain' is what makes \`alice\` arrive at the
# server instead of \`alice@tacacs\`. Adjust if your tac_plus-ng rules
# match on the fully-qualified form.`;

const moxaTemplate = ({ serverHost, port }: SnippetContext) => `! Moxa industrial switches (EDS / IKS / IEX series)
! Moxa supports TACACS+ for AUTHENTICATION only — there is no command
! authorization on the device side. Map operator roles by binding AD
! groups to a tac_plus-ng privilege profile in this UI; the resolved
! priv-lvl is what the switch's local role model consumes on login.
! Replace ${SECRET_PLACEHOLDER} with the device's shared secret.

configure
 authentication method tacacs+ local
 tacacs+ server primary
  ip ${serverHost}
  port ${port}
  shared-key ${SECRET_PLACEHOLDER}
  timeout 5
 exit
exit
write memory

! Web UI equivalent (older firmware without full CLI):
!   System → Authentication → TACACS+
!     Server IP:        ${serverHost}
!     Server port:      ${port}
!     Shared key:       ${SECRET_PLACEHOLDER}
!     Auth type:        PAP   (tac_plus-ng accepts PAP and CHAP; PAP is
!                              the safe default for legacy Moxa firmware)
!     Timeout:          5 s
!   Then: System → Account Management → "Use TACACS+ for login"
!
! Caveat: most Moxa platforms cap the shared secret at 32 chars and
! ASCII-only. Generate the device secret from the Devices page with
! that constraint in mind (the UI allows longer keys; the NAS won't).`;

const PLACEHOLDER_HOST = "<SERVER_IP>";

export function DeviceTemplatesPage() {
  const { t } = useTranslation();
  const hints = useDeviceTemplateHints();
  const clipboard = useClipboard({ timeout: 1500 });

  if (hints.isPending) return <Loader />;

  const ctx: SnippetContext = {
    serverHost: hints.data?.server_host ?? PLACEHOLDER_HOST,
    port: hints.data?.tacacs_port ?? 49,
  };
  const missingHost = !hints.data?.server_host;

  const tabs: Array<{
    value: string;
    label: string;
    intro: string;
    snippet: string;
  }> = [
    {
      value: "cisco",
      label: t("deviceTemplates.cisco.label"),
      intro: t("deviceTemplates.cisco.intro"),
      snippet: ciscoTemplate(ctx),
    },
    {
      value: "comware",
      label: t("deviceTemplates.comware.label"),
      intro: t("deviceTemplates.comware.intro"),
      snippet: comwareTemplate(ctx),
    },
    {
      value: "moxa",
      label: t("deviceTemplates.moxa.label"),
      intro: t("deviceTemplates.moxa.intro"),
      snippet: moxaTemplate(ctx),
    },
  ];

  return (
    <Stack>
      <Title order={2}>{t("deviceTemplates.title")}</Title>
      <Text c="dimmed" maw={820}>
        {t("deviceTemplates.subtitle")}
      </Text>
      {missingHost && (
        <Alert color="yellow" variant="light">
          {t("deviceTemplates.missingHostHint")}
        </Alert>
      )}

      <Tabs defaultValue="cisco">
        <Tabs.List>
          {tabs.map((tab) => (
            <Tabs.Tab key={tab.value} value={tab.value}>
              {tab.label}
            </Tabs.Tab>
          ))}
        </Tabs.List>
        {tabs.map((tab) => (
          <Tabs.Panel key={tab.value} value={tab.value} pt="md">
            <Stack>
              <Text size="sm">{tab.intro}</Text>
              <Group justify="flex-end">
                <Button
                  variant="default"
                  size="xs"
                  leftSection={<IconCopy size={14} />}
                  onClick={() => {
                    clipboard.copy(tab.snippet);
                    notifications.show({
                      color: "green",
                      message: t("deviceTemplates.copied"),
                    });
                  }}
                >
                  {t("deviceTemplates.copy")}
                </Button>
              </Group>
              <Code block style={{ whiteSpace: "pre", overflowX: "auto" }}>
                {tab.snippet}
              </Code>
            </Stack>
          </Tabs.Panel>
        ))}
      </Tabs>
    </Stack>
  );
}
