// The one table of URL → page. Adding a page = one line here (+ a sidebar entry in app/Layout.tsx).
import type { RouteObject } from 'react-router'
import { Layout } from '@/app/Layout'
import { RouteError } from '@/app/RouteError'
import OverviewPage from '@/features/overview/Page'
import PrioritiesPage from '@/features/priorities/ListPage'
import PriorityDetailPage from '@/features/priorities/DetailPage'
import MapPage from '@/features/map/Page'
import SimulatorPage from '@/features/simulator/Page'
import ReportsPage from '@/features/reports/Page'
import ImpactPage from '@/features/impact/Page'
import CitizenReportPage from '@/features/citizen-report/ReportPage'
import TrackPage from '@/features/citizen-report/TrackPage'

export const routes: RouteObject[] = [
  {
    // Policymaker pages share the sidebar layout. Each page has its own error boundary.
    element: <Layout />,
    errorElement: <RouteError />,
    children: [
      { path: '/', element: <OverviewPage />, errorElement: <RouteError /> },
      { path: '/priorities', element: <PrioritiesPage />, errorElement: <RouteError /> },
      { path: '/priorities/:id', element: <PriorityDetailPage />, errorElement: <RouteError /> },
      { path: '/map', element: <MapPage />, errorElement: <RouteError /> },
      { path: '/simulator', element: <SimulatorPage />, errorElement: <RouteError /> },
      { path: '/impact', element: <ImpactPage />, errorElement: <RouteError /> },
      { path: '/reports', element: <ReportsPage />, errorElement: <RouteError /> },
      { path: '*', element: <RouteError /> },
    ],
  },
  // Citizen pages: no sidebar, mobile-first.
  { path: '/report', element: <CitizenReportPage />, errorElement: <RouteError /> },
  { path: '/track', element: <TrackPage />, errorElement: <RouteError /> },
  { path: '/track/:trackingId', element: <TrackPage />, errorElement: <RouteError /> },
]
