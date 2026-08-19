import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';

// Reused from the Leaflet L.divIcon pin marker drawn in Home.jsx (~line 527)
// so the loader's pin reads as the same mark, without touching the Leaflet
// marker's own .pure-pin/.pure-ring/.pure-pulse CSS at all.
const PIN_PATH = 'M12 2C8.14 2 5 5.14 5 9c0 4.38 4.62 9.44 6.29 11.16.37.38.98.38 1.35 0C14.38 18.44 19 13.38 19 9c0-3.86-3.14-7-7-7zm0 9.5A2.5 2.5 0 1 1 12 6a2.5 2.5 0 0 1 0 5.5z';

const DEFAULT_LABELS = [
  'Verifying CLUP Zoning Regulations',
  'Cross-referencing Hazard Risk Overlays',
  'Querying Live Market Saturation',
  'Calculating Demand Infrastructure',
];

const DEFAULT_STAGE_MS = 1500;
const FADE_MS = 400;
const EASE_STANDARD = [0.16, 1, 0.3, 1];

// Rapidly cycling 2-digit number for the "score" stage — deliberately never
// settles on a value, so it reads as "calculating" rather than previewing a
// (possibly wrong) real result.
function ScoreScramble() {
  const [value, setValue] = useState(() => Math.floor(Math.random() * 100));

  useEffect(() => {
    const id = setInterval(() => setValue(Math.floor(Math.random() * 100)), 80);
    return () => clearInterval(id);
  }, []);

  return (
    <motion.span
      key="score"
      className="analysis-loader__score"
      initial={{ opacity: 0, scale: 0.7 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.8 }}
    >
      {value}
    </motion.span>
  );
}

// Loops a small pin -> radius -> score -> verdict story for the duration of
// a real (progress-less) async wait. `active` mirrors the caller's own
// loading boolean — the loop just keeps running for however long that
// takes, it isn't tied to real progress.
//
// `labels` lets callers rephrase the 4 stage captions for their own context
// (e.g. "fetching a saved report" vs. "running a full analysis") without
// forking the component. `stageMs` controls how long each stage holds —
// shorter for loaders expected to be on-screen only briefly. Pass a stable
// (module-level or memoized) `labels` array, not an inline literal — it's a
// timer-loop dependency, so a new reference every render would keep
// restarting the loop instead of letting it advance.
export default function AnalysisLoader({ active, labels = DEFAULT_LABELS, stageMs = DEFAULT_STAGE_MS }) {
  const [stageIndex, setStageIndex] = useState(0);
  const [fading, setFading] = useState(false);
  const [verdict, setVerdict] = useState('pass');
  const shouldReduceMotion = useReducedMotion();
  const timerRef = useRef(null);

  useEffect(() => {
    // Callers only ever mount this component while `active` is true
    // (swapped in/out of an AnimatePresence branch, or otherwise gated by
    // the same condition), so a fresh mount already starts at stage 0 — no
    // need to reset state for the inactive case here, which would mean
    // calling setState synchronously in the effect body just to be
    // immediately unmounted.
    if (!active) return undefined;

    const advance = () => {
      setStageIndex((current) => {
        if (current + 1 < labels.length) {
          timerRef.current = setTimeout(advance, stageMs);
          return current + 1;
        }

        // Reached the last stage: fade everything out, flip the verdict for
        // next lap, then loop back to stage 0 (pin) — this reset was
        // missing before, which left stageIndex stuck at the last stage
        // forever (fading out and back in on the same verdict stage,
        // instead of actually restarting the pin -> radius -> score cycle).
        setFading(true);
        timerRef.current = setTimeout(() => {
          setFading(false);
          setVerdict((v) => (v === 'pass' ? 'fail' : 'pass'));
          setStageIndex(0);
          timerRef.current = setTimeout(advance, stageMs);
        }, FADE_MS);
        return current;
      });
    };

    timerRef.current = setTimeout(advance, stageMs);
    return () => clearTimeout(timerRef.current);
  }, [active, labels, stageMs]);

  if (!active) return null;

  const currentLabel = labels[stageIndex % labels.length];

  if (shouldReduceMotion) {
    // Real signal (the label still cycles) with no motion, rather than
    // relying on animation durations merely collapsing to near-zero.
    return (
      <div className="analysis-loader analysis-loader--static" role="status" aria-live="polite">
        <svg className="analysis-loader__icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d={PIN_PATH} />
        </svg>
        <p className="analysis-loader__label">{currentLabel}</p>
      </div>
    );
  }

  return (
    <div className="analysis-loader" role="status" aria-live="polite">
      <div className="analysis-loader__stage">
        <AnimatePresence mode="wait">
          {!fading && stageIndex === 0 && (
            <motion.svg
              key="pin"
              className="analysis-loader__icon"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
              initial={{ opacity: 0, scale: 0.6 }}
              animate={{
                opacity: 1,
                scale: [1, 1.08, 1],
                // Scoped to the `animate` target (not the shared component-level
                // transition prop) so this infinite pulse doesn't also govern the
                // exit transition below — an infinite-repeat animation never
                // "completes", so AnimatePresence's mode="wait" would otherwise
                // stall forever waiting for this exit to finish, and every later
                // stage (radius/score/verdict) would never get to mount.
                transition: { scale: { repeat: Infinity, duration: 0.9, ease: EASE_STANDARD }, opacity: { duration: 0.3, ease: EASE_STANDARD } },
              }}
              exit={{
                opacity: 0,
                scale: 0.7,
                transition: { duration: 0.3, ease: EASE_STANDARD },
              }}
            >
              <path d={PIN_PATH} />
            </motion.svg>
          )}

          {!fading && stageIndex === 1 && (
            <motion.div
              key="radius"
              className="analysis-loader__radius"
              aria-hidden="true"
              initial={{ opacity: 0, scale: 0.2 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 1.3 }}
              transition={{ duration: 0.5, ease: EASE_STANDARD }}
            />
          )}

          {!fading && stageIndex === 2 && <ScoreScramble />}

          {!fading && stageIndex === 3 && (
            <motion.svg
              key="verdict"
              className={`analysis-loader__verdict analysis-loader__verdict--${verdict}`}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
              initial={{ opacity: 0, scale: 0.5, rotate: -15 }}
              animate={{ opacity: 1, scale: 1, rotate: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.35, ease: EASE_STANDARD }}
            >
              {verdict === 'pass' ? (
                <path d="M20 6L9 17l-5-5" />
              ) : (
                <>
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </>
              )}
            </motion.svg>
          )}
        </AnimatePresence>
      </div>

      <AnimatePresence mode="wait">
        <motion.p
          key={currentLabel}
          className="analysis-loader__label"
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.25, ease: EASE_STANDARD }}
        >
          {currentLabel}
        </motion.p>
      </AnimatePresence>
    </div>
  );
}
