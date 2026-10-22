// Thin outline icons (1.6 stroke), decorative: the buttons carry text labels.
const base = {
  width: 20,
  height: 20,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export const PlayIcon = () => (
  <svg {...base}>
    <path d="M8 5.5v13l10-6.5z" />
  </svg>
);
export const StopIcon = () => (
  <svg {...base}>
    <rect x="6.5" y="6.5" width="11" height="11" rx="2" />
  </svg>
);
export const MicIcon = () => (
  <svg {...base}>
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3" />
  </svg>
);
