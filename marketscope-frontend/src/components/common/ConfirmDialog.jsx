import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import Modal from './Modal';
import { ConfirmContext } from './useConfirm';

// In-app replacement for window.confirm. Wrap the app in <ConfirmProvider>
// (main.jsx), then (useConfirm comes from ./useConfirm):
//
//   const confirm = useConfirm();
//   if (!(await confirm({ title: 'Delete "Bakery"?', message: '...', confirmLabel: 'Delete' }))) return;
//
// confirm() resolves true on the confirm button, false on Cancel, Escape or a
// click outside. tone="danger" (default) paints the confirm button red;
// tone="primary" uses the regular primary button.

const cancelClass =
  'inline-flex min-h-[44px] cursor-pointer items-center justify-center rounded-xl border border-[var(--border-color)] bg-[var(--bg-sheet)] px-4 text-sm font-medium text-[var(--text-main)] hover:bg-[var(--accent-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]';

const confirmClass = {
  danger:
    'inline-flex min-h-[44px] cursor-pointer items-center justify-center gap-2 rounded-xl bg-[var(--trend-down)] px-4 text-sm font-semibold text-white hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]',
  primary:
    'inline-flex min-h-[44px] cursor-pointer items-center justify-center gap-2 rounded-xl bg-[var(--btn-primary-bg)] px-4 text-sm font-semibold text-[var(--btn-primary-text)] hover:bg-[var(--btn-primary-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]'
};

export function ConfirmProvider({ children }) {
  const [request, setRequest] = useState(null);
  const resolverRef = useRef(null);

  const settle = useCallback((answer) => {
    resolverRef.current?.(answer);
    resolverRef.current = null;
    setRequest(null);
  }, []);

  const confirm = useCallback((options) => {
    // A second confirm replaces the first, which counts as cancelled.
    resolverRef.current?.(false);
    return new Promise((resolve) => {
      resolverRef.current = resolve;
      setRequest({ tone: 'danger', confirmLabel: 'Confirm', cancelLabel: 'Cancel', ...options });
    });
  }, []);

  useEffect(() => {
    if (!request) return undefined;
    const onKeyDown = (event) => {
      if (event.key === 'Escape') settle(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [request, settle]);

  const tone = request?.tone === 'primary' ? 'primary' : 'danger';

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <Modal
        isOpen={Boolean(request)}
        onClose={() => settle(false)}
        variant="center"
        overlayClassName="history-confirm-overlay"
        panelClassName="history-confirm-modal"
        ariaLabelledBy="app-confirm-title"
      >
        <div className="flex items-start gap-3">
          {tone === 'danger' && (
            <span className="mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--trend-down-bg)] text-[var(--trend-down)]">
              <ExclamationTriangleIcon className="h-5 w-5" aria-hidden="true" />
            </span>
          )}
          <div className="min-w-0">
            <h3 id="app-confirm-title" className="break-words text-lg font-semibold text-[var(--text-main)]">{request?.title}</h3>
            {request?.message && <div className="mt-2 text-sm leading-6 text-[var(--text-muted)]">{request.message}</div>}
          </div>
        </div>
        <div className="mt-5 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          {/* Cancel gets focus so Enter never confirms a destructive action by accident. */}
          <button type="button" className={cancelClass} onClick={() => settle(false)} autoFocus>
            {request?.cancelLabel}
          </button>
          <button type="button" className={confirmClass[tone]} onClick={() => settle(true)}>
            {request?.confirmLabel}
          </button>
        </div>
      </Modal>
    </ConfirmContext.Provider>
  );
}
