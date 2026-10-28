import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { BUSINESS_TYPE_OPTIONS } from '../../utils/businessTypes';
import { ZONING_GROUPS } from '../../utils/zoneStyle';
import { CardHeader, SkeletonRows } from './ui/AdminUi';
import { buttonClass } from './ui/adminStyles';

// Which business types are allowed in each LGU zone. Zoning is pass/fail: a
// scan of an allowed business in the zone gets the full zoning score, any other
// business gets 0. The admin matches this to Panabo's zoning ordinance.

const SHORT_LABELS = {
  coffee: 'Coffee',
  print: 'Print',
  laundry: 'Laundry',
  carwash: 'Car wash',
  kiosk: 'Food kiosk',
  water: 'Water refill',
  bakery: 'Bakery',
  pharmacy: 'Pharmacy',
  barber: 'Barber/Salon',
  moto: 'Motorcycle',
  internet: 'Internet cafe',
  meat: 'Meat shop',
  hardware: 'Hardware'
};

const toSets = (allowed) => Object.fromEntries(
  Object.entries(allowed || {}).map(([zone, businesses]) => [zone, new Set(businesses)])
);

const sameTable = (a, b) => {
  const zones = new Set([...Object.keys(a), ...Object.keys(b)]);
  return [...zones].every((zone) => {
    const left = a[zone] || new Set();
    const right = b[zone] || new Set();
    return left.size === right.size && [...left].every((business) => right.has(business));
  });
};

export default function ZoningAllowedUses({ api, notify }) {
  const [saved, setSaved] = useState(null);
  const [table, setTable] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api('/admin/zoning-allowed-uses');
      const sets = toSets(data?.allowed);
      setSaved(sets);
      setTable(sets);
    } catch (error) {
      notify('error', error.message);
    }
  }, [api, notify]);

  useEffect(() => {
    load();
  }, [load]);

  const dirty = useMemo(() => Boolean(saved && table && !sameTable(saved, table)), [saved, table]);

  const toggle = (zone, business) => {
    setTable((current) => {
      const next = new Set(current[zone] || []);
      if (next.has(business)) next.delete(business);
      else next.add(business);
      return { ...current, [zone]: next };
    });
  };

  const setRow = (zone, allowAll) => {
    setTable((current) => ({ ...current, [zone]: new Set(allowAll ? BUSINESS_TYPE_OPTIONS.map((option) => option.value) : []) }));
  };

  const save = async () => {
    setSaving(true);
    try {
      const allowed = Object.fromEntries(Object.entries(table).map(([zone, businesses]) => [zone, [...businesses]]));
      const data = await api('/admin/zoning-allowed-uses', { method: 'PUT', body: { allowed } });
      const sets = toSets(data?.allowed);
      setSaved(sets);
      setTable(sets);
      notify('success', 'Allowed businesses saved. New scans use them now, and saved trend scans will refresh.');
    } catch (error) {
      notify('error', error.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <CardHeader
        title="Allowed businesses per zone"
        description="Tick the business types the zoning ordinance allows in each zone. Allowed scores full zoning points; not allowed scores 0."
        actions={(
          <>
            {dirty && <button type="button" className={buttonClass.ghost} onClick={() => setTable(saved)} disabled={saving}>Undo changes</button>}
            <button type="button" className={buttonClass.primary} onClick={save} disabled={!dirty || saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>
          </>
        )}
      />
      {!table ? <SkeletonRows count={4} /> : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">Business types allowed in each zone</caption>
            <thead>
              <tr className="border-b border-[var(--border-color)]">
                <th scope="col" className="sticky left-0 z-10 min-w-[220px] bg-[var(--bg-sheet)] px-4 py-2 text-left text-xs font-semibold text-[var(--text-muted)]">Zone</th>
                {BUSINESS_TYPE_OPTIONS.map((option) => (
                  <th key={option.value} scope="col" title={option.label} className="px-1 py-2 text-center text-[0.7rem] font-semibold leading-tight text-[var(--text-muted)]">
                    {SHORT_LABELS[option.value] || option.label}
                  </th>
                ))}
                <th scope="col" className="px-3 py-2 text-xs font-semibold text-[var(--text-muted)]"><span className="sr-only">Row actions</span></th>
              </tr>
            </thead>
            <tbody>
              {ZONING_GROUPS.map(([group, zones]) => (
                <React.Fragment key={group}>
                  <tr>
                    <th colSpan={BUSINESS_TYPE_OPTIONS.length + 2} scope="colgroup" className="sticky left-0 bg-[var(--bg-app)] px-4 py-1.5 text-left text-[0.7rem] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                      {group}
                    </th>
                  </tr>
                  {zones.map((zone) => {
                    const allowed = table[zone.id] || new Set();
                    return (
                      <tr key={zone.id} className="border-b border-[var(--border-color)] hover:bg-[var(--accent-hover)]">
                        <th scope="row" className="sticky left-0 z-10 bg-[var(--bg-sheet)] px-4 py-1.5 text-left font-medium text-[var(--text-main)]">
                          <span className="flex items-center gap-2">
                            <span className="h-3.5 w-3.5 flex-none rounded" style={{ background: zone.fill, boxShadow: `inset 0 0 0 2px ${zone.color}` }} aria-hidden="true" />
                            <span className="min-w-0">
                              {zone.label}
                              <span className="block text-[0.7rem] font-normal text-[var(--text-muted)]">{allowed.size ? `${allowed.size} allowed` : 'Nothing allowed'}</span>
                            </span>
                          </span>
                        </th>
                        {BUSINESS_TYPE_OPTIONS.map((option) => (
                          <td key={option.value} className="px-1 py-1.5 text-center">
                            <input
                              type="checkbox"
                              checked={allowed.has(option.value)}
                              onChange={() => toggle(zone.id, option.value)}
                              aria-label={`${option.label} allowed in ${zone.label}`}
                              className="h-4 w-4 cursor-pointer accent-[var(--accent)]"
                            />
                          </td>
                        ))}
                        <td className="whitespace-nowrap px-3 py-1.5 text-right">
                          <button type="button" className={buttonClass.rowAction} onClick={() => setRow(zone.id, allowed.size < BUSINESS_TYPE_OPTIONS.length)}>
                            {allowed.size < BUSINESS_TYPE_OPTIONS.length ? 'All' : 'None'}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
