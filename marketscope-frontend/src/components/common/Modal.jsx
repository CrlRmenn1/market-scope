import { useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { createPortal } from 'react-dom';
import useIsDesktop from '../utils/useIsDesktop';

const EASE_STANDARD = [0.16, 1, 0.3, 1];

// Reusable modal primitive, driven by Framer Motion instead of CSS keyframes
// so panels get a real exit animation and can optionally morph out of the
// button that opened them.
//
// variant="sheet" (default) renders the existing .sheet-overlay/.bottom-sheet
// pair: a full-width sheet sliding up from the bottom on mobile, a centered
// panel on desktop. Morph only engages on desktop there — morphing a small
// top-right button into a full-width bottom sheet reads as visual noise on
// mobile.
//
// variant="center" is a plain always-centered card (confirm dialogs, info
// modals, etc.) with no mobile/desktop split, so morph is available at any
// width. Pass `overlayClassName`/`panelClassName` for the caller's own
// visual styling — Modal only supplies positioning/portal/animation.
//
// Pass `layoutId` matching a `motion.*` trigger element (e.g. a motion.button)
// to get the "grow from the button" effect.
export default function Modal({
  isOpen,
  onClose,
  layoutId,
  variant = 'sheet',
  overlayClassName = 'sheet-overlay',
  panelClassName = '',
  ariaLabel,
  ariaLabelledBy,
  children,
}) {
  const isDesktop = useIsDesktop(768);
  const shouldReduceMotion = useReducedMotion();

  // Many callers clear the data a panel's content — and, for per-instance
  // triggers, its `layoutId` itself — depends on (a "selected item", a
  // delete candidate, etc.) in the very same click that closes the modal.
  // `children` recomputed on this render can be null-derived garbage — or
  // throw outright — for the ~200-400ms the exit animation is still visibly
  // playing, and a `layoutId` that drops to undefined mid-close leaves the
  // *trigger* (which still declares that layoutId) as the sole remaining
  // claimant of a now-orphaned shared layout, so Framer Motion runs a stray
  // "reconcile" animation on the trigger itself to patch it up — visible as
  // the trigger button slowly sliding into place after a cancel.
  //
  // Freeze both the last real children and the last real layoutId while
  // `isOpen` is true, and keep using that frozen snapshot throughout the
  // close animation instead of whatever (possibly undefined/broken) values
  // this render produced. This only prevents a *crash* for children —
  // callers whose children access nullable data still need optional
  // chaining so evaluating them doesn't throw; the bad result just never
  // gets shown, since it's discarded here.
  //
  // "Adjusting state during render" (React-sanctioned pattern: a guarded
  // setState call in the render body, not an effect) — converges
  // immediately with no extra commit, and no ref-mutation-during-render.
  const [frozenChildren, setFrozenChildren] = useState(children);
  const [frozenLayoutId, setFrozenLayoutId] = useState(layoutId);
  if (isOpen) {
    if (frozenChildren !== children) setFrozenChildren(children);
    if (frozenLayoutId !== layoutId) setFrozenLayoutId(layoutId);
  }
  const renderedChildren = isOpen ? children : frozenChildren;
  const renderedLayoutId = isOpen ? layoutId : frozenLayoutId;

  // 'sheet' only morphs on desktop (see above); 'center' is the same
  // treatment at every width, so it can morph anywhere.
  const morphEligible = variant === 'center' || isDesktop;
  const useMorph = morphEligible && !shouldReduceMotion && Boolean(renderedLayoutId);

  if (typeof document === 'undefined') return null;

  const panelClass = variant === 'sheet' ? `bottom-sheet ${panelClassName}` : panelClassName;

  let panelInitial;
  let panelExit;
  if (useMorph) {
    panelInitial = false;
    panelExit = { opacity: 0 };
  } else if (variant === 'sheet') {
    panelInitial = isDesktop ? { opacity: 0, y: 20, scale: 0.95 } : { y: '100%' };
    panelExit = isDesktop ? { opacity: 0, y: 20, scale: 0.97 } : { y: '100%' };
  } else {
    panelInitial = { opacity: 0, y: 16, scale: 0.95 };
    panelExit = { opacity: 0, y: 10, scale: 0.96 };
  }

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className={overlayClassName}
          role="presentation"
          onClick={onClose}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: shouldReduceMotion ? 0 : 0.2, ease: EASE_STANDARD }}
        >
          <motion.div
            // If a trigger's own removal (e.g. a closing dropdown) ever gets
            // its own exit animation, its rect would be measured mid-motion
            // and the morph would degrade — every current trigger unmounts
            // synchronously in the same click handler that opens this
            // modal, so the rect is stable.
            layoutId={useMorph ? renderedLayoutId : undefined}
            className={panelClass}
            role="dialog"
            aria-modal="true"
            aria-label={ariaLabel}
            aria-labelledby={ariaLabelledBy}
            onClick={(event) => event.stopPropagation()}
            initial={panelInitial}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={panelExit}
            transition={{
              layout: { duration: shouldReduceMotion ? 0 : 0.38, ease: EASE_STANDARD },
              default: { duration: shouldReduceMotion ? 0 : (variant === 'center' ? 0.2 : 0.24), ease: EASE_STANDARD },
            }}
          >
            {renderedChildren}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
