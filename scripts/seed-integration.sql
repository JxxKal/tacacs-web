-- Seed the backend DB for the integration smoke.
--
-- Re-running is safe (ON CONFLICT clauses).
--
-- Layout:
--   - system_setting('ldap.url') so the MAVIS AUTH handler can resolve the
--     live-bind endpoint (M3)
--   - one user row whose distinguished_name matches the user bitnami/openldap
--     creates from LDAP_USERS=smokeuser at LDAP_ROOT=dc=corp,dc=example (M3)
--   - device_group + privilege_profile + device + authorization so the MAVIS
--     INFO handler returns priv-lvl=15 for that user on any NAS (M4)

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

INSERT INTO device_group (name, description, created_at)
VALUES ('smoke-dg', 'integration smoke test', now())
ON CONFLICT (name) DO NOTHING;

INSERT INTO privilege_profile (
    name, tacacs_priv_lvl,
    permit_commands_regex, deny_commands_regex, extra_av_pairs,
    description, created_at
)
VALUES (
    'smoke-admin', 15,
    '[]'::json, '[]'::json, '{}'::json,
    'integration smoke test', now()
)
ON CONFLICT (name) DO NOTHING;

-- 0.0.0.0/0 catches the source IP of whichever container or netns the
-- TACACS client sits in. Real deployments use specific IPs/CIDRs.
INSERT INTO device (name, ip_or_cidr, device_group_id, description, created_at, updated_at)
SELECT 'smoke-nas', '0.0.0.0/0', dg.id, 'catch-all for the smoke', now(), now()
FROM device_group dg
WHERE dg.name = 'smoke-dg'
ON CONFLICT (ip_or_cidr) DO NOTHING;

INSERT INTO authorization (
    principal_user_id, principal_ad_group_id,
    device_group_id, privilege_profile_id, created_at
)
SELECT u.id, NULL, dg.id, pp.id, now()
FROM "user" u, device_group dg, privilege_profile pp
WHERE u.sam_account_name = 'smokeuser'
  AND dg.name = 'smoke-dg'
  AND pp.name = 'smoke-admin'
ON CONFLICT (principal_user_id, device_group_id, privilege_profile_id) DO NOTHING;
