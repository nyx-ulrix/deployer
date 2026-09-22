import { lazy, Suspense } from "react";
import { createBrowserRouter, Link, RouterProvider, useRouteError } from "react-router-dom";
import { RedirectIfAuthed, RequireAuth, RequireInstanceOwner, SetupGate } from "./auth/guards";
import { AppLayout, AuthShell } from "./components/layout/AppLayout";
import { PageSpinner } from "./components/ui/Spinner";
import { EmptyState, ErrorState } from "./components/ui/States";
import { AuthCompletePage } from "./features/auth/AuthCompletePage";
import { InvitePage } from "./features/auth/InvitePage";
import { LoginPage } from "./features/auth/LoginPage";
import { SignupPage } from "./features/auth/SignupPage";
import { DataTab } from "./features/data/DataTab";
import { BackupsTab } from "./features/backups/BackupsTab";
import { InstanceBackupsPage } from "./features/backups/InstanceBackupsPage";
import { DatabasesTab } from "./features/databases/DatabasesTab";
import { AppPage } from "./features/deploys/AppPage";
import { DeploysTab } from "./features/deploys/DeploysTab";
import { ApproveDevicePage } from "./features/devices/ApproveDevicePage";
import { DevicesPage } from "./features/devices/DevicesPage";
import { DeviceStatusPage } from "./features/devices/DeviceStatusPage";
import { ApiKeysTab } from "./features/projects/ApiKeysTab";
import { MembersTab } from "./features/projects/MembersTab";
import { OverviewTab } from "./features/projects/OverviewTab";
import { ProjectLayout } from "./features/projects/ProjectLayout";
import { ProjectSettingsTab } from "./features/projects/ProjectSettingsTab";
import { ProjectsPage } from "./features/projects/ProjectsPage";
import { AccountSettingsPage } from "./features/settings/AccountSettingsPage";
import { InstanceSettingsPage } from "./features/settings/InstanceSettingsPage";
import { RemoteAccessPage } from "./features/remote-access/RemoteAccessPage";
import { TransferPage } from "./features/settings/TransferPage";
import { SetupWizard } from "./features/setup/SetupWizard";

// React Flow + dagre are only needed on the Schema tab; CodeMirror only on the Query tab.
const SchemaTab = lazy(() => import("./features/schema/SchemaTab"));
const QueryTab = lazy(() => import("./features/query/QueryTab"));

function RouteError() {
  const error = useRouteError();
  return (
    <AuthShell wide>
      <ErrorState title="Something went wrong" error={error} onRetry={() => window.location.reload()} />
    </AuthShell>
  );
}

function NotFound() {
  return (
    <EmptyState
      title="Page not found"
      description="The page you're looking for doesn't exist."
      action={
        <Link to="/" className="text-sm font-medium text-accent hover:underline">
          Back to projects
        </Link>
      }
    />
  );
}

const router = createBrowserRouter([
  {
    element: <SetupGate />,
    errorElement: <RouteError />,
    children: [
      { path: "/setup", element: <SetupWizard /> },
      { path: "/device", element: <DeviceStatusPage /> },
      {
        path: "/login",
        element: (
          <RedirectIfAuthed>
            <LoginPage />
          </RedirectIfAuthed>
        ),
      },
      {
        path: "/signup",
        element: (
          <RedirectIfAuthed>
            <SignupPage />
          </RedirectIfAuthed>
        ),
      },
      { path: "/auth/complete", element: <AuthCompletePage /> },
      { path: "/invite/:token", element: <InvitePage /> },
      {
        element: <RequireAuth />,
        children: [
          // Focused page (no app chrome); the login redirect keeps `?code=`.
          { path: "/devices/approve", element: <ApproveDevicePage /> },
          {
            element: <AppLayout />,
            children: [
              { index: true, element: <ProjectsPage /> },
              {
                path: "/projects/:projectId",
                element: <ProjectLayout />,
                children: [
                  { index: true, element: <OverviewTab /> },
                  { path: "databases", element: <DatabasesTab /> },
                  {
                    path: "schema",
                    element: (
                      <Suspense fallback={<PageSpinner label="Loading schema viewer…" />}>
                        <SchemaTab />
                      </Suspense>
                    ),
                  },
                  { path: "data", element: <DataTab /> },
                  {
                    path: "query",
                    element: (
                      <Suspense fallback={<PageSpinner label="Loading query console…" />}>
                        <QueryTab />
                      </Suspense>
                    ),
                  },
                  { path: "backups", element: <BackupsTab /> },
                  { path: "deploys", element: <DeploysTab /> },
                  { path: "deploys/:appId", element: <AppPage /> },
                  { path: "members", element: <MembersTab /> },
                  { path: "api-keys", element: <ApiKeysTab /> },
                  { path: "settings", element: <ProjectSettingsTab /> },
                ],
              },
              { path: "/settings/account", element: <AccountSettingsPage /> },
              {
                path: "/settings/instance",
                element: (
                  <RequireInstanceOwner>
                    <InstanceSettingsPage />
                  </RequireInstanceOwner>
                ),
              },
              { path: "/settings/transfer", element: <TransferPage /> },
              { path: "/settings/devices", element: <DevicesPage /> },
              {
                path: "/settings/backups",
                element: (
                  <RequireInstanceOwner>
                    <InstanceBackupsPage />
                  </RequireInstanceOwner>
                ),
              },
              {
                path: "/settings/remote-access",
                element: (
                  <RequireInstanceOwner>
                    <RemoteAccessPage />
                  </RequireInstanceOwner>
                ),
              },
              { path: "*", element: <NotFound /> },
            ],
          },
        ],
      },
    ],
  },
]);

export function App() {
  return <RouterProvider router={router} />;
}
