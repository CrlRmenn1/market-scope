import React from 'react';
import { InformationCircleIcon } from '@heroicons/react/24/outline';
import { Card, PageHeader, SkeletonRows } from '../../components/admin/ui/AdminUi';

const FloodZoneManager = React.lazy(() => import('../../components/admin/FloodZoneManager'));

// Preview of the flood-hazard and CLUP zoning overlays.
export default function MapLayersPage({ token }) {
  return (
    <>
      <PageHeader title="Map layers" description="Preview the flood-prone areas and CLUP zoning overlays, or import a GeoJSON layer to review it." />
      <div className="mb-5 flex items-start gap-3 rounded-xl border border-[var(--border-color)] bg-[var(--bg-sheet)] px-4 py-3 text-sm text-[var(--text-muted)]">
        <InformationCircleIcon className="mt-0.5 h-5 w-5 flex-none text-[var(--accent)]" aria-hidden="true" />
        <p>
          Imported layers can be previewed and edited here, but saving them is not connected to the backend yet. Scans use the
          flood data file in <code className="rounded bg-[var(--accent-hover)] px-1 text-[var(--text-main)]">data/flood/</code> and the built-in zoning areas.
        </p>
      </div>
      <Card className="min-w-0 overflow-hidden">
        <React.Suspense fallback={<SkeletonRows count={3} />}>
          <FloodZoneManager token={token} />
        </React.Suspense>
      </Card>
    </>
  );
}
