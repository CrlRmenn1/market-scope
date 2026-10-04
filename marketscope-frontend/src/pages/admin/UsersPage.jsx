import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { UsersIcon } from '@heroicons/react/24/outline';
import { getBusinessTypeLabel } from '../../utils/businessTypes';
import {
  Card,
  DataTable,
  Detail,
  EmptyState,
  PageHeader,
  SearchField,
  SkeletonRows
} from '../../components/admin/ui/AdminUi';
import { buttonClass } from '../../components/admin/ui/adminStyles';

const SETUP_LABELS = {
  kiosk: 'Kiosk',
  storefront: 'Storefront',
  roadside: 'Roadside',
  'market-stall': 'Market stall',
  warehouse: 'Warehouse'
};

const formatDate = (value) => {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
};

const Muted = ({ children }) => <span className="text-[var(--text-muted)]">{children}</span>;

// Read-only directory of registered users and their trend preferences.
export default function UsersPage({ api, notify, isDesktop }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api('/admin/users');
      setUsers(Array.isArray(data?.users) ? data.users : []);
    } catch (error) {
      notify('error', error.message);
    } finally {
      setLoading(false);
    }
  }, [api, notify]);

  useEffect(() => {
    load();
  }, [load]);

  const rows = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return users;
    return users.filter((user) =>
      [user.full_name, user.email, user.cellphone_number, user.address]
        .some((value) => String(value || '').toLowerCase().includes(query))
    );
  }, [users, search]);

  const businessOf = (user) => (user.primary_business ? getBusinessTypeLabel(user.primary_business) : <Muted>Not set</Muted>);
  const setupOf = (user) => (user.preferred_setup ? SETUP_LABELS[user.preferred_setup] || user.preferred_setup : <Muted>Not set</Muted>);

  return (
    <>
      <PageHeader title="Users" description="Everyone who registered in MarketScope, with the preferences used by Business Trends." />

      <Card className="min-w-0">
        <div className="flex flex-wrap items-center gap-3 border-b border-[var(--border-color)] px-5 py-4">
          <SearchField value={search} onChange={setSearch} placeholder="Search by name, email, phone or address" label="Search users" />
          <p className="text-sm tabular-nums text-[var(--text-muted)]">{rows.length} of {users.length}</p>
        </div>

        {loading ? (
          <SkeletonRows />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={UsersIcon}
            title={users.length === 0 ? 'No users yet' : 'No users match your search'}
            description={users.length === 0 ? 'Users appear here after they register in the app.' : 'Try a different name or email.'}
            action={users.length > 0 && <button type="button" className={buttonClass.secondary} onClick={() => setSearch('')}>Clear search</button>}
          />
        ) : isDesktop ? (
          <DataTable
            caption="Registered users"
            rows={rows}
            rowKey={(user) => user.user_id}
            columns={[
              {
                key: 'name',
                header: 'Name',
                render: (user) => (
                  <div className="min-w-0">
                    <p className="font-medium text-[var(--text-main)]">{user.full_name || 'Unnamed user'}</p>
                    <p className="text-xs tabular-nums text-[var(--text-muted)]">ID {user.user_id}</p>
                  </div>
                )
              },
              { key: 'email', header: 'Email', render: (user) => <span className="break-all">{user.email}</span> },
              { key: 'phone', header: 'Phone', className: 'tabular-nums whitespace-nowrap', render: (user) => user.cellphone_number || <Muted>-</Muted> },
              { key: 'business', header: 'Primary business', render: businessOf },
              { key: 'setup', header: 'Setup', render: setupOf },
              { key: 'joined', header: 'Joined', className: 'whitespace-nowrap tabular-nums', render: (user) => formatDate(user.created_at) }
            ]}
          />
        ) : (
          <ul className="divide-y divide-[var(--border-color)]">
            {rows.map((user) => (
              <li key={user.user_id} className="px-4 py-4">
                <p className="font-medium text-[var(--text-main)]">{user.full_name || 'Unnamed user'}</p>
                <p className="break-all text-sm text-[var(--text-muted)]">{user.email}</p>
                <dl className="mt-3 grid grid-cols-2 gap-3">
                  <Detail label="Primary business">{businessOf(user)}</Detail>
                  <Detail label="Setup">{setupOf(user)}</Detail>
                  <Detail label="Phone">{user.cellphone_number || <Muted>-</Muted>}</Detail>
                  <Detail label="Joined">{formatDate(user.created_at)}</Detail>
                </dl>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
