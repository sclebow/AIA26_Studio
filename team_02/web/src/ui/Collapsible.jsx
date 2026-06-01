import { useState } from "react";

// Headless collapsible — owns ONLY the open/closed state and conditional body.
// It is deliberately opinion-free about markup: the caller renders its own
// trigger (a <div className="formula-toggle">, a <button className="fc-why-toggle">,
// …) via the `trigger` render-prop, so each call site keeps its exact styling.
// This is the "headless component" pattern: behavior is shared, presentation is
// not. Replaces three hand-rolled useState/{open && …} blocks.
export default function Collapsible({ defaultOpen = false, trigger, bodyClassName, bodyStyle, children }) {
  const [open, setOpen] = useState(defaultOpen);
  const toggle = () => setOpen((o) => !o);
  return (
    <>
      {trigger(open, toggle)}
      {open && (
        <div className={bodyClassName} style={bodyStyle}>{children}</div>
      )}
    </>
  );
}
