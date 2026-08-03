/**
 * Markdown simple → HTML escapado (sin dependencias).
 * Soporta: párrafos, **negrita**, *cursiva*, `código`, #/##/###, listas -,
 * enlaces, imágenes ![alt](url) (http(s), /api/, /reports/, data:image/).
 */

function escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function isSafeImageSrc(src) {
  const s = String(src || "").trim();
  if (!s) return false;
  if (/^https?:\/\//i.test(s)) return true;
  if (s.startsWith("/api/")) return true;
  // Estáticos del frontend (p. ej. mapas de mortalidad en /public/reports/images/)
  if (s.startsWith("/reports/")) return true;
  if (/^data:image\/(png|jpe?g|gif|webp);base64,/i.test(s)) return true;
  return false;
}

function inlineMd(escapedLine) {
  let s = escapedLine;
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  s = s.replace(
    /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
  );
  return s;
}

export function renderSimpleMarkdown(md) {
  const raw = String(md || "").replace(/\r\n/g, "\n").trim();
  if (!raw) return "";

  const lines = raw.split("\n");
  const out = [];
  let listOpen = false;
  let para = [];

  const flushPara = () => {
    if (!para.length) return;
    const text = para.map((l) => inlineMd(escapeHtml(l))).join("<br/>");
    out.push(`<p>${text}</p>`);
    para = [];
  };

  const closeList = () => {
    if (listOpen) {
      out.push("</ul>");
      listOpen = false;
    }
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      flushPara();
      closeList();
      continue;
    }

    const image = trimmed.match(/^!\[([^\]]*)\]\(([^)\s]+)\)$/);
    if (image && isSafeImageSrc(image[2])) {
      flushPara();
      closeList();
      const alt = escapeHtml(image[1] || "imagen");
      const src = escapeHtml(image[2]);
      out.push(
        `<figure class="landing-md-figure"><img src="${src}" alt="${alt}" loading="lazy" /></figure>`
      );
      continue;
    }

    const heading = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      flushPara();
      closeList();
      const level = heading[1].length;
      out.push(`<h${level}>${inlineMd(escapeHtml(heading[2]))}</h${level}>`);
      continue;
    }

    const bullet = trimmed.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      flushPara();
      if (!listOpen) {
        out.push("<ul>");
        listOpen = true;
      }
      out.push(`<li>${inlineMd(escapeHtml(bullet[1]))}</li>`);
      continue;
    }

    closeList();
    para.push(trimmed);
  }
  flushPara();
  closeList();
  return out.join("\n");
}
