import React from 'react';
import { CheckCircleIcon, ExclamationTriangleIcon, MagnifyingGlassIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { inputClass } from './adminStyles';

// Shared building blocks for the admin console. Colors come from the app's theme
// tokens (styles/index.css), so light and dark mode follow the rest of MarketScope.
// Class strings for inputs and buttons live in adminStyles.js.

export function PageHeader({ title, description, actions }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="font-[family-name:var(--font-brand)] text-2xl font-semibold tracking-tight text-[var(--text-main)] lg:text-3xl">{title}</h1>
        {description && <p className="mt-1.5 max-w-2xl text-sm leading-6 text-[var(--text-muted)]">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ children, className = '' }) {
  return (
    <section className={`rounded-2xl border border-[var(--border-color)] bg-[var(--bg-sheet)] ${className}`}>
      {children}
    </section>
  );
}

export function CardHeader({ title, description, actions }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--border-color)] px-5 py-4">
      <div className="min-w-0">
        <h2 className="text-base font-semibold text-[var(--text-main)]">{title}</h2>
        {description && <p className="mt-0.5 text-sm text-[var(--text-muted)]">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

const STATUS_STYLES = {
  pending: { label: 'Pending', className: 'bg-[var(--trend-neutral-bg)] text-[var(--trend-neutral)]' },
  approved: { label: 'Approved', className: 'bg-[var(--trend-up-bg)] text-[var(--trend-up)]' },
  active: { label: 'Active', className: 'bg-[var(--trend-up-bg)] text-[var(--trend-up)]' },
  rejected: { label: 'Rejected', className: 'bg-[var(--trend-down-bg)] text-[var(--trend-down)]' },
  archived: { label: 'Archived', className: 'bg-[var(--accent-hover)] text-[var(--text-muted)]' },
  inactive: { label: 'Inactive', className: 'bg-[var(--accent-hover)] text-[var(--text-muted)]' }
};

// Colored pill with a dot and a text label, so status never relies on color alone.
export function StatusBadge({ status }) {
  const key = String(status || 'pending').toLowerCase();
  const style = STATUS_STYLES[key] || STATUS_STYLES.pending;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${style.className}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      {style.label}
    </span>
  );
}

export function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      {Icon && (
        <span className="mb-3 inline-flex h-11 w-11 items-center justify-center rounded-full bg-[var(--accent-hover)] text-[var(--accent)]">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </span>
      )}
      <p className="text-sm font-semibold text-[var(--text-main)]">{title}</p>
      {description && <p className="mt-1 max-w-sm text-sm text-[var(--text-muted)]">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Notice({ tone = 'success', children, onDismiss }) {
  const isError = tone === 'error';
  const Icon = isError ? ExclamationTriangleIcon : CheckCircleIcon;
  return (
    <div
      role={isError ? 'alert' : 'status'}
      aria-live={isError ? 'assertive' : 'polite'}
      className={`mb-5 flex items-start gap-3 rounded-xl border px-4 py-3 text-sm ${isError ? 'border-[var(--trend-down)] bg-[var(--trend-down-bg)] text-[var(--trend-down)]' : 'border-[var(--trend-up)] bg-[var(--trend-up-bg)] text-[var(--trend-up)]'}`}
    >
      <Icon className="mt-0.5 h-5 w-5 flex-none" aria-hidden="true" />
      <p className="min-w-0 flex-1 font-medium">{children}</p>
      {onDismiss && (
        <button type="button" onClick={onDismiss} className="-m-1 inline-flex h-8 w-8 flex-none cursor-pointer items-center justify-center rounded-lg hover:bg-black/5" aria-label="Dismiss message">
          <XMarkIcon className="h-4 w-4" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

export function Field({ label, required = false, hint, className = '', children }) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1.5 block text-sm font-medium text-[var(--text-main)]">
        {label}
        {required && <span className="ml-0.5 text-[var(--trend-down)]" aria-hidden="true">*</span>}
      </span>
      {children}
      {hint && <span className="mt-1.5 block text-xs text-[var(--text-muted)]">{hint}</span>}
    </label>
  );
}

export function SearchField({ value, onChange, placeholder, label = 'Search' }) {
  return (
    <div className="relative min-w-[min(100%,14rem)] flex-1">
      <MagnifyingGlassIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" aria-hidden="true" />
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label={label}
        className={`${inputClass} pl-9`}
      />
    </div>
  );
}

// Segmented control for switching views inside one page (not for page navigation).
export function SegmentedTabs({ tabs, value, onChange, ariaLabel }) {
  return (
    <div role="tablist" aria-label={ariaLabel} className="inline-flex max-w-full gap-1 overflow-x-auto rounded-xl border border-[var(--border-color)] bg-[var(--bg-sheet)] p-1">
      {tabs.map((tab) => {
        const isActive = tab.id === value;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(tab.id)}
            className={`inline-flex min-h-[40px] flex-none cursor-pointer items-center gap-2 rounded-lg px-3.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] ${isActive ? 'bg-[var(--accent-hover)] text-[var(--accent)]' : 'text-[var(--text-muted)] hover:text-[var(--text-main)]'}`}
          >
            {tab.label}
            {Number(tab.count) > 0 && (
              <span className="rounded-full bg-[var(--btn-primary-bg)] px-1.5 py-0.5 text-[0.7rem] font-bold leading-none tabular-nums text-[var(--btn-primary-text)]">{tab.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// Plain data table for the desktop layout; pages render cards on mobile instead.
export function DataTable({ columns, rows, rowKey, isRowHighlighted, caption }) {
  return (
    <div className="admin-table-wrap overflow-x-auto">
      <table className="admin-table w-full text-left text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col" className={column.className || ''}>{column.header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className={isRowHighlighted?.(row) ? 'is-highlighted' : ''}>
              {columns.map((column) => (
                <td key={column.key} className={column.className || ''}>{column.render(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SkeletonRows({ count = 4 }) {
  return (
    <div className="space-y-3 p-5" aria-hidden="true">
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="admin-skeleton h-12 rounded-xl" />
      ))}
    </div>
  );
}

// Small label/value pair used inside mobile cards and submission cards.
export function Detail({ label, children }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-[var(--text-muted)]">{label}</dt>
      <dd className="mt-0.5 break-words text-sm text-[var(--text-main)]">{children}</dd>
    </div>
  );
}
