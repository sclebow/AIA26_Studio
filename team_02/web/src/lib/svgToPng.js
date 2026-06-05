// Export a live <svg> to a downloaded PNG. The plan styles itself with external
// CSS + CSS variables (e.g. rgb(var(--fg-rgb))), which a serialized SVG would lose,
// so we clone the node and inline the *computed* style of every element first.

const PROPS = [
  "fill", "fill-opacity", "fill-rule",
  "stroke", "stroke-width", "stroke-opacity", "stroke-dasharray", "stroke-linecap", "stroke-linejoin",
  "opacity", "color", "vector-effect",
  "font-family", "font-size", "font-weight", "text-anchor", "dominant-baseline", "letter-spacing",
];

function inlineStyles(src, dst) {
  const cs = getComputedStyle(src);
  let css = "";
  for (const p of PROPS) {
    const v = cs.getPropertyValue(p);
    if (v) css += `${p}:${v};`;
  }
  dst.setAttribute("style", css + (dst.getAttribute("style") || ""));
  const sc = src.children, dc = dst.children;
  for (let i = 0; i < sc.length && i < dc.length; i++) inlineStyles(sc[i], dc[i]);
}

export async function exportSvgToPng(svgEl, { filename = "sensi-plan.png", scale = 2, background = "#0d0d0d" } = {}) {
  if (!svgEl) return;
  const rect = svgEl.getBoundingClientRect();
  const w = Math.max(1, Math.round(rect.width));
  const h = Math.max(1, Math.round(rect.height));

  const clone = svgEl.cloneNode(true);
  inlineStyles(svgEl, clone);
  clone.setAttribute("width", String(w));
  clone.setAttribute("height", String(h));
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");

  const xml = new XMLSerializer().serializeToString(clone);
  const src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(xml);

  const img = new Image();
  await new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = reject;
    img.src = src;
  });

  const canvas = document.createElement("canvas");
  canvas.width = w * scale;
  canvas.height = h * scale;
  const ctx = canvas.getContext("2d");
  if (background) { ctx.fillStyle = background; ctx.fillRect(0, 0, canvas.width, canvas.height); }
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

  const url = canvas.toDataURL("image/png");
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}
