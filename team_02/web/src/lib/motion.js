// JS mirror of the CSS motion ladder (--dur-* / --ease-* in styles/global.css)
// for Framer Motion, which can't read CSS variables. Authoring the curve once
// here stops the easing array [0.22, 0.61, 0.36, 1] from being retyped by hand
// in every transition. Keep aligned with the CSS ladder.
export const DUR = { fast: 0.12, base: 0.22, slow: 0.42 };
export const EASE = {
  out: [0.22, 0.61, 0.36, 1],  // default settle  (mirror of --ease-out)
  soft: [0.4, 0, 0.2, 1],      // calm in/out      (mirror of --ease-soft)
};
