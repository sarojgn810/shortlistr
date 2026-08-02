/** Decode HTML entities and strip tags for readable job-description text. */
export function plainJobDescription(raw: string, maxLen = 2000): string {
  if (!raw) return "";

  let text = raw
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, "&");

  if (typeof document !== "undefined") {
    const el = document.createElement("div");
    el.innerHTML = text;
    text = el.textContent || el.innerText || text;
  } else {
    text = text
      .replace(/<script[\s\S]*?<\/script>/gi, "")
      .replace(/<style[\s\S]*?<\/style>/gi, "")
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/p>/gi, "\n\n")
      .replace(/<[^>]+>/g, "");
  }

  text = text.replace(/\u00a0/g, " ").replace(/\n{3,}/g, "\n\n").trim();
  if (text.length > maxLen) return `${text.slice(0, maxLen)}…`;
  return text;
}
