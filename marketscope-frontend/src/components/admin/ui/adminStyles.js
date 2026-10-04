// Tailwind class strings shared by every admin form and button.

export const inputClass =
  'w-full min-h-[44px] rounded-xl border border-[var(--border-color)] bg-[var(--bg-app)] px-3 py-2 text-sm text-[var(--text-main)] outline-none transition-colors placeholder:text-[var(--text-muted)] focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--focus-ring)]';

const buttonBase =
  'inline-flex min-h-[44px] cursor-pointer items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] disabled:cursor-not-allowed disabled:opacity-50';

export const buttonClass = {
  primary: `${buttonBase} bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] hover:bg-[var(--btn-primary-hover)]`,
  secondary: `${buttonBase} border border-[var(--border-color)] bg-[var(--bg-sheet)] text-[var(--text-main)] hover:border-[var(--border-strong)] hover:bg-[var(--accent-hover)]`,
  ghost: `${buttonBase} text-[var(--text-muted)] hover:bg-[var(--accent-hover)] hover:text-[var(--text-main)]`,
  danger: `${buttonBase} text-[var(--trend-down)] hover:bg-[var(--trend-down-bg)]`,
  // Compact variants for table rows (still a 36px+ target with padding around it).
  rowAction: 'inline-flex min-h-[36px] cursor-pointer items-center rounded-lg px-3 text-sm font-medium text-[var(--accent)] transition-colors hover:bg-[var(--accent-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] disabled:cursor-not-allowed disabled:opacity-50',
  rowDanger: 'inline-flex min-h-[36px] cursor-pointer items-center rounded-lg px-3 text-sm font-medium text-[var(--trend-down)] transition-colors hover:bg-[var(--trend-down-bg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] disabled:cursor-not-allowed disabled:opacity-50'
};
