import { useId } from "react";
// Adapted from the user's logo.html. Static path remains visible without motion.
export function Logo({ animated = false }: { animated?: boolean }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg
      className={`darijadoc-logo ${animated ? "logo-animated" : ""}`}
      viewBox="22 22 156 156"
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient id={`brand-${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#2E9E5B" />
          <stop offset="100%" stopColor="#2E6FA8" />
        </linearGradient>
      </defs>
      <path
        className="logo-shape"
        fill={`url(#brand-${id})`}
        d="M 100 40 C 130 40, 160 70, 160 100 C 160 130, 130 160, 100 160 C 70 160, 40 130, 40 100 C 40 70, 70 40, 100 40 Z"
      />
      <g className="logo-cross" fill="#FFFFFF">
        <rect x="93" y="70" width="14" height="60" rx="3" />
        <rect x="70" y="93" width="60" height="14" rx="3" />
      </g>
    </svg>
  );
}
