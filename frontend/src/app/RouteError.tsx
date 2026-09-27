import { isRouteErrorResponse, Link, useRouteError } from 'react-router'

/** Shown inside the layout when one page crashes; the sidebar and other pages keep working. */
export function RouteError() {
  const error = useRouteError()
  const notFound = isRouteErrorResponse(error) && error.status === 404
  return (
    <div role="alert" className="rounded-lg border border-line bg-surface p-6">
      <div className="font-medium">{notFound ? 'Page not found' : 'This page hit an error'}</div>
      <p className="mt-1 text-muted">
        {notFound ? 'There is nothing at this address.' : error instanceof Error ? error.message : 'Unexpected error.'}
      </p>
      <Link to="/" className="mt-3 inline-block text-accent">
        Back to overview
      </Link>
    </div>
  )
}
