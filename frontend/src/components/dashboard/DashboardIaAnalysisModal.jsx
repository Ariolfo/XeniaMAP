import { useCallback, useMemo, useRef, useState } from "react";
import { getClientBrand } from "../../branding";
import { ensureMortalidadFigures } from "./customIaReports";
import useDashboardIaReport from "./useDashboardIaReport";

export function DigitalBrainIcon({ className, size = 22 }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <path
        d="M12 3.5c-1.2 0-2.2.55-2.85 1.4-.25-.08-.52-.12-.8-.12-1.1 0-2 .75-2.25 1.75-.85.25-1.45 1-1.45 1.9 0 .45.15.85.4 1.2-.15.35-.25.75-.25 1.15 0 .95.55 1.75 1.35 2.15v.85c0 1.15.9 2.1 2.05 2.1h.15c.55.95 1.55 1.6 2.7 1.6s2.2-.65 2.75-1.6h.2c1.1 0 2-.95 2-2.1v-.85c.85-.4 1.4-1.2 1.4-2.15 0-.4-.1-.8-.25-1.15.25-.35.4-.75.4-1.2 0-.9-.6-1.65-1.45-1.9-.25-1-1.15-1.75-2.25-1.75-.28 0-.55.04-.8.12C14.2 4.05 13.2 3.5 12 3.5Z"
        stroke="currentColor"
        strokeWidth="1.35"
        strokeLinejoin="round"
      />
      <circle cx="9" cy="10" r="0.9" fill="currentColor" />
      <circle cx="15" cy="10" r="0.9" fill="currentColor" />
      <path d="M12 12.2v2.2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
      <path
        d="M6.5 8.5h-1M17.5 8.5h1M7 14.5H6M18 14.5h-1M12 5.5V4"
        stroke="currentColor"
        strokeWidth="1"
        strokeLinecap="round"
        opacity="0.85"
      />
    </svg>
  );
}

/** `**negrita**` y `` `código` `` sin asteriscos/backticks sueltos (evita fallos con `**texto:**` etc.). */
function renderReportInline(text, keyPrefix) {
  const s = String(text);
  const out = [];
  let i = 0;
  let part = 0;
  const pushPlain = (from, to) => {
    if (from < to) out.push(<span key={`${keyPrefix}-p-${part++}`}>{s.slice(from, to)}</span>);
  };
  while (i < s.length) {
    if (s.slice(i, i + 2) === "**") {
      const j = s.indexOf("**", i + 2);
      if (j === -1) {
        pushPlain(i, s.length);
        break;
      }
      out.push(
        <strong key={`${keyPrefix}-b-${part++}`} className="adv-ia-strong">
          {s.slice(i + 2, j)}
        </strong>,
      );
      i = j + 2;
      continue;
    }
    if (s[i] === "`") {
      const j = s.indexOf("`", i + 1);
      if (j === -1) {
        pushPlain(i, s.length);
        break;
      }
      out.push(
        <code key={`${keyPrefix}-c-${part++}`} className="adv-ia-code">
          {s.slice(i + 1, j)}
        </code>,
      );
      i = j + 1;
      continue;
    }
    const ns = s.indexOf("**", i);
    const nb = s.indexOf("`", i);
    let next = s.length;
    if (ns >= 0) next = Math.min(next, ns);
    if (nb >= 0) next = Math.min(next, nb);
    pushPlain(i, next);
    i = next;
  }
  return out;
}

function parseTableRow(line) {
  const trimmed = String(line || "").trim();
  if (!trimmed.startsWith("|") || !trimmed.endsWith("|")) return null;
  const cells = trimmed
    .slice(1, -1)
    .split("|")
    .map((c) => c.trim());
  return cells.length ? cells : null;
}

function isTableSeparatorRow(line) {
  const cells = parseTableRow(line);
  if (!cells) return false;
  return cells.every((c) => /^:?-{3,}:?$/.test(c));
}

function parseImageLine(line) {
  const trimmed = String(line || "").trim();
  const m = trimmed.match(/^!\[([^\]]*)\]\((.+)\)$/);
  if (!m) return null;
  return { alt: m[1].trim(), src: m[2].trim() };
}

function parseCaptionLine(line) {
  const trimmed = String(line || "").trim();
  const m = trimmed.match(/^\*([^*]+)\*$/);
  if (!m) return null;
  return m[1].trim();
}

function formatBlocks(text) {
  const lines = String(text || "").split("\n");
  const blocks = [];
  let buf = [];
  let tableRows = [];

  const flushPara = () => {
    if (buf.length) {
      blocks.push(buf.join("\n"));
      buf = [];
    }
  };

  const flushTable = () => {
    if (!tableRows.length) return;
    const header = tableRows[0];
    const body = tableRows.slice(1);
    blocks.push({ type: "table", header, rows: body });
    tableRows = [];
  };

  for (const line of lines) {
    const row = parseTableRow(line);
    if (row && !isTableSeparatorRow(line)) {
      flushPara();
      tableRows.push(row);
      continue;
    }
    if (row && isTableSeparatorRow(line)) {
      continue;
    }
    flushTable();
    const image = parseImageLine(line);
    if (image) {
      flushPara();
      blocks.push({ type: "figure", alt: image.alt, src: image.src, caption: null });
      continue;
    }
    const caption = parseCaptionLine(line);
    if (caption && blocks.length && blocks[blocks.length - 1]?.type === "figure") {
      const prev = blocks[blocks.length - 1];
      if (!prev.caption) {
        blocks[blocks.length - 1] = { ...prev, caption };
        continue;
      }
    }
    if (line.startsWith("# ")) {
      flushPara();
      blocks.push({ type: "h1", text: line.slice(2).trim() });
    } else if (line.startsWith("## ")) {
      flushPara();
      blocks.push({ type: "h", text: line.slice(3).trim() });
    } else if (line.startsWith("### ")) {
      flushPara();
      blocks.push({ type: "h3", text: line.slice(4).trim() });
    } else if (line.trim() === "") {
      flushPara();
    } else {
      buf.push(line);
    }
  }
  flushTable();
  flushPara();
  return blocks;
}

function ReportFigure({ src, alt, caption, keyPrefix }) {
  return (
    <figure className="adv-ia-figure">
      <img
        className="adv-ia-figure-img"
        src={src}
        alt={alt || caption || "Figura del informe"}
        loading="lazy"
        onError={(e) => {
          e.currentTarget.style.display = "none";
          const msg = e.currentTarget.nextElementSibling;
          if (msg?.classList?.contains("adv-ia-figure-fallback")) return;
          const el = document.createElement("p");
          el.className = "adv-ia-figure-fallback";
          el.textContent = "No se pudo cargar la imagen. Recargue la pagina (Ctrl+F5).";
          e.currentTarget.parentElement?.appendChild(el);
        }}
      />
      {caption ? (
        <figcaption className="adv-ia-figure-caption">{caption}</figcaption>
      ) : null}
    </figure>
  );
}

function ReportTable({ header, rows, keyPrefix }) {
  return (
    <div className="adv-ia-table-wrap">
      <table className="adv-ia-table">
        <thead>
          <tr>
            {header.map((cell, ci) => (
              <th key={`${keyPrefix}-h-${ci}`}>{renderReportInline(cell, `${keyPrefix}-th-${ci}`)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={`${keyPrefix}-r-${ri}`}>
              {row.map((cell, ci) => (
                <td key={`${keyPrefix}-c-${ri}-${ci}`}>{renderReportInline(cell, `${keyPrefix}-td-${ri}-${ci}`)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function DashboardIaAnalysisModal({ open, onClose, iaContext, embedded = false, viewerEmail = "" }) {
  const printAreaRef = useRef(null);
  const [printing, setPrinting] = useState(false);

  const {
    fullReport,
    isCustom,
    reportLoading,
    reportReady: markdownReady,
    integralLoading,
    integralError,
    customLoading,
    customError,
  } = useDashboardIaReport(iaContext, { enabled: open || embedded });

  const blocks = useMemo(() => {
    let parsed = formatBlocks(fullReport);
    if (isCustom) parsed = ensureMortalidadFigures(parsed);
    return parsed;
  }, [fullReport, isCustom]);

  const reportReady = blocks.length > 0 && markdownReady;

  const handlePrintPdf = useCallback(async () => {
    const root = printAreaRef.current;
    if (!root || !reportReady) return;
    setPrinting(true);
    try {
      const imgs = root.querySelectorAll("img");
      await Promise.all(
        Array.from(imgs).map(
          (img) =>
            img.complete
              ? Promise.resolve()
              : new Promise((resolve) => {
                  img.addEventListener("load", resolve, { once: true });
                  img.addEventListener("error", resolve, { once: true });
                }),
        ),
      );
      document.body.classList.add("adv-ia-printing");
      const cleanup = () => {
        document.body.classList.remove("adv-ia-printing");
        setPrinting(false);
      };
      window.addEventListener("afterprint", cleanup, { once: true });
      window.print();
      window.setTimeout(() => {
        if (document.body.classList.contains("adv-ia-printing")) cleanup();
      }, 2000);
    } catch {
      setPrinting(false);
    }
  }, [reportReady]);

  if (!embedded && !open) return null;

  const brand = getClientBrand(viewerEmail);

  const reportWindow = (
      <div
        ref={printAreaRef}
        className={`adv-ia-window adv-ia-window--report adv-ia-print-area${isCustom ? " adv-ia-window--report-custom" : ""}${embedded ? " adv-ia-window--embedded" : ""}`}
      >
        <div className="adv-ia-header adv-ia-header--report">
          <div className="adv-ia-header-title">
            <DigitalBrainIcon className="adv-ia-header-icon adv-no-print" size={24} />
            <h3 id="adv-ia-report-title">
              {isCustom ? "Informe agronómico — Palma Vichada" : "Informe técnico (ingeniería agronómica)"}
            </h3>
          </div>
          <div className="adv-ia-header-actions adv-no-print">
            <button
              type="button"
              className="adv-ia-pdf-btn"
              onClick={handlePrintPdf}
              disabled={!reportReady || printing}
              title="Abre el diálogo de impresión; elija «Guardar como PDF» para descargar el informe tal como se ve aquí"
            >
              {printing ? "Preparando…" : "Guardar PDF"}
            </button>
            {!embedded ? (
              <button type="button" className="adv-close-btn" onClick={onClose} aria-label="Cerrar ventana">
                ×
              </button>
            ) : null}
          </div>
        </div>
        <p className="adv-ia-sub adv-ia-sub--report">
          {iaContext?.projectName ? `Proyecto: ${String(iaContext.projectName).trim()}` : null}
        </p>
        <div className="adv-ia-body adv-ia-body--report" role="document">
          {isCustom ? (
            <header className="adv-ia-report-hero">
              {brand.hideLogo ? null : (
                <img className="adv-ia-report-logo" src={brand.logoSrc} alt={brand.logoAlt} />
              )}
              <h2 className="adv-ia-report-hero-title">{brand.tagline}</h2>
            </header>
          ) : null}
          {customLoading ? (
            <p className="adv-ia-integral-status adv-no-print">Cargando informe Palma Vichada…</p>
          ) : null}
          {customError ? (
            <p className="adv-ia-integral-status adv-ia-integral-status--err adv-no-print">{customError}</p>
          ) : null}
          {!isCustom && integralLoading ? (
            <p className="adv-ia-integral-status adv-no-print">
              Analizando todas las escenas Planet en servidor (NDVI, RGB, textura)…
            </p>
          ) : null}
          {!isCustom && integralError ? (
            <p className="adv-ia-integral-status adv-ia-integral-status--err adv-no-print">
              No se pudo completar el análisis multi-escena: {integralError}
            </p>
          ) : null}
          {blocks.map((b, i) => {
            if (typeof b === "object" && b?.type === "h1") {
              const isMortalidad = /4\.\s*ANALISIS DE MORTALIDAD/i.test(String(b.text || ""));
              return (
                <h3
                  key={`h1-${i}`}
                  id={isMortalidad ? "informe-mortalidad" : undefined}
                  className="adv-ia-chapter-title"
                >
                  {renderReportInline(b.text, `h1-${i}`)}
                </h3>
              );
            }
            if (typeof b === "object" && b?.type === "h") {
              return (
                <h4 key={`h-${i}`} className="adv-ia-section-title">
                  {renderReportInline(b.text, `h-${i}`)}
                </h4>
              );
            }
            if (typeof b === "object" && b?.type === "h3") {
              return (
                <h5 key={`h3-${i}`} className="adv-ia-subsection-title">
                  {renderReportInline(b.text, `h3-${i}`)}
                </h5>
              );
            }
            if (typeof b === "object" && b?.type === "table") {
              return (
                <ReportTable
                  key={`tbl-${i}`}
                  keyPrefix={`tbl-${i}`}
                  header={b.header}
                  rows={b.rows}
                />
              );
            }
            if (typeof b === "object" && (b?.type === "figure" || b?.type === "image")) {
              return (
                <ReportFigure
                  key={`fig-${i}`}
                  keyPrefix={`fig-${i}`}
                  src={b.src}
                  alt={b.alt}
                  caption={b.caption || null}
                />
              );
            }
            return (
              <p key={`p-${i}`} className="adv-ia-paragraph">
                {String(b).split("\n").map((line, j) => (
                  <span key={j}>
                    {renderReportInline(line, `p-${i}-${j}`)}
                    {j < String(b).split("\n").length - 1 ? <br /> : null}
                  </span>
                ))}
              </p>
            );
          })}
        </div>
      </div>
  );

  if (embedded) {
    return (
      <div className="adv-ia-embedded" role="region" aria-labelledby="adv-ia-report-title">
        {reportWindow}
      </div>
    );
  }

  return (
    <div className="adv-ia-overlay" role="dialog" aria-modal="true" aria-labelledby="adv-ia-report-title">
      <div className="adv-ia-backdrop" onClick={onClose} />
      {reportWindow}
    </div>
  );
}
