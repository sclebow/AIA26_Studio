import { motion } from "framer-motion";
import { DUR, EASE } from "../lib/motion.js";

// The Narrator — one ambient plain-language band (bottom-centre) that teaches the
// galaxy without redesigning it. It shows, in priority order:
//   1. the first-look orientation tour (when `tour` is set), with spotlight beats
//   2. a live readout of whatever the viewer hovers / a lens they point at (`readout`)
//   3. a gentle idle nudge otherwise
// Purely additive: the container ignores pointer events so the 3D scene stays
// draggable; only the small controls are interactive.
export default function GalaxyNarrator({ tour, readout, idle, onNext, onBack, onSkip, onHide }) {
  const inTour = !!tour;
  const isIdle = !inTour && !readout;
  const content = inTour ? tour.beat : readout || { tag: "", title: "", body: idle };
  const last = inTour && tour.index === tour.total - 1;

  return (
    <motion.div
      className="galaxy-guide"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 12 }}
      transition={{ duration: DUR.base, ease: EASE.out }}
    >
      <div className={"galaxy-guide-card" + (isIdle ? " is-idle" : "")}>
        {content.tag ? <div className="galaxy-guide-tag">{content.tag}</div> : null}
        {!isIdle && content.title ? <div className="galaxy-guide-title">{content.title}</div> : null}
        <div className="galaxy-guide-body">{content.body}</div>

        {inTour ? (
          <div className="galaxy-guide-controls">
            <button className="galaxy-guide-btn" onClick={onSkip}>skip</button>
            <div className="galaxy-guide-dots" aria-hidden="true">
              {Array.from({ length: tour.total }).map((_, i) => (
                <span key={i} className={"galaxy-guide-dot" + (i === tour.index ? " on" : "")} />
              ))}
            </div>
            <button className="galaxy-guide-btn" onClick={onBack} disabled={tour.index === 0}>back</button>
            <button className="galaxy-guide-btn is-primary" onClick={onNext}>{last ? "done" : "next →"}</button>
          </div>
        ) : (
          <button className="galaxy-guide-hide" onClick={onHide} title="hide the guide for a clean view">
            dismiss guide ×
          </button>
        )}
      </div>
    </motion.div>
  );
}
