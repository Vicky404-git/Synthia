/**
 * Small inline SVG icon set.
 *
 * A single consistent stroke style (1.8px, rounded joins) keeps the "system
 * tool" look and avoids emoji, which render inconsistently across platforms.
 * Icons inherit `currentColor`, so colour comes from the surrounding CSS.
 */

type IconProps = {
  className?: string;
  size?: number;
};

function Svg({
  className,
  size = 18,
  children,
}: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export function ConsoleIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="3" y="4" width="18" height="16" rx="1.5" />
      <path d="M3 8h18" />
      <path d="m7 12 2 2-2 2" />
      <path d="M12 16h4" />
    </Svg>
  );
}

export function HistoryIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3 12a9 9 0 1 0 3-6.7" />
      <path d="M3 4v4h4" />
      <path d="M12 8v4l3 2" />
    </Svg>
  );
}

export function CloudIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M7 18h9.5a3.5 3.5 0 0 0 .3-6.98 5 5 0 0 0-9.6-1.6A3.5 3.5 0 0 0 7 18Z" />
    </Svg>
  );
}

export function SlidersIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 7h10" />
      <path d="M18 7h2" />
      <path d="M4 17h4" />
      <path d="M12 17h8" />
      <circle cx="16" cy="7" r="2" />
      <circle cx="10" cy="17" r="2" />
    </Svg>
  );
}

export function MicIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0" />
      <path d="M12 18v3" />
    </Svg>
  );
}

export function StopIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="7" y="7" width="10" height="10" rx="1.5" />
    </Svg>
  );
}

export function PowerIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 3v9" />
      <path d="M6.5 6.5a8 8 0 1 0 11 0" />
    </Svg>
  );
}
