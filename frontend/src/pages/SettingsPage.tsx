import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Divider,
  FileButton,
  Group,
  Loader,
  NumberInput,
  Select,
  Stack,
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
  IconDownload,
  IconLock,
  IconTrash,
} from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  useImportIdpMetadata,
  useRegenerateSpKeypair,
  useSamlStatus,
  useUpdateSamlMapping,
  type RoleMapping,
  type SamlRole,
  type SamlStatus,
} from "@/api/saml";
import {
  useLdapSettings,
  useUpdateLdapSettings,
  useUpdateWebSettings,
  useWebSettings,
} from "@/api/settings";
import {
  useRegenerateTls,
  useTlsStatus,
  useUploadTls,
  type CertInfo,
} from "@/api/tls";
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
      <TlsCard />
      <SamlCard />
    </Stack>
  );
}

function SamlCard() {
  const { t } = useTranslation();
  const status = useSamlStatus();
  const regen = useRegenerateSpKeypair();

  if (status.isPending) return <Loader />;
  if (status.isError) {
    return (
      <Card withBorder padding="lg">
        <Alert color="red" icon={<IconAlertCircle size={16} />} title={t("common.error")}>
          {t("common.errorMessage", { message: errorToMessage(status.error) })}
        </Alert>
      </Card>
    );
  }
  const s = status.data;
  const onRegenerate = () => {
    regen.mutate(null, {
      onSuccess: () =>
        notifications.show({
          color: "green",
          message: t("settings.samlKeypairRegenerated"),
        }),
      onError: (err) =>
        notifications.show({
          color: "red",
          title: t("common.error"),
          message: errorToMessage(err),
        }),
    });
  };
  return (
    <Card withBorder padding="lg">
      <Stack>
        <Stack gap={4}>
          <Title order={4}>{t("settings.samlTitle")}</Title>
          <Text c="dimmed" size="sm">
            {t("settings.samlDescription")}
          </Text>
          {!s.configured && (
            <Alert color="yellow" variant="light" mt="xs">
              {t("settings.samlUnconfiguredHint")}
            </Alert>
          )}
        </Stack>

        <SamlInfoTable status={s} />

        <Group>
          <Button variant="default" onClick={() => openIdpImportModal(t)}>
            {t("settings.samlImportIdp")}
          </Button>
          <Button variant="default" onClick={onRegenerate} loading={regen.isPending}>
            {t("settings.samlRegenerateKeypair")}
          </Button>
          {s.sp_has_keypair && s.configured && (
            <Anchor
              href="/api/v1/settings/saml/sp-metadata"
              target="_blank"
              rel="noreferrer"
            >
              <Group gap={4}>
                <IconDownload size={14} />
                {t("settings.samlDownloadSpMetadata")}
              </Group>
            </Anchor>
          )}
        </Group>

        <Divider my="sm" />

        <SamlMappingForm status={s} />
      </Stack>
    </Card>
  );
}

function SamlInfoTable({ status }: { status: SamlStatus }) {
  const { t } = useTranslation();
  const rows: Array<[string, string]> = [
    [t("settings.samlSpEntityId"), status.sp_entity_id ?? "—"],
    [t("settings.samlSpAcsUrl"), status.sp_acs_url ?? "—"],
    [
      t("settings.samlSpKeypair"),
      status.sp_has_keypair
        ? t("settings.samlSpKeypairPresent")
        : t("settings.samlSpKeypairMissing"),
    ],
    [t("settings.samlIdpEntityId"), status.idp_entity_id ?? "—"],
    [t("settings.samlIdpSsoUrl"), status.idp_sso_url ?? "—"],
    [
      t("settings.samlIdpCert"),
      status.idp_cert_present
        ? t("settings.samlSpKeypairPresent")
        : t("settings.samlIdpNoMetadata"),
    ],
  ];
  return (
    <Stack gap={4}>
      {rows.map(([label, value]) => (
        <Group key={label} gap="md" wrap="nowrap" align="flex-start">
          <Text size="sm" c="dimmed" w={140} fw={500}>
            {label}
          </Text>
          <Text size="sm" ff="monospace" style={{ wordBreak: "break-all" }}>
            {value}
          </Text>
        </Group>
      ))}
    </Stack>
  );
}

interface MappingFormValues {
  group_attribute: string;
  rows: RoleMapping[];
}

function SamlMappingForm({ status }: { status: SamlStatus }) {
  const { t } = useTranslation();
  const save = useUpdateSamlMapping();
  const form = useForm<MappingFormValues>({
    initialValues: {
      group_attribute: status.group_attribute,
      rows: status.role_mappings.length > 0 ? status.role_mappings : [],
    },
    validate: {
      group_attribute: (v) =>
        v.trim() === "" ? t("settings.samlGroupAttribute") : null,
    },
  });

  useEffect(() => {
    form.setFieldValue("group_attribute", status.group_attribute);
    form.setFieldValue("rows", status.role_mappings);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status.group_attribute, status.role_mappings]);

  const addRow = () =>
    form.setFieldValue("rows", [
      ...form.values.rows,
      { ad_group: "", role: "viewer" as SamlRole },
    ]);
  const removeRow = (idx: number) =>
    form.setFieldValue(
      "rows",
      form.values.rows.filter((_, i) => i !== idx),
    );

  const submit = form.onSubmit((values) => {
    save.mutate(
      {
        group_attribute: values.group_attribute.trim(),
        role_mappings: values.rows
          .map((r) => ({ ad_group: r.ad_group.trim(), role: r.role }))
          .filter((r) => r.ad_group.length > 0),
      },
      {
        onSuccess: () =>
          notifications.show({ color: "green", message: t("settings.samlMappingSaved") }),
        onError: (err) =>
          notifications.show({
            color: "red",
            title: t("common.error"),
            message: errorToMessage(err),
          }),
      },
    );
  });

  return (
    <form onSubmit={submit}>
      <Stack>
        <Stack gap={4}>
          <Text size="sm" fw={500}>
            {t("settings.samlMapping")}
          </Text>
          <Text size="xs" c="dimmed">
            {t("settings.samlMappingDescription")}
          </Text>
        </Stack>
        <TextInput
          label={t("settings.samlGroupAttribute")}
          description={t("settings.samlGroupAttributeHint")}
          required
          {...form.getInputProps("group_attribute")}
        />
        <Stack gap={6}>
          {form.values.rows.map((row, idx) => (
            <Group key={idx} gap="xs" align="flex-end">
              <TextInput
                label={idx === 0 ? t("settings.samlGroupValue") : undefined}
                placeholder="CN=net-admins,OU=Groups,DC=corp,DC=example"
                value={row.ad_group}
                onChange={(e) => {
                  const next = [...form.values.rows];
                  next[idx] = { ...row, ad_group: e.currentTarget.value };
                  form.setFieldValue("rows", next);
                }}
                flex={2}
              />
              <Select
                label={idx === 0 ? t("settings.samlRole") : undefined}
                data={[
                  { value: "admin", label: "admin" },
                  { value: "operator", label: "operator" },
                  { value: "viewer", label: "viewer" },
                ]}
                value={row.role}
                onChange={(v) => {
                  const next = [...form.values.rows];
                  next[idx] = { ...row, role: (v as SamlRole) ?? "viewer" };
                  form.setFieldValue("rows", next);
                }}
                w={140}
              />
              <ActionIcon
                variant="subtle"
                color="red"
                onClick={() => removeRow(idx)}
                aria-label={t("common.delete")}
              >
                <IconTrash size={16} />
              </ActionIcon>
            </Group>
          ))}
          <Button variant="subtle" size="xs" onClick={addRow}>
            {t("settings.samlAddMapping")}
          </Button>
        </Stack>
        <Group justify="flex-end">
          <Button type="submit" loading={save.isPending}>
            {t("settings.samlSaveMapping")}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

function openIdpImportModal(
  t: (key: string, opts?: Record<string, unknown>) => string,
) {
  const modalId = `saml-idp-import-${Date.now()}`;
  modals.open({
    modalId,
    title: t("settings.samlImportTitle"),
    size: "lg",
    children: <IdpImportForm t={t} onClose={() => modals.close(modalId)} />,
  });
}

function IdpImportForm({
  t,
  onClose,
}: {
  t: (key: string, opts?: Record<string, unknown>) => string;
  onClose: () => void;
}) {
  const importIdp = useImportIdpMetadata();
  const form = useForm({
    initialValues: { xml: "" },
    validate: {
      xml: (v) =>
        v.includes("EntityDescriptor") ? null : t("settings.samlMetadataXml"),
    },
  });
  const [fileName, setFileName] = useState<string | null>(null);

  const readFile = (file: File | null) => {
    if (!file) return;
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = (e) => {
      const result = e.target?.result;
      if (typeof result === "string") form.setFieldValue("xml", result);
    };
    reader.readAsText(file);
  };

  const submit = form.onSubmit((values) => {
    importIdp.mutate(values.xml, {
      onSuccess: () => {
        notifications.show({ color: "green", message: t("settings.samlImported") });
        onClose();
      },
      onError: (err) =>
        notifications.show({
          color: "red",
          title: t("common.error"),
          message: errorToMessage(err),
        }),
    });
  });

  return (
    <form onSubmit={submit}>
      <Stack>
        <Text size="sm" c="dimmed">
          {t("settings.samlImportHint")}
        </Text>
        <FileButton onChange={readFile} accept=".xml,application/xml,text/xml">
          {(props) => (
            <Button variant="default" {...props}>
              {fileName ?? t("settings.samlMetadataXml")}
            </Button>
          )}
        </FileButton>
        <Textarea
          label={t("settings.samlMetadataXml")}
          autosize
          minRows={6}
          maxRows={20}
          required
          ff="monospace"
          {...form.getInputProps("xml")}
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" loading={importIdp.isPending}>
            {t("settings.samlImportButton")}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

function TlsCard() {
  const { t } = useTranslation();
  const status = useTlsStatus();

  if (status.isPending) return <Loader />;
  if (status.isError) {
    return (
      <Card withBorder padding="lg">
        <Alert color="red" icon={<IconAlertCircle size={16} />} title={t("common.error")}>
          {t("common.errorMessage", { message: errorToMessage(status.error) })}
        </Alert>
      </Card>
    );
  }

  return (
    <Card withBorder padding="lg">
      <Stack>
        <Stack gap={4}>
          <Group justify="space-between" align="flex-end">
            <Title order={4}>{t("settings.tlsTitle")}</Title>
            <Badge variant="light" color="gray" leftSection={<IconLock size={12} />}>
              {sourceLabel(status.data.info?.source, t)}
            </Badge>
          </Group>
          <Text c="dimmed" size="sm">
            {t("settings.tlsDescription")}
          </Text>
          <Alert color="yellow" variant="light" mt="xs">
            {t("settings.tlsRestartHint")}
          </Alert>
        </Stack>

        {status.data.info ? (
          <CertInfoTable info={status.data.info} />
        ) : (
          <Text c="dimmed">{t("settings.tlsNone")}</Text>
        )}

        <Group>
          <Button variant="default" onClick={() => openUploadModal(t)}>
            {t("settings.tlsUpload")}
          </Button>
          <Button variant="default" onClick={() => openRegenerateModal(t)}>
            {t("settings.tlsRegenerate")}
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}

function sourceLabel(
  source: string | undefined,
  t: (key: string) => string,
): string {
  switch (source) {
    case "uploaded":
      return t("settings.tlsSourceUploaded");
    case "self_signed_via_ui":
      return t("settings.tlsSourceUiSelfSigned");
    case "bootstrap":
    default:
      return t("settings.tlsSourceBootstrap");
  }
}

function CertInfoTable({ info }: { info: CertInfo }) {
  const { t } = useTranslation();
  const rows: Array<[string, string]> = [
    [t("settings.tlsSubject"), info.subject_cn ?? "—"],
    [t("settings.tlsIssuer"), info.issuer_cn ?? "—"],
    [t("settings.tlsSan"), info.san_dns.join(", ") || "—"],
    [t("settings.tlsNotBefore"), new Date(info.not_before).toLocaleString()],
    [t("settings.tlsNotAfter"), new Date(info.not_after).toLocaleString()],
    [t("settings.tlsFingerprint"), info.fingerprint_sha256],
  ];
  return (
    <Stack gap={4}>
      {rows.map(([label, value]) => (
        <Group key={label} gap="md" wrap="nowrap" align="flex-start">
          <Text size="sm" c="dimmed" w={140} fw={500}>
            {label}
          </Text>
          <Text size="sm" ff="monospace" style={{ wordBreak: "break-all" }}>
            {value}
          </Text>
        </Group>
      ))}
    </Stack>
  );
}

function openUploadModal(t: (key: string, opts?: Record<string, unknown>) => string) {
  const modalId = `tls-upload-${Date.now()}`;
  modals.open({
    modalId,
    title: t("settings.tlsUploadTitle"),
    size: "lg",
    children: <UploadForm t={t} onClose={() => modals.close(modalId)} />,
  });
}

function openRegenerateModal(
  t: (key: string, opts?: Record<string, unknown>) => string,
) {
  const modalId = `tls-regen-${Date.now()}`;
  modals.open({
    modalId,
    title: t("settings.tlsRegenerateTitle"),
    children: <RegenerateForm t={t} onClose={() => modals.close(modalId)} />,
  });
}

interface FormProps {
  t: (key: string, opts?: Record<string, unknown>) => string;
  onClose: () => void;
}

function UploadForm({ t, onClose }: FormProps) {
  const upload = useUploadTls();
  const form = useForm({
    initialValues: { cert_pem: "", key_pem: "" },
    validate: {
      cert_pem: (v) =>
        v.includes("BEGIN CERTIFICATE") ? null : t("settings.tlsCertPem"),
      key_pem: (v) =>
        v.includes("PRIVATE KEY") ? null : t("settings.tlsKeyPem"),
    },
  });
  const [certName, setCertName] = useState<string | null>(null);
  const [keyName, setKeyName] = useState<string | null>(null);

  const readFile = (file: File | null, field: "cert_pem" | "key_pem") => {
    if (!file) return;
    if (field === "cert_pem") setCertName(file.name);
    else setKeyName(file.name);
    const reader = new FileReader();
    reader.onload = (e) => {
      const result = e.target?.result;
      if (typeof result === "string") form.setFieldValue(field, result);
    };
    reader.readAsText(file);
  };

  const submit = form.onSubmit((values) => {
    upload.mutate(
      { cert_pem: values.cert_pem, key_pem: values.key_pem },
      {
        onSuccess: () => {
          notifications.show({ color: "green", message: t("settings.tlsUploaded") });
          onClose();
        },
        onError: (err) =>
          notifications.show({
            color: "red",
            title: t("common.error"),
            message: errorToMessage(err),
          }),
      },
    );
  });

  return (
    <form onSubmit={submit}>
      <Stack>
        <Group>
          <FileButton
            onChange={(f) => readFile(f, "cert_pem")}
            accept=".crt,.pem,application/x-x509-ca-cert"
          >
            {(props) => (
              <Button variant="default" {...props}>
                {certName ?? t("settings.tlsCertFile")}
              </Button>
            )}
          </FileButton>
          <FileButton
            onChange={(f) => readFile(f, "key_pem")}
            accept=".key,.pem"
          >
            {(props) => (
              <Button variant="default" {...props}>
                {keyName ?? t("settings.tlsKeyFile")}
              </Button>
            )}
          </FileButton>
        </Group>
        <Textarea
          label={t("settings.tlsCertPem")}
          autosize
          minRows={4}
          maxRows={8}
          required
          ff="monospace"
          {...form.getInputProps("cert_pem")}
        />
        <Textarea
          label={t("settings.tlsKeyPem")}
          autosize
          minRows={4}
          maxRows={8}
          required
          ff="monospace"
          {...form.getInputProps("key_pem")}
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" loading={upload.isPending}>
            {t("settings.tlsUploadButton")}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

function RegenerateForm({ t, onClose }: FormProps) {
  const regen = useRegenerateTls();
  const form = useForm({
    initialValues: { common_name: "", days: 825 },
    validate: {
      common_name: (v) => (v.trim() === "" ? t("settings.tlsCommonName") : null),
      days: (v) => (v >= 1 && v <= 3650 ? null : t("settings.tlsDays")),
    },
  });

  const submit = form.onSubmit((values) => {
    regen.mutate(
      { common_name: values.common_name.trim(), days: values.days },
      {
        onSuccess: () => {
          notifications.show({ color: "green", message: t("settings.tlsRegenerated") });
          onClose();
        },
        onError: (err) =>
          notifications.show({
            color: "red",
            title: t("common.error"),
            message: errorToMessage(err),
          }),
      },
    );
  });

  return (
    <form onSubmit={submit}>
      <Stack>
        <TextInput
          label={t("settings.tlsCommonName")}
          placeholder={t("settings.tlsCommonNamePlaceholder")}
          required
          {...form.getInputProps("common_name")}
        />
        <NumberInput
          label={t("settings.tlsDays")}
          min={1}
          max={3650}
          required
          {...form.getInputProps("days")}
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" loading={regen.isPending}>
            {t("settings.tlsRegenerate")}
          </Button>
        </Group>
      </Stack>
    </form>
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
