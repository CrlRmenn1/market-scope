import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { createPortal } from 'react-dom';
import useIsDesktop from '../utils/useIsDesktop';

const EASE_STANDARD = [0.16, 1, 0.3, 1];

// Reusable modal primitive. Renders the existing .sheet-overlay/.bottom-sheet
// pair (mobile: full-width sheet sliding up from the bottom; desktop: centered
// panel), but drives the transitions with Framer Motion instead of CSS
// keyframes so a panel can optionally morph out of the button that opened it.
//
// Pass `layoutId` matching a `motion.*` trigger element (e.g. a motion.button)
// to get the "grow from the button" effect. The morph only engages on desktop
// (>=768px, matching the existing .bottom-sheet breakpoint) — on mobile the
// panel keeps its familiar bottom-sheet slide-up, since morphing a small
// top-right button into a full-width bottom sheet reads as visual noise there.
export default function Modal({
  isOpen,
  onClose,
  layoutId,
  panelClassName = '',
  ariaLabel,
  children,
}) {
  const isDesktop = useIsDesktop(768);
  const shouldReduceMotion = useReducedMotion();
  const useMorph = isDesktop && !shouldReduceMotion && Boolean(layoutId);

  if (typeof document === 'undefined') return null;

  const panelInitial = useMorph
    ? false
    : isDesktop
      ? { opacity: 0, y: 20, scale: 0.95 }
      : { y: '100%' };

  const panelExit = useMorph
    ? { opacity: 0 }
    : isDesktop
      ? { opacity: 0, y: 20, scale: 0.97 }
      : { y: '100%' };

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className="sheet-overlay"
          role="presentation"
          onClick={onClose}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: shouldReduceMotion ? 0 : 0.22, ease: EASE_STANDARD }}
        >
          <motion.div
            // If the dropdown/trigger ever gains its own exit animation, this
            // button's rect would be measured mid-animation and the morph
            // would degrade — trigger and panel currently mount/unmount in
            // the same synchronous click handler, so the rect is stable.
            layoutId={useMorph ? layoutId : undefined}
            className={`bottom-sheet ${panelClassName}`}
            role="dialog"
            aria-modal="true"
            aria-label={ariaLabel}
            onClick={(event) => event.stopPropagation()}
            initial={panelInitial}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={panelExit}
            transition={{
              layout: { duration: shouldReduceMotion ? 0 : 0.38, ease: EASE_STANDARD },
              default: { duration: shouldReduceMotion ? 0 : 0.24, ease: EASE_STANDARD },
            }}
          >
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
