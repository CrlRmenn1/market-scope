// Shared Framer Motion layoutId strings, used to link a trigger element to the
// Modal panel it opens so the panel can morph out of the trigger's position/size.
// Kept in one place so components on either side of a trigger/modal pair don't
// need to import from each other just to share a string.

export const SPACE_SUBMISSION_TRIGGER_ID = 'space-submission-modal-panel';
export const LOGOUT_CONFIRM_TRIGGER_ID = 'logout-confirm-modal-panel';
export const BULK_DELETE_CONFIRM_TRIGGER_ID = 'bulk-delete-confirm-modal-panel';
export const PDF_SETTINGS_TRIGGER_ID = 'pdf-settings-modal-panel';

// The per-row History delete confirm intentionally does NOT use a layoutId
// (see the comment above that Modal call in History.jsx) — sharing a
// layoutId with a list item showed a stray "reconcile" animation on the
// trigger button after closing, a first-shared-transition rough edge under
// React StrictMode. Not worth it for a small icon button.
