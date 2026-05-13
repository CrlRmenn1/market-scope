export const parseCoordinatePairText = (text) => {
  const rawText = String(text || '').trim();
  if (!rawText || !rawText.includes(',')) return null;

  const [latPart, lonPart, ...rest] = rawText.split(',');
  if (rest.length > 0) return null;

  const latitude = Number(String(latPart || '').trim());
  const longitude = Number(String(lonPart || '').trim());

  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;

  return { latitude, longitude };
};