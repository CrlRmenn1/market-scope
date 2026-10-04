// The profile fields a user must fill in before trend recommendations work.
export const REQUIRED_TREND_FIELDS = [
  'primary_business',
  'startup_capital',
  'preferred_setup',
  'target_payback_months'
];

export const normalizePreferenceValue = (value) => {
  if (value === null || value === undefined) return null;
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed ? trimmed : null;
  }
  return value;
};

export const getMissingTrendPreferenceFields = (user) => REQUIRED_TREND_FIELDS.filter((field) => normalizePreferenceValue(user?.[field]) === null);
