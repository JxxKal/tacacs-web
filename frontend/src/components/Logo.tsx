interface LogoProps {
  size?: number;
  title?: string;
}

/**
 * Inline SVG mark for tacacs-web.
 *
 * Design: a rounded shield (auth context), a central `T+` glyph
 * (TACACS+ wordmark), and three orbit dots wired to the centre via
 * thin connectors (NAS-to-server topology, the gateway between
 * `aaa` clients and the AAA server). Single file, no dependencies,
 * scales cleanly down to 16 px because everything is built from
 * shapes rather than text.
 */
export function Logo({ size = 28, title = "tacacs-web" }: LogoProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label={title}
    >
      <title>{title}</title>
      <defs>
        <linearGradient id="tw-shield" x1="0" y1="0" x2="64" y2="64" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#4c6ef5" />
          <stop offset="1" stopColor="#5f3dc4" />
        </linearGradient>
      </defs>
      <rect
        x="6"
        y="6"
        width="52"
        height="52"
        rx="14"
        ry="14"
        fill="url(#tw-shield)"
      />
      <g stroke="#dbe4ff" strokeWidth="1.6" strokeLinecap="round" opacity="0.85">
        <line x1="32" y1="32" x2="14" y2="14" />
        <line x1="32" y1="32" x2="50" y2="14" />
        <line x1="32" y1="32" x2="32" y2="54" />
      </g>
      <g fill="#dbe4ff">
        <circle cx="14" cy="14" r="3" />
        <circle cx="50" cy="14" r="3" />
        <circle cx="32" cy="54" r="3" />
      </g>
      <g fill="#ffffff">
        <rect x="22" y="26" width="14" height="3" rx="1" />
        <rect x="27.5" y="26" width="3" height="14" rx="1" />
        <rect x="38" y="32" width="6" height="2" rx="1" />
        <rect x="40" y="30" width="2" height="6" rx="1" />
      </g>
    </svg>
  );
}
