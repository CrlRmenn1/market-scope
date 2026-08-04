import { useEffect, useState } from 'react';

// Tracks a min-width media query so card lists can render as two independent
// columns on desktop (expanding one card must not shift the other column).
export default function useIsDesktop(breakpoint = 1024) {
  const query = `(min-width: ${breakpoint}px)`;
  const [isDesktop, setIsDesktop] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(query).matches
  );

  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = (event) => setIsDesktop(event.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, [query]);

  return isDesktop;
}
