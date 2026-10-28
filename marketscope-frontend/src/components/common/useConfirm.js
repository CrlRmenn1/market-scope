import { createContext, useContext } from 'react';

// Filled by <ConfirmProvider> (ConfirmDialog.jsx); see that file for usage.
export const ConfirmContext = createContext(null);

export function useConfirm() {
  const confirm = useContext(ConfirmContext);
  if (!confirm) throw new Error('useConfirm() needs a <ConfirmProvider> above it.');
  return confirm;
}
