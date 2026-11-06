// Tone name ('high' | 'medium' | 'low') for a 0-100 viability score; used to pick badge colors.
// Same cut-offs as the backend verdict (constants/engine.py); new scans send their own tone.
export const getScoreTone = (score) => {
  const value = Number(score || 0);
  if (value >= 68) return 'high';
  if (value >= 47) return 'medium';
  return 'low';
};
