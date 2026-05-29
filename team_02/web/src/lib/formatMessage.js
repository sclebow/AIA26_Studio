// Port of _formatChatMessage in index.html. Returns an HTML string for a Sensi
// message: extracts the "For Name (role), Layout-ID:" header, bolds **text**,
// and splits \n\n into paragraphs. Used via dangerouslySetInnerHTML in the
// chat bubble (the source already trusts this content from its own backend).
export function formatChatMessage(text) {
  let safe = String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  let headerHtml = "";
  safe = safe.replace(/^(For\s+[^,\n]+\([^)]+\)[^:\n]*:)\s*/, (_, h) => {
    headerHtml = '<span class="bubble-msg-header">' + h + "</span>";
    return "";
  });

  safe = safe.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

  let bodyHtml;
  if (safe.indexOf("\n\n") !== -1) {
    bodyHtml = safe
      .split(/\n\n+/)
      .map((p) => p.trim())
      .filter(Boolean)
      .map((p) => '<p class="bubble-msg-para">' + p + "</p>")
      .join("");
  } else {
    bodyHtml = '<p class="bubble-msg-para">' + safe.trim() + "</p>";
  }
  return headerHtml + bodyHtml;
}
