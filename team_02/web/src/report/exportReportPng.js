// Export the report DOM (HTML, not SVG — so lib/svgToPng.js can't serialise it) to
// a PNG. html-to-image rasterises the node as currently rendered, so un-generated
// room images export as their placeholder — an honest snapshot of what the user made.
import { toPng } from "html-to-image";

export async function exportReportPng(node, filename = "sensi-report.png") {
  if (!node) return;
  // The content is max-width:920 + margin:0 auto. html-to-image would otherwise
  // bake those auto side-margins into the canvas (a wide image with the report
  // offset and dark bars on the sides). Pin the node's own box and zero the margin
  // so the PNG is exactly the report's width.
  const dataUrl = await toPng(node, {
    pixelRatio: 2,
    backgroundColor: "#0d0d0d",
    width: node.offsetWidth,
    height: node.scrollHeight,
    cacheBust: true,
    // The page loads Inter / JetBrains Mono from Google Fonts (cross-origin). html-to-image
    // tries to read their cssRules to inline @font-face and throws a SecurityError that
    // aborts the whole export. Skip font embedding — the fonts are already loaded in the
    // browser, so the rasterised text still uses them.
    skipFonts: true,
    style: { margin: "0" },
  });
  const a = document.createElement("a");
  a.href = dataUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}
