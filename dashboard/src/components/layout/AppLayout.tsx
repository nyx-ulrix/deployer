import type { ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { ArrowLeftRight, ChevronDown, FolderKanban, Globe, HardDrive, History, LogOut, Server, UserRound } from "lucide-react";
import { useAuth } from "../../auth/auth-context";
import { cn } from "../../lib/cn";
import { Menu, MenuItem } from "../ui/Menu";
import { Avatar, Logo } from "./Brand";
import { ThemeToggle } from "./ThemeToggle";

export function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const name = user?.display_name || user?.email || "";
  const instanceSection = ["/settings/instance", "/settings/backups", "/settings/remote-access"].some((p) =>
    pathname.startsWith(p),
  );
  const go = (close: () => void, to: string) => {
    close();
    navigate(to);
  };

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 border-b border-border bg-surface/90 backdrop-blur supports-[backdrop-filter]:bg-surface/75">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-2 px-4 sm:gap-4">
          <Link to="/" className="shrink-0" aria-label="Deployer home">
            <Logo />
          </Link>
          <nav className="ml-2 hidden items-center gap-1 sm:flex">
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                cn(
                  "rounded-lg px-3 py-1.5 text-sm font-medium",
                  isActive ? "bg-surface-2 text-fg" : "text-muted hover:text-fg",
                )
              }
            >
              Projects
            </NavLink>
            <NavLink
              to="/settings/devices"
              className={({ isActive }) =>
                cn(
                  "rounded-lg px-3 py-1.5 text-sm font-medium",
                  isActive ? "bg-surface-2 text-fg" : "text-muted hover:text-fg",
                )
              }
            >
              Devices
            </NavLink>
            <NavLink
              to="/settings/transfer"
              className={({ isActive }) =>
                cn(
                  "rounded-lg px-3 py-1.5 text-sm font-medium",
                  isActive ? "bg-surface-2 text-fg" : "text-muted hover:text-fg",
                )
              }
            >
              Export &amp; import
            </NavLink>
            {user?.is_instance_owner && (
              <NavLink
                to="/settings/instance"
                className={() =>
                  cn(
                    "rounded-lg px-3 py-1.5 text-sm font-medium",
                    instanceSection ? "bg-surface-2 text-fg" : "text-muted hover:text-fg",
                  )
                }
              >
                Instance
              </NavLink>
            )}
          </nav>
          <div className="ml-auto flex items-center gap-1">
            <ThemeToggle />
            <Menu
              trigger={({ toggle, open }) => (
                <button
                  type="button"
                  onClick={toggle}
                  aria-expanded={open}
                  aria-haspopup="menu"
                  className="flex items-center gap-1.5 rounded-lg p-1 pr-2 hover:bg-surface-2"
                >
                  <Avatar name={name} src={user?.avatar_url} className="size-7" />
                  <ChevronDown className="size-4 text-muted" />
                  <span className="sr-only">Account menu</span>
                </button>
              )}
            >
              {(close) => (
                <>
                  <div className="border-b border-border px-2.5 pt-1.5 pb-2.5">
                    <p className="truncate text-sm font-medium">{user?.display_name || "Signed in"}</p>
                    <p className="truncate text-xs text-muted">{user?.email}</p>
                  </div>
                  <div className="py-1">
                    <MenuItem
                      icon={<FolderKanban />}
                      onClick={() => {
                        close();
                        navigate("/");
                      }}
                    >
                      Projects
                    </MenuItem>
                    <MenuItem
                      icon={<UserRound />}
                      onClick={() => {
                        close();
                        navigate("/settings/account");
                      }}
                    >
                      Account settings
                    </MenuItem>
                    <MenuItem icon={<HardDrive />} onClick={() => go(close, "/settings/devices")}>
                      Devices
                    </MenuItem>
                    <MenuItem
                      icon={<ArrowLeftRight />}
                      onClick={() => {
                        close();
                        navigate("/settings/transfer");
                      }}
                    >
                      Export &amp; import
                    </MenuItem>
                    {user?.is_instance_owner && (
                      <>
                        <div className="mx-2.5 mt-1.5 mb-1 border-t border-border pt-1.5 text-[11px] font-semibold tracking-wide text-muted uppercase">
                          Instance
                        </div>
                        <MenuItem
                          icon={<Server />}
                          onClick={() => {
                            close();
                            navigate("/settings/instance");
                          }}
                        >
                          Instance settings
                        </MenuItem>
                        <MenuItem icon={<History />} onClick={() => go(close, "/settings/backups")}>
                          Backups
                        </MenuItem>
                        <MenuItem icon={<Globe />} onClick={() => go(close, "/settings/remote-access")}>
                          Domains &amp; remote access
                        </MenuItem>
                      </>
                    )}
                  </div>
                  <div className="border-t border-border pt-1">
                    <MenuItem
                      icon={<LogOut />}
                      onClick={async () => {
                        close();
                        await logout();
                        navigate("/login", { replace: true });
                      }}
                    >
                      Sign out
                    </MenuItem>
                  </div>
                </>
              )}
            </Menu>
          </div>
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-4 py-5 sm:py-8">
        <Outlet />
      </main>
    </div>
  );
}

export function AuthShell({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex h-14 items-center justify-between px-4">
        <Link to="/" aria-label="Deployer home">
          <Logo />
        </Link>
        <ThemeToggle />
      </header>
      <main className="flex flex-1 items-start justify-center px-4 pt-4 pb-12 sm:items-center sm:pt-0">
        <div className={cn("w-full", wide ? "max-w-2xl" : "max-w-sm")}>{children}</div>
      </main>
    </div>
  );
}
