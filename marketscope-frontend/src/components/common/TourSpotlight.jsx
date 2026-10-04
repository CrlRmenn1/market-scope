import { useEffect, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { createPortal } from 'react-dom';

const EASE_STANDARD = [0.16, 1, 0.3, 1];
// Above app chrome (.app-header/.bottom-navbar: 1000) and .map-quick-panel
// (2600), below .tour-card (2700) so the instruction card always stays
// legible and clickable on top of the darkened backdrop.
const Z_INDEX = 2650;
const HOLE_PADDING = 8;

function unionRect(elements) {
  const rects = elements.filter(Boolean).map((el) => el.getBoundingClientRect());
  if (!rects.length) return null;
  const top = Math.min(...rects.map((r) => r.top));
  const left = Math.min(...rects.map((r) => r.left));
  const right = Math.max(...rects.map((r) => r.right));
  const bottom = Math.max(...rects.map((r) => r.bottom));
  return { top, left, width: right - left, height: bottom - top };
}

// Game-tutorial-style spotlight: darkens the whole screen and blocks clicks
// everywhere except a live-tracked cutout around the current tour step's
// target element(s) — the "hole" is just an absence of overlay at that
// screen region, so whatever sits there (the map, a form field...) stays
// fully visible and interactive, and is the *only* thing the user can
// interact with. `step` selects which ref(s) are the target; step 3 spans
// two separate elements (radius field + run button), so the cutout is
// their union rect rather than either one alone.
export default function TourSpotlight({ active, step, mapRef, businessTypeRef, radiusRef, actionsRef }) {
  const [rect, setRect] = useState(null);
  const shouldReduceMotion = useReducedMotion();

  useEffect(() => {
    if (!active) return undefined;

    const getElements = () => {
      if (step === 1) return [mapRef.current];
      if (step === 2) return [businessTypeRef.current];
      if (step === 3) return [radiusRef.current, actionsRef.current];
      return [];
    };

    // Poll the real position every frame instead of measuring once (or a
    // couple of times) right as the step changes. A one-shot measurement
    // can catch the target mid-layout — the quick-panel's open animation
    // still settling, a tab switch mid-repaint, or some other timing quirk
    // — and lock onto a stale/wrong box with nothing to ever correct it.
    // Polling means the spotlight is structurally unable to stay wrong: any
    // frame where the real position differs from what's currently drawn
    // gets picked up and corrected within ~16ms. Only calls setRect when
    // the value actually changed, so this is cheap and doesn't spam
    // re-renders once the target is stationary.
    let rafId;
    let lastKey = null;

    const tick = () => {
      const next = unionRect(getElements());
      const key = next ? `${next.top}|${next.left}|${next.width}|${next.height}` : null;
      if (key !== lastKey) {
        lastKey = key;
        setRect(next);
      }
      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);

    return () => cancelAnimationFrame(rafId);
    // Refs are stable across renders (React guarantees this), so only
    // `active`/`step` need to be real dependencies here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, step]);

  if (typeof document === 'undefined') return null;

  const move = { duration: shouldReduceMotion ? 0 : 0.4, ease: EASE_STANDARD };

  return createPortal(
    <AnimatePresence>
      {active && rect && (
        <motion.div
          key="tour-spotlight"
          style={{ position: 'fixed', inset: 0, zIndex: Z_INDEX, pointerEvents: 'none' }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: shouldReduceMotion ? 0 : 0.25, ease: EASE_STANDARD }}
        >
          {/* Four panels covering everything except rect (+ padding) — each
              blocks clicks and darkens/blurs its region; nothing is drawn
              over the hole itself, so it stays natively interactive. */}
          <motion.div
            className="tour-spotlight-mask"
            style={{ top: 0, left: 0, right: 0 }}
            animate={{ height: Math.max(0, rect.top - HOLE_PADDING) }}
            transition={move}
          />
          <motion.div
            className="tour-spotlight-mask"
            style={{ left: 0, right: 0, bottom: 0 }}
            animate={{ top: rect.top + rect.height + HOLE_PADDING }}
            transition={move}
          />
          <motion.div
            className="tour-spotlight-mask"
            style={{ left: 0 }}
            animate={{
              top: Math.max(0, rect.top - HOLE_PADDING),
              height: rect.height + HOLE_PADDING * 2,
              width: Math.max(0, rect.left - HOLE_PADDING),
            }}
            transition={move}
          />
          <motion.div
            className="tour-spotlight-mask"
            style={{ right: 0 }}
            animate={{
              top: Math.max(0, rect.top - HOLE_PADDING),
              height: rect.height + HOLE_PADDING * 2,
              left: rect.left + rect.width + HOLE_PADDING,
            }}
            transition={move}
          />
          {/* Decorative highlight ring around the hole; reuses the existing
              .tour-pulse glow (already reduced-motion-aware). */}
          <motion.div
            className="tour-spotlight-ring tour-pulse"
            animate={{
              top: rect.top - HOLE_PADDING,
              left: rect.left - HOLE_PADDING,
              width: rect.width + HOLE_PADDING * 2,
              height: rect.height + HOLE_PADDING * 2,
            }}
            transition={move}
          />
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
