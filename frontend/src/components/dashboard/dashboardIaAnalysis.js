/**
 * Informe técnico integral a partir del estado del dashboard del proyecto.
 * Prioriza PlanetScope (RGB + índices), cruza Sentinel, clima, clusters y suelo.
 * Redacción orientada a palma aceitera en Colombia cuando el contexto del proyecto lo sugiere.
 */

const SENSOR_LABELS = { s1: "Sentinel-1 (SAR)", s2: "Sentinel-2 (multiespectral)", ps: "PlanetScope" };

function fmt(n, d = 2) {
  if (n == null || !Number.isFinite(Number(n))) return "—";
  return Number(n).toFixed(d);
}

function normIso(s) {
  return String(s || "").slice(0, 10);
}

function formatShortDate(iso) {
  const m = normIso(iso).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return String(iso || "").trim() || "—";
  return `${m[3]}/${m[2]}/${m[1]}`;
}

function meanFinite(arr) {
  const v = (arr || []).filter(Number.isFinite);
  if (!v.length) return NaN;
  return v.reduce((a, b) => a + b, 0) / v.length;
}

/** Contexto de cultivo inferido del nombre del proyecto (sin texto de “instrucciones”). */
function inferPalmContext(projectName) {
  const n = String(projectName || "").trim();
  const isPalm = /palma|palm|aceite|elaeis|oil\s*palm/i.test(n);
  let ageYears = null;
  const m10 = /(?:^|[^0-9])(10)\s*(?:años|anos|a|y|yr)|10a|diez/i.exec(n);
  if (m10) ageYears = 10;
  const md = /(\d{1,2})\s*(?:años|anos|a(?![-z])|yr)/i.exec(n);
  if (md && ageYears == null) {
    const y = parseInt(md[1], 10);
    if (y >= 4 && y <= 25) ageYears = y;
  }
  return { isPalm, ageYears, label: n || "Proyecto sin nombre" };
}

function pickPsIndexKey(seriesPs, preferred) {
  const pts = seriesPs?.points;
  if (!Array.isArray(pts) || !pts.length) return null;
  const keys = Object.keys(pts[0]?.by_index || {});
  if (preferred && keys.includes(preferred)) return preferred;
  if (keys.includes("NDVI")) return "NDVI";
  return keys[0] || null;
}

function planetHeterogeneityTrendBlock(seriesPs, preferredIndex) {
  const ix = pickPsIndexKey(seriesPs, preferredIndex);
  if (!ix) return "";
  const pts = [...(seriesPs?.points || [])].sort((a, b) => normIso(a.date).localeCompare(normIso(b.date)));
  const rows = [];
  for (const p of pts) {
    const row = p?.by_index?.[ix];
    const m = row?.mean;
    const st = row?.std;
    if (!Number.isFinite(m) || !Number.isFinite(st)) continue;
    rows.push({ date: normIso(p.date), mean: m, std: st });
  }
  const n = rows.length;
  if (n < 4) {
    return `Sobre **${ix}** (PlanetScope) solo hay **${n}** escenas con media y desviación espacial agregadas válidas; la lectura de lucanas o palmas sin dosel debe apoyarse sobre todo en la **serie RGB** fecha a fecha.`;
  }
  const third = Math.max(1, Math.floor(n / 3));
  const early = rows.slice(0, third);
  const late = rows.slice(n - third);
  const stdE = meanFinite(early.map((r) => r.std));
  const stdL = meanFinite(late.map((r) => r.std));
  const mnE = meanFinite(early.map((r) => r.mean));
  const mnL = meanFinite(late.map((r) => r.mean));
  const dStd = stdL - stdE;
  const dMn = mnL - mnE;
  const d0 = early[0]?.date;
  const d1 = early[early.length - 1]?.date;
  const d2 = late[0]?.date;
  const d3 = late[late.length - 1]?.date;

  let frag = "";
  if (dStd > 0.018) {
    frag = `La **desviación típica espacial** de **${ix}** en Planet **aumenta** del bloque temporal ${d0}–${d1} al ${d2}–${d3} (Δstd ≈ ${fmt(dStd)}). En palma adulta esto suele leerse como **mayor heterogeneidad de dosel**: más claros, fallas o manchas que no eran tan dominantes al inicio de la serie; conviene contrastar con RGB en esas mismas ventanas.`;
  } else if (dStd < -0.018) {
    frag = `La desviación espacial de **${ix}** **se reduce** entre el tramo inicial (${d0}–${d1}) y el final (${d2}–${d3}) (Δstd ≈ ${fmt(dStd)}), compatible con dosel algo **más uniforme** en fechas recientes (menos textura “quebrada” a escala de parcela), sin descartar efectos de iluminación o brillo por escena.`;
  } else {
    frag = `La dispersión espacial agregada de **${ix}** apenas cambia entre tercios inicial y final (Δstd ≈ ${fmt(dStd)}). Eso no descarta lucanas puntuales: a esta resolución agregada el promedio puede **enmascarar** huecos localizados que sí aparecen en **RGB Planet**.`;
  }

  let meanLn = "";
  if (dMn < -0.06) {
    meanLn = ` La media espacial de **${ix}** cae en el tramo reciente (Δmedia ≈ ${fmt(dMn)}), compatible con menor biomasa foliar visible o mayor exposición de suelo/interfila; debe cruzarse con sequía, radiación o eventos de manejo en esas fechas.`;
  } else if (dMn > 0.06) {
    meanLn = ` La media de **${ix}** sube al final de la serie (Δmedia ≈ +${fmt(dMn)}), alineado con recuperación vegetativa o menor estrés hídrico en ese tramo.`;
  }

  return `${frag}${meanLn}`;
}

function sceneAnchorParagraph(activeSceneDate, activeSensorKey, activeIndexKey) {
  const iso = normIso(activeSceneDate);
  const sk = activeSensorKey || "ps";
  const ix = String(activeIndexKey || "NDVI").trim() || "NDVI";
  const label = SENSOR_LABELS[sk] || sk;
  if (!iso) {
    return `Las series y el bloque multi-escena describen el **lote completo**; al desplazar el timelapse, cada fecha de **Planet RGB** aporta una lectura fina de claros y dosel.`;
  }
  return `La escena **${formatShortDate(iso)}** en **${label}** (índice **${ix}**) sirve como **referencia visual** en el visor; el juicio agronómico siguiente se apoya en la **trayectoria completa** de fechas y sensores, no solo en ese fotograma.`;
}

function indexMeansTrajectory(seriesData, indexKey) {
  const pts = Array.isArray(seriesData?.points) ? seriesData.points : [];
  const out = [];
  for (const p of pts) {
    const row = p?.by_index?.[indexKey];
    const m = row?.mean;
    if (Number.isFinite(m)) out.push({ date: normIso(p.date), mean: m });
  }
  return out;
}

function largestMeanDrop(traj) {
  if (traj.length < 2) return null;
  let best = null;
  for (let i = 1; i < traj.length; i += 1) {
    const drop = traj[i - 1].mean - traj[i].mean;
    if (drop > 0.03 && (!best || drop > best.drop)) best = { drop, from: traj[i - 1], to: traj[i] };
  }
  return best;
}

function largestMeanRise(traj) {
  if (traj.length < 2) return null;
  let best = null;
  for (let i = 1; i < traj.length; i += 1) {
    const rise = traj[i].mean - traj[i - 1].mean;
    if (rise > 0.03 && (!best || rise > best.rise)) best = { rise, from: traj[i - 1], to: traj[i] };
  }
  return best;
}

function pickClimateRows(climateBySensor) {
  for (const k of ["ps", "s2", "s1"]) {
    const rows = climateBySensor?.[k];
    if (Array.isArray(rows) && rows.length) return rows;
  }
  return [];
}

function summarizeClimateVar(rows, key) {
  const vals = rows.map((r) => Number(r?.[key])).filter(Number.isFinite);
  if (!vals.length) return null;
  return {
    min: Math.min(...vals),
    max: Math.max(...vals),
    mean: vals.reduce((a, b) => a + b, 0) / vals.length,
    n: vals.length,
  };
}

function clusterInventorySummary(clusterBySensor) {
  const parts = [];
  for (const sk of ["ps", "s2", "s1"]) {
    const arr = clusterBySensor?.[sk] || [];
    if (!arr.length) {
      parts.push(`${SENSOR_LABELS[sk]}: sin modelos GMM en inventario.`);
      continue;
    }
    const labels = arr.map((r) => r.label || r.key).filter(Boolean);
    parts.push(
      `${SENSOR_LABELS[sk]}: **${arr.length}** salida(s) GMM (${labels.slice(0, 5).join(", ")}${labels.length > 5 ? "…" : ""}).`,
    );
  }
  return parts;
}

function smartClusterDetailLines(psSt) {
  const slots = [
    {
      n: 1,
      title: "Smart cluster 1",
      indices: "NDVI, NDRE, NDWI, VARI",
      palm:
        "En palma, trayectorias conjuntas de verdor y humedad foliar suelen separar **núcleo productivo** de **zonas con más estrés hídrico o suelo expuesto**; colores periféricos persistentes merecen cruce con borde de recorte y accesos.",
    },
    {
      n: 2,
      title: "Smart cluster 2",
      indices: "EVI, NDRE, NDWI, VARI",
      palm:
        "EVI ayuda cuando el dosel está denso: resalta **estructura vertical** frente a NDVI saturado; útil para ver si el bloque central mantiene arquitectura de copa homogénea en el tiempo.",
    },
    {
      n: 3,
      title: "Smart cluster 3",
      indices: "KNDVI, MCARI, NDWI, VARI",
      palm:
        "MCARI/KNDVI son sensibles a **pigmentación y estado fotosintético**; en lotes de ~10 años pueden marcar manchas de estrés nutricional o senescencia desigual si se mantienen estables en varias fechas.",
    },
  ];
  return slots.map((s) => {
    const st = psSt?.[s.n] || {};
    let estado = "";
    if (st.busy) estado = "Estado actual: en carga.";
    else if (st.error) estado = `Estado: error al generar mapa (${String(st.error).slice(0, 90)}).`;
    else if (st.preview) estado = "Salida cartográfica disponible en el dashboard.";
    else estado = "Aún sin mapa (stack de índices PS incompleto o no calculado).";
    return `**${s.title}** (${s.indices}). ${estado} ${s.palm}`;
  });
}

function soilLines(clientSoilSummary, hasGeofisica, soilDemInfo) {
  const lines = [];
  if (!hasGeofisica && !soilDemInfo?.dem_roi_mean) {
    lines.push("No hay resultados guardados de **Smart Soil** ni DEM de geofísica visibles para este cliente; la interpretación de bordes o clases periféricas queda acotada a imagen y clima.");
    return lines;
  }
  for (const vk of ["fast", "matlab"]) {
    const s = clientSoilSummary?.[vk];
    if (!s?.saved_at && !s?.n_clusters) continue;
    lines.push(
      `**${vk === "fast" ? "Smart Soil Fast" : "Smart Soil Mat"}:** K=${s.n_clusters ?? "—"}, muestras ${s.total_samples_placed ?? "—"}/${s.total_samples ?? "—"}, último guardado ${s.saved_at ?? "—"}.`,
    );
  }
  if (soilDemInfo?.dem_roi_mean != null && Number.isFinite(Number(soilDemInfo.dem_roi_mean))) {
    lines.push(`Relieve (DEM en ROI): media de elevación ≈ **${fmt(soilDemInfo.dem_roi_mean, 1)}** m.`);
  }
  if (soilDemInfo?.cv_mean != null && Number.isFinite(Number(soilDemInfo.cv_mean))) {
    lines.push(`Coeficiente de variación edáfico agregado (última corrida): **${fmt(soilDemInfo.cv_mean, 3)}**.`);
  }
  if (!lines.length) lines.push("Geofísica habilitada pero sin metadatos completos de suelo en esta vista.");
  return lines;
}

function sensorInventoryLines(sensorData) {
  return ["ps", "s2", "s1"].map((sk) => {
    const inv = sensorData?.[sk];
    if (!inv?.indices?.length) return `${SENSOR_LABELS[sk]}: sin stacks indexados.`;
    const nFrames = Object.values(inv.framesByIndex || {}).reduce((m, fr) => Math.max(m, (fr || []).length), 0);
    return `${SENSOR_LABELS[sk]}: **${nFrames}** escena(s) indexadas; bandas de índice {${inv.indices.slice(0, 10).join(", ")}${inv.indices.length > 10 ? "…" : ""}}.`;
  });
}

function seriesDetailParagraph(sensorKey, seriesData, indexKey) {
  if (!seriesData?.points?.length && !seriesData?.dates?.length) {
    return `${SENSOR_LABELS[sensorKey]}: sin serie temporal cargada para este proyecto.`;
  }
  const ts = seriesData?.temporal_stats?.[indexKey];
  const traj = indexMeansTrajectory(seriesData, indexKey);
  const drop = largestMeanDrop(traj);
  const rise = largestMeanRise(traj);
  const n = traj.length;
  const bits = [`**${n}** fechas con media válida de **${indexKey}**.`];
  if (ts?.mean != null) bits.push(`Media global de la serie: **${fmt(ts.mean)}** (σ **${fmt(ts.std)}**).`);
  if (drop && drop.drop >= 0.05) {
    bits.push(
      `Caída acentuada **${drop.from.date} → ${drop.to.date}** (Δ ≈ **${fmt(drop.drop)}**); en palma suele buscarse coherencia con **RGB Planet** (claros nuevos) y con **estrés térmico o déficit hídrico** en el mismo intervalo.`,
    );
  }
  if (rise && rise.rise >= 0.05) {
    bits.push(`Repunte **${rise.from.date} → ${rise.to.date}** (Δ ≈ **+${fmt(rise.rise)}**), compatible con recuperación vegetativa o lluvias favorables después de un tramo seco.`);
  }
  const pp = seriesData?.per_pixel;
  if (pp?.n_sampled) bits.push(`Curvas por píxel muestreadas: **n=${pp.n_sampled}**.`);
  return bits.join(" ");
}

function palmIntroBlock(ctx) {
  const { isPalm, ageYears, label } = inferPalmContext(ctx.projectName);
  if (!isPalm) {
    const ageBit =
      ageYears != null ? ` Antigüedad aproximada **~${ageYears} años** si el identificador del lote es representativo.` : "";
    return `Lote **«${label}»**.${ageBit} Se prioriza **PlanetScope** (RGB + índices de alta cadencia), con apoyo de Sentinel-2, Sentinel-1, agroclima y modelos de zona espectral.`;
  }
  const ageBit =
    ageYears != null
      ? ` Stand con antigüedad en torno a **~${ageYears} años**.`
      : " Antigüedad de plantación **no acotada** desde el identificador del lote; el cierre del dosel y la distribución espacial de claros aportan la referencia de “edad fisiológica” del bloque.";
  return (
    `Lote **«${label}»**, interpretado como **palma aceitera africana (*Elaeis guineensis*)** en **Colombia**.${ageBit} ` +
    "A esta etapa el dosel tiende a estar **cerrado**; la rentabilidad agronómica depende de **uniformidad del stand**, control de **lucanas** y del **estrés abiótico** (sequías, picos térmicos, radiación). " +
    "Lo que sigue sintetiza **únicamente** imágenes, índices, clima y salidas de suelo/cluster ya calculadas en XeniaMAP para este polígono."
  );
}

function climateParagraph(rows) {
  if (!rows.length) return "No hay serie agroclimática alineada al centroide del proyecto para el periodo mostrado.";
  const p = summarizeClimateVar(rows, "precip");
  const t = summarizeClimateVar(rows, "temp");
  const r = summarizeClimateVar(rows, "radiation");
  const h = summarizeClimateVar(rows, "humidity");
  const bits = [];
  if (p) bits.push(`Precipitación mensual en ventana de escenas: **${fmt(p.min, 1)}–${fmt(p.max, 1)}** mm (media **${fmt(p.mean, 1)}**).`);
  if (t) bits.push(`Temperatura: **${fmt(t.min, 1)}–${fmt(t.max, 1)}** °C (media **${fmt(t.mean, 1)}**).`);
  if (r) bits.push(`Radiación: **${fmt(r.min, 1)}–${fmt(r.max, 1)}** MJ/m² (media **${fmt(r.mean, 1)}**).`);
  if (h) bits.push(`Humedad relativa: **${fmt(h.min, 1)}–${fmt(h.max, 1)}** % (media **${fmt(h.mean, 1)}**).`);
  const d0 = normIso(rows[0]?.date);
  const d1 = normIso(rows[rows.length - 1]?.date);
  const palm =
    " En palma en Llanos y piedemonte, **ondas secas prolongadas** o **noches calientes** consecutivas suelen preceder caídas de verdor en índices; **lluvias intensas** pueden homogeneizar brillo en RGB sin reflejar alivio nutricional.";
  return `Agroclima (${d0} → ${d1}): ${bits.join(" ")}${palm}`;
}

function planetSceneCalendar(sensorData) {
  const fr = sensorData?.ps?.framesByIndex;
  if (!fr || typeof fr !== "object") return "";
  const keys = Object.keys(fr);
  if (!keys.length) return "";
  const frames = fr[keys[0]] || [];
  const dates = frames.map((f) => normIso(f.date)).filter(Boolean);
  if (!dates.length) return "";
  const u = [...new Set(dates)].sort();
  const head = u.slice(0, 12).join(", ");
  const tail = u.length > 16 ? ` … ${u.slice(-5).join(", ")}` : u.length > 12 ? ` (+${u.length - 12} fechas más)` : "";
  return `**${u.length}** fechas PlanetScope con recorte e índices en el proyecto: ${head}${tail}. La lectura RGB debe recorrer **cada** una de estas fechas para lucanas, sombras fijas y bordes de lote.`;
}

function synthesisBlock(ctx, psIx) {
  const { isPalm, ageYears } = inferPalmContext(ctx.projectName);
  const traj = indexMeansTrajectory(ctx.seriesBySensor?.ps, psIx);
  const drop = largestMeanDrop(traj);
  const rows = pickClimateRows(ctx.climateBySensor || {});
  const tmax = summarizeClimateVar(rows, "temp")?.max;

  const parts = [];
  if (isPalm) {
    parts.push(
      `En conjunto, el paquete de datos describe la **evolución del dosel** y de la **heterogeneidad espacial** a escala de parcela. ` +
        (ageYears != null
          ? `A **~${ageYears} años**, el foco agronómico típico en Colombia está en **mortalidad dispersa**, **lucanas** y **respuesta al clima** más que en fallas de implantación. `
          : "") +
        "**Planet RGB** aporta la evidencia más fina de huecos entre plantas; los índices y Smart clusters cuantifican **cómo cambia** esa firma en el tiempo.",
    );
  } else {
    parts.push(
      "La combinación de **Planet de alta resolución** con series Sentinel y clima permite seguir **cambios de biomasa y heterogeneidad** del cultivo a lo largo del periodo disponible.",
    );
  }
  if (drop && drop.drop >= 0.05) {
    parts.push(
      `La caída más marcada de **${psIx}** entre **${drop.from.date}** y **${drop.to.date}** debe confrontarse con **RGB** en esas fechas y con **temperatura/precipitación** del mismo mes.`,
    );
  }
  if (tmax != null && tmax > 34) {
    parts.push(`Picos térmicos por encima de **${fmt(tmax, 1)}** °C en la serie mensual pueden asociarse a **estrés térmico** en palma si coinciden con bajas de verdor.`);
  }
  return parts.join(" ");
}

/**
 * @param {string} report
 * @param {object|null} apiData respuesta de `/preprocess/dashboard-ia-planet-integral/:id`
 */
export function appendPlanetIntegralAppendix(report, apiData) {
  if (!apiData || typeof apiData !== "object") return report;
  const lines = [];
  lines.push("## PlanetScope: visión por computador en toda la serie");
  lines.push(
    "Sobre **cada** escena GeoTIFF Planet del proyecto (ocho bandas espectrales) se calculó en malla reducida: **NDVI**, fracción de **dosel bajo** (NDVI inferior a 0,22), variabilidad del verde y, sobre la composición **RGB equivalente a la vista true-color del dashboard** (bandas 6-4-2), el **brillo percibido** y la **varianza del laplaciano** del brillo como proxy de **textura y bordes** (surcos, huecos, copas). Los valores son agregados por escena; lucanas estrechas pueden seguir siendo más visibles en RGB a resolución plena.",
  );
  const narr = apiData.narrative;
  if (Array.isArray(narr) && narr.length) {
    lines.push("### Hallazgos automáticos en el tiempo");
    for (const n of narr) lines.push(String(n));
  }
  const sum = apiData.summary || {};
  if (sum.n_scenes_analyzed != null) {
    lines.push(
      `### Cobertura del análisis automático: **${sum.n_scenes_analyzed}** escenas válidas de **${sum.n_paths_seen ?? "—"}** archivos candidatos.`,
    );
  }
  if (sum.delta_frac_low_ndvi != null && Number.isFinite(Number(sum.delta_frac_low_ndvi))) {
    lines.push(
      `Cambio medio de fracción de dosel bajo (tramo reciente − inicial): **${Number(sum.delta_frac_low_ndvi).toFixed(3)}** (valores absolutos dependen de atmósfera y umbral).`,
    );
  }
  if (sum.delta_rgb_laplace != null && Number.isFinite(Number(sum.delta_rgb_laplace))) {
    lines.push(
      `Cambio de energía de borde RGB (laplaciano, tramo reciente − inicial): **${Number(sum.delta_rgb_laplace).toExponential(2)}** (misma escala relativa entre escenas del proyecto).`,
    );
  }
  const scenes = Array.isArray(apiData.scenes) ? apiData.scenes : [];
  const ok = scenes.filter((r) => r.ndvi_mean != null);
  if (ok.length) {
    lines.push("### Muestra escena a escena (primeras y últimas analizadas)");
    const fmtRow = (r) => {
      const lap = r.rgb_laplace_var != null && Number.isFinite(Number(r.rgb_laplace_var)) ? Number(r.rgb_laplace_var).toExponential(1) : "—";
      return `${normIso(r.sort_key)}: NDVI_medio=${Number(r.ndvi_mean).toFixed(2)}, frac_bajo=${Number(r.frac_low_ndvi).toFixed(2)}, Lap_RGB=${lap}`;
    };
    lines.push(ok.slice(0, 5).map(fmtRow).join(" | "));
    if (ok.length > 7) lines.push(ok.slice(-3).map(fmtRow).join(" | "));
  }
  const err = scenes.find((r) => r.error);
  if (err && ok.length === 0) {
    lines.push(`Incidencia en lectura de archivos: ${String(err.error)}`);
  }
  return `${report}\n\n${lines.join("\n\n")}`;
}

/**
 * @returns {{ report: string, disclaimer: string }}
 */
export function buildDashboardIaTechnicalReport(ctx) {
  const {
    projectName = "",
    sensorData = {},
    indexBySensor = {},
    seriesBySensor = {},
    climateBySensor = {},
    clusterBySensor = {},
    psStClusters = {},
    clientSoilSummary = null,
    hasGeofisica = false,
    soilDemInfo = null,
    activeSceneDate = null,
    activeSensorKey = "ps",
    activeIndexKey = "NDVI",
  } = ctx;

  const intro = palmIntroBlock({ projectName });
  const inv = sensorInventoryLines(sensorData);
  const psIx = indexBySensor.ps || pickPsIndexKey(seriesBySensor.ps, "NDVI") || "NDVI";
  const hetero = planetHeterogeneityTrendBlock(seriesBySensor.ps, psIx);
  const serPs = seriesDetailParagraph("ps", seriesBySensor.ps, psIx);
  const serS2 = seriesDetailParagraph("s2", seriesBySensor.s2, indexBySensor.s2 || "NDVI");
  const serS1 = seriesDetailParagraph("s1", seriesBySensor.s1, indexBySensor.s1 || "RVI");
  const cli = climateParagraph(pickClimateRows(climateBySensor));
  const clu = clusterInventorySummary(clusterBySensor);
  const sm = smartClusterDetailLines(psStClusters);
  const soil = soilLines(clientSoilSummary, hasGeofisica, soilDemInfo);
  const anchor = sceneAnchorParagraph(activeSceneDate, activeSensorKey, activeIndexKey);
  const psCal = planetSceneCalendar(sensorData);
  const syn = synthesisBlock(ctx, psIx);

  const report = [
    intro,
    "",
    "## Capacidad de datos del proyecto",
    ...inv.map((l) => `• ${l}`),
    ...(psCal ? ["", "## Calendario PlanetScope", psCal] : []),
    "",
    "## Referencia de escena en el visor",
    anchor,
    "",
    "## PlanetScope: RGB, índices y heterogeneidad espacial",
    "La **ortofoto Planet** es la principal fuente para detectar **lucanas**, **palmas sin copa**, **líneas de acceso** y **bordes de recorte** frente al patrón regular de palmas adultas.",
    "Los índices en Planet refinan **verdor**, **agua en hoja** y **estructura**; deben leerse **junto** con RGB en la misma fecha para no confundir brillo del suelo húmedo o sombras con estrés real.",
    hetero ? `\n### Heterogeneidad espacial agregada (índice ${psIx})\n${hetero}` : "",
    "",
    "## Series espectrales (evolución temporal)",
    `• **Planet (${psIx}):** ${serPs}`,
    `• **Sentinel-2:** ${serS2}`,
    `• **Sentinel-1 (SAR):** ${serS1}`,
    "",
    "## Smart Clusters Planet (k-medias espacio-temporal)",
    "Cada mapa resume **trayectorias conjuntas** de píxeles en el tiempo, no una sola fecha. En palma, las clases que se **pegan al borde** del recorte suelen mezclar dosel con **caminos, sombras de borde o fuera de ROI**; el **núcleo** del polígono describe mejor el comportamiento del stand.",
    ...sm.map((l) => `• ${l}`),
    "",
    "## Clusters espectrales GMM (inventario por sensor)",
    ...clu.map((l) => `• ${l}`),
    "",
    "## Modelado de suelo y relieve (Smart Soil / geofísica)",
    ...soil.map((l) => `• ${l}`),
    "",
    "## Agroclima y coherencia con la biomasa observada",
    cli,
    "",
    "## Síntesis integral",
    syn,
  ]
    .filter(Boolean)
    .join("\n");

  const disclaimer =
    "Texto generado automáticamente a partir de los datos del proyecto; no sustituye inspección fitosanitaria certificada en campo.";

  return { report, disclaimer };
}
