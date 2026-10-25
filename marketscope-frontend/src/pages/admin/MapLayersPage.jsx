import React from 'react';
import { PageHeader, SkeletonRows } from '../../components/admin/ui/AdminUi';

const MapLayerStudio = React.lazy(() => import('../../components/admin/MapLayerStudio'));

// Flood hazard and zoning layers that every scan scores against.
export default function MapLayersPage({ api, notify, token }) {
  return (
    <>
      <PageHeader
        title="Map layers"
        description="Draw, trace or import the flood hazard and zoning areas that scans use. Each type has one active layer, limited to the dashed Panabo main area."
      />
      <React.Suspense fallback={<SkeletonRows count={4} />}>
        <MapLayerStudio api={api} notify={notify} token={token} />
      </React.Suspense>
    </>
  );
}
