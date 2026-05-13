import { ActionIcon, Menu } from "@mantine/core";
import { IconLanguage } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "de", label: "Deutsch" },
] as const;

export function LanguageSwitcher() {
  const { i18n, t } = useTranslation();
  return (
    <Menu shadow="md" width={160}>
      <Menu.Target>
        <ActionIcon
          variant="subtle"
          aria-label={t("common.language")}
          size="lg"
        >
          <IconLanguage size={18} />
        </ActionIcon>
      </Menu.Target>
      <Menu.Dropdown>
        {LANGUAGES.map((lng) => (
          <Menu.Item
            key={lng.code}
            onClick={() => void i18n.changeLanguage(lng.code)}
            fw={i18n.resolvedLanguage === lng.code ? 600 : 400}
          >
            {lng.label}
          </Menu.Item>
        ))}
      </Menu.Dropdown>
    </Menu>
  );
}
