-- Seed the backend DB for the integration smoke.
--
-- Inserts:
--   1. system_setting('ldap.url') so the MAVIS handler can resolve the
--      live-bind endpoint
--   2. one user row whose distinguished_name matches the user bitnami/openldap
--      creates from LDAP_USERS=smokeuser at LDAP_ROOT=dc=corp,dc=example
--
-- Re-running is safe (ON CONFLICT clauses).

INSERT INTO system_setting (key, value, updated_at)
VALUES ('ldap.url', 'ldap://openldap:1389', now())
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value, updated_at = now();

INSERT INTO "user" (sam_account_name, distinguished_name, enabled, created_at, updated_at)
VALUES (
    'smokeuser',
    'cn=smokeuser,ou=users,dc=corp,dc=example',
    true,
    now(),
    now()
)
ON CONFLICT (sam_account_name) DO UPDATE
SET distinguished_name = EXCLUDED.distinguished_name,
    enabled = true,
    updated_at = now();
