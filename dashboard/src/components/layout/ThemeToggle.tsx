import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme, type ThemeMode } from "../../lib/theme";

const next: Record<ThemeMode, ThemeMode> = { system: "light", light: "dark", dark: "system" };
const labels: Record<ThemeMode, string> = { system: "System theme", light: "Light theme", dark: "Dark theme" };

export function ThemeToggle() {
  const { mode, setMode } = useTheme();
  const Icon = mode === "system" ? Monitor : mode === "light" ? Sun : Moon;
  return (
    <button
      type="button"
      onClick={() => setMode(next[mode])}
      className="inline-flex size-9 items-center justify-center rounded-lg text-muted hover:bg-surface-2 hover:text-fg"
      aria-label={`${labels[mode]} (click to switch)`}
      title={`${labels[mode]} — click to switch`}
    >
      <Icon className="size-4.5" />
    </button>
  );
}
