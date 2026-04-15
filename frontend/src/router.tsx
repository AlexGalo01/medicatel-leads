import { Navigate, createBrowserRouter } from "react-router-dom";

import { AppLayout } from "./layout";
import { JobStatusPage } from "./pages/JobStatusPage";
import { LeadDetailPage } from "./pages/LeadDetailPage";
import { LeadsPage } from "./pages/LeadsPage";
import { SearchPage } from "./pages/SearchPage";

export const appRouter = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/search" replace /> },
      { path: "search", element: <SearchPage /> },
      { path: "jobs/:jobId", element: <JobStatusPage /> },
      { path: "jobs/:jobId/leads", element: <LeadsPage /> },
      { path: "leads/:leadId", element: <LeadDetailPage /> },
    ],
  },
]);

