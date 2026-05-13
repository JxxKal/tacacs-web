import {
  Alert,
  Button,
  Card,
  Center,
  Container,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { IconAlertTriangle } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";

import { useLogin, useMe } from "@/api/auth";
import { ApiError } from "@/api/client";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";

interface LocationState {
  from?: string;
}

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const me = useMe();
  const login = useLogin();
  const [errorKey, setErrorKey] = useState<string | null>(null);

  const form = useForm({
    initialValues: { username: "", password: "" },
    validate: {
      username: (v) => (v.trim() === "" ? t("login.username") : null),
      password: (v) => (v === "" ? t("login.password") : null),
    },
  });

  useEffect(() => {
    if (me.data) {
      const dest = (location.state as LocationState | null)?.from ?? "/";
      navigate(dest, { replace: true });
    }
  }, [me.data, location.state, navigate]);

  const onSubmit = form.onSubmit((values) => {
    setErrorKey(null);
    login.mutate(values, {
      onSuccess: () => {
        const dest = (location.state as LocationState | null)?.from ?? "/";
        navigate(dest, { replace: true });
      },
      onError: (err) => {
        if (err instanceof ApiError && err.status === 401) {
          setErrorKey("login.invalidCredentials");
        } else {
          setErrorKey("login.unexpectedError");
        }
      },
    });
  });

  return (
    <Center mih="100vh" bg="var(--mantine-color-default-hover)">
      <Container w={420}>
        <Stack>
          <Card withBorder shadow="md" padding="xl">
            <Stack>
              <Stack gap={4}>
                <Title order={3}>{t("login.title")}</Title>
                <Text size="sm" c="dimmed">
                  {t("app.title")}
                </Text>
              </Stack>
              <Alert
                color="orange"
                icon={<IconAlertTriangle size={16} />}
                title={t("login.title")}
              >
                {t("login.breakGlassWarning")}
              </Alert>
              <form onSubmit={onSubmit}>
                <Stack>
                  <TextInput
                    label={t("login.username")}
                    autoComplete="username"
                    {...form.getInputProps("username")}
                  />
                  <PasswordInput
                    label={t("login.password")}
                    autoComplete="current-password"
                    {...form.getInputProps("password")}
                  />
                  {errorKey && (
                    <Alert color="red" variant="light">
                      {t(errorKey)}
                    </Alert>
                  )}
                  <Button type="submit" loading={login.isPending} fullWidth>
                    {t("login.submit")}
                  </Button>
                </Stack>
              </form>
            </Stack>
          </Card>
          <Center>
            <LanguageSwitcher />
          </Center>
        </Stack>
      </Container>
    </Center>
  );
}
