import { Navigate, createBrowserRouter } from "react-router-dom";

import { RequireAuth } from "./auth/RequireAuth";
import { AppLayout } from "./layout";
import { DirectoriesListPage } from "./features/directories/pages/DirectoriesListPage";
import { DirectoryCreatePage } from "./features/directories/pages/DirectoryCreatePage";
import { DirectoryBoardPage } from "./features/directories/pages/DirectoryBoardPage";
import { DirectoryEditPage } from "./features/directories/pages/DirectoryEditPage";
import { OpportunitiesListPage } from "./features/opportunities/pages/OpportunitiesListPage";
import { OpportunityCreatePage } from "./features/opportunities/pages/OpportunityCreatePage";
import { OpportunityDetailPage } from "./features/opportunities/pages/OpportunityDetailPage";
import { AdminCreateUserPage } from "./pages/AdminCreateUserPage";
import { AdminUsersPage } from "./pages/AdminUsersPage";
import { JobExaResultDetailPage } from "./pages/JobExaResultDetailPage";
import { JobSearchWorkspacePage } from "./pages/JobSearchWorkspacePage";
import { LeadDetailPage } from "./pages/LeadDetailPage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { SearchPage } from "./pages/SearchPage";
import { UrlScrapeJobPage } from "./pages/UrlScrapeJobPage";

export const appRouter = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/registro", element: <RegisterPage /> },
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
      { path: "jobs/:jobId/result/:resultIndex", element: <JobExaResultDetailPage /> },
      { path: "jobs/:jobId", element: <JobSearchWorkspacePage /> },
      { path: "url-scrape-jobs/:jobId", element: <UrlScrapeJobPage /> },
      { path: "jobs/:jobId/leads", element: <Navigate to=".." relative="path" replace /> },
      { path: "leads/:leadId", element: <LeadDetailPage /> },
      { path: "directories", element: <DirectoriesListPage /> },
      { path: "directories/new", element: <DirectoryCreatePage /> },
      { path: "directories/:directoryId", element: <DirectoryBoardPage /> },
      { path: "directories/:directoryId/edit", element: <DirectoryEditPage /> },
      { path: "opportunities", element: <OpportunitiesListPage /> },
      { path: "opportunities/new", element: <OpportunityCreatePage /> },
      { path: "opportunities/:opportunityId", element: <OpportunityDetailPage /> },
      { path: "admin/users", element: <AdminUsersPage /> },
      { path: "admin/users/new", element: <AdminCreateUserPage /> },
    ],
  },
]);

