import React, { useState } from 'react';
import DataBackupButtons from '../../components/admin/ui/DataBackupButtons';
import { PageHeader, SkeletonRows } from '../../components/admin/ui/AdminUi';

const MapLayerStudio = React.lazy(() => import('../../components/admin/MapLayerStudio'));

// Flood hazard and zoning layers that every scan scores against.
export default function MapLayersPage({ api, notify, token }) {
  // Bumped after a backup upload so the studio remounts and reloads every layer.
  const [studioKey, setStudioKey] = useState(0);

  return (
    <>
      <PageHeader
        title="Map layers"
        description="Draw, trace or import the flood hazard and zoning areas that scans use. Each type has one active layer, limited to the dashed Panabo main area."
        actions={(
          <DataBackupButtons token={token} dataset="map-layers" label="map layers" notify={notify} onImported={() => setStudioKey((key) => key + 1)} />
        )}
      />
      <React.Suspense fallback={<SkeletonRows count={4} />}>
        <MapLayerStudio key={studioKey} api={api} notify={notify} token={token} />
      </React.Suspense>
    </>
  );
}
