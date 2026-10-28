import React, { useRef, useState } from 'react';
import { ArrowDownTrayIcon, ArrowUpTrayIcon } from '@heroicons/react/24/outline';
import { apiUrl } from '../../../lib/api';
import { buttonClass } from './adminStyles';
import { useConfirm } from '../../common/useConfirm';

const today = () => new Date().toISOString().slice(0, 10);

const readDetail = async (response) => {
  try {
    const data = await response.json();
    if (typeof data?.detail === 'string') return data.detail;
  } catch {
    // Not JSON; fall through to the status code.
  }
  return `Request failed (${response.status})`;
};

// Download / Upload buttons for one admin page's tables (backend: routers/data_backup.py).
// Download saves a JSON backup; Upload replaces this database's rows with a backup's,
// e.g. to copy the deployed data into a local database for debugging.
export default function DataBackupButtons({ token, dataset, label, notify, onImported }) {
  const fileInput = useRef(null);
  const [busy, setBusy] = useState('');
  const confirm = useConfirm();

  const download = async () => {
    setBusy('download');
    try {
      const response = await fetch(apiUrl(`/admin/backup/${dataset}`), { headers: { 'x-admin-token': token || '' } });
      if (!response.ok) throw new Error(await readDetail(response));
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = `marketscope-${dataset}-${today()}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      notify('error', error.message);
    } finally {
      setBusy('');
    }
  };

  const upload = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;

    let backup;
    try {
      backup = JSON.parse(await file.text());
    } catch {
      notify('error', `${file.name} is not a MarketScope backup file.`);
      return;
    }
    if (backup?.dataset !== dataset) {
      notify('error', `${file.name} holds ${backup?.dataset || 'unknown'} data. Upload it on its own page.`);
      return;
    }
    const confirmed = await confirm({
      title: `Replace all ${label} in this database?`,
      message: (
        <>
          <p className="break-all">
            From <span className="font-medium text-[var(--text-main)]">{file.name}</span>
            {backup.source_host && <> ({backup.source_host}, {backup.exported_at})</>}
          </p>
          <ul className="mt-2 list-disc pl-5">
            {Object.entries(backup.tables || {}).map(([table, { rows = [] } = {}]) => (
              <li key={table}><span className="tabular-nums">{rows.length}</span> rows in {table}</li>
            ))}
          </ul>
          <p className="mt-2">Rows that aren&apos;t in the file will be deleted. This cannot be undone.</p>
        </>
      ),
      confirmLabel: 'Replace data'
    });
    if (!confirmed) return;

    setBusy('upload');
    try {
      const form = new FormData();
      form.append('file', file);
      const response = await fetch(apiUrl(`/admin/backup/${dataset}`), {
        method: 'POST',
        headers: { 'x-admin-token': token || '' },
        body: form
      });
      if (!response.ok) throw new Error(await readDetail(response));
      const { summary = {} } = await response.json();
      const details = Object.entries(summary)
        .map(([table, { rows, removed }]) => `${table}: ${rows} rows${removed ? `, ${removed} removed` : ''}`)
        .join('; ');
      notify('success', `${label[0].toUpperCase()}${label.slice(1)} replaced from ${file.name}. ${details}.`);
      await onImported?.();
    } catch (error) {
      notify('error', error.message);
    } finally {
      setBusy('');
    }
  };

  return (
    <>
      <button type="button" className={buttonClass.secondary} onClick={download} disabled={Boolean(busy)}>
        <ArrowDownTrayIcon className="h-4 w-4" aria-hidden="true" />
        {busy === 'download' ? 'Downloading…' : 'Download data'}
      </button>
      <button type="button" className={buttonClass.secondary} onClick={() => fileInput.current?.click()} disabled={Boolean(busy)}>
        <ArrowUpTrayIcon className="h-4 w-4" aria-hidden="true" />
        {busy === 'upload' ? 'Uploading…' : 'Upload data'}
      </button>
      <input ref={fileInput} type="file" accept=".json,application/json" className="hidden" onChange={upload} />
    </>
  );
}
