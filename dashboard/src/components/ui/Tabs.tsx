import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { cn } from "../../lib/cn";

export type TabItem<T extends string> = { value: T; label: ReactNode; icon?: ReactNode; disabled?: boolean };

const tabClass = (active: boolean) =>
  cn(
    "inline-flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm font-medium whitespace-nowrap transition-colors",
    active ? "border-accent text-fg" : "border-transparent text-muted hover:text-fg hover:border-border-strong",
  );

/** Stateful tabs (controlled). */
export function Tabs<T extends string>({
  items,
  value,
  onChange,
  className,
}: {
  items: TabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKeyDown = (e: KeyboardEvent, index: number) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const dir = e.key === "ArrowRight" ? 1 : -1;
    let next = index;
    for (let i = 0; i < items.length; i++) {
      next = (next + dir + items.length) % items.length;
      if (!items[next].disabled) break;
    }
    refs.current[next]?.focus();
    onChange(items[next].value);
  };
  return (
    <div role="tablist" className={cn("flex overflow-x-auto border-b border-border [scrollbar-width:none] [&::-webkit-scrollbar]:hidden", className)}>
      {items.map((item, i) => (
        <button
          key={item.value}
          ref={(el) => {
            refs.current[i] = el;
          }}
          role="tab"
          type="button"
          aria-selected={item.value === value}
          tabIndex={item.value === value ? 0 : -1}
          disabled={item.disabled}
          onClick={() => onChange(item.value)}
          onKeyDown={(e) => onKeyDown(e, i)}
          className={cn(tabClass(item.value === value), "disabled:opacity-50")}
        >
          {item.icon}
          {item.label}
        </button>
      ))}
    </div>
  );
}

/** Route-driven tabs. */
export function NavTabs({
  items,
  className,
}: {
  items: { to: string; label: ReactNode; icon?: ReactNode; end?: boolean }[];
  className?: string;
}) {
  const navRef = useRef<HTMLElement>(null);
  const { pathname } = useLocation();
  // Keep the active tab visible on narrow screens.
  useEffect(() => {
    const active = navRef.current?.querySelector<HTMLElement>("a.active");
    active?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [pathname]);
  return (
    <nav ref={navRef} className={cn("-mx-4 flex overflow-x-auto border-b border-border [scrollbar-width:none] [&::-webkit-scrollbar]:hidden px-4 sm:mx-0 sm:px-0", className)}>
      {items.map((item) => (
        <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => tabClass(isActive)}>
          {item.icon}
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}
