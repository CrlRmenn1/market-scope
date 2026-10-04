// Tone name ('high' | 'medium' | 'low') for a 0-100 viability score; used to pick badge colors.
export const getScoreTone = (score) => {
  const value = Number(score || 0);
  if (value >= 75) return 'high';
  if (value >= 55) return 'medium';
  return 'low';
};
