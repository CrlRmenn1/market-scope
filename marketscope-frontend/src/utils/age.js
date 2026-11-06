// Age from a YYYY-MM-DD birthday. Reads the date parts directly, because
// new Date('YYYY-MM-DD') parses as UTC and can land on the previous local day.
export const computeAgeFromBirthday = (birthday, today = new Date()) => {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(birthday || ''));
  if (!match) return null;

  const [, year, month, day] = match.map(Number);
  const thisMonth = today.getMonth() + 1;
  const hadBirthdayThisYear = thisMonth > month || (thisMonth === month && today.getDate() >= day);
  return Math.max(0, today.getFullYear() - year - (hadBirthdayThisYear ? 0 : 1));
};

// Today as YYYY-MM-DD in local time, for a date input's max.
export const todayYmd = (today = new Date()) => {
  const month = String(today.getMonth() + 1).padStart(2, '0');
  const day = String(today.getDate()).padStart(2, '0');
  return `${today.getFullYear()}-${month}-${day}`;
};
