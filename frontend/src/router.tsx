import { Navigate, createBrowserRouter } from "react-router-dom";

import { RequireAuth } from "./auth/RequireAuth";
import { AppLayout } from "./layout";
import { OpportunityDetailPage } from "./features/opportunities/pages/OpportunityDetailPage";
import { OpportunitiesListPage } from "./features/opportunities/pages/OpportunitiesListPage";
import { AdminUsersPage } from "./pages/AdminUsersPage";
import { ExaResultsPage } from "./pages/ExaResultsPage";
import { JobExaResultDetailPage } from "./pages/JobExaResultDetailPage";
import { JobSearchWorkspacePage } from "./pages/JobSearchWorkspacePage";
import { LeadDetailPage } from "./pages/LeadDetailPage";
import { LoginPage } from "./pages/LoginPage";
import { SearchPage } from "./pages/SearchPage";

export const appRouter = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    path: "/",
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Navigate to="/search" replace /> },
      { path: "search", element: <SearchPage /> },
      { path: "busquedas", element: <ExaResultsPage /> },
      { path: "exa-results", element: <Navigate to="/busquedas" replace /> },
      { path: "jobs/:jobId/result/:resultIndex", element: <JobExaResultDetailPage /> },
      { path: "jobs/:jobId", element: <JobSearchWorkspacePage /> },
      { path: "jobs/:jobId/leads", element: <Navigate to=".." relative="path" replace /> },
      { path: "leads/:leadId", element: <LeadDetailPage /> },
      { path: "opportunities", element: <OpportunitiesListPage /> },
      { path: "opportunities/:opportunityId", element: <OpportunityDetailPage /> },
      { path: "admin/users", element: <AdminUsersPage /> },
    ],
  },
]);

