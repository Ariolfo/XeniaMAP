import {
  BarChart,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  Pill,
  Row,
  Spacer,
  Stack,
  Stat,
  Table,
  Text,
  TodoList,
  UsageBar,
} from "cursor/canvas";

/**
 * Plan de trabajo: Hexagonal-first + Clean-lite sobre monolito modular (A),
 * luego contratos extractables (B). Sin implementar código — roadmap.
 * LOC medidos 2026-09-06 (conteo de líneas por archivo).
 */

const DECISION = {
  primary: "Hexagonal (ports & adapters) sobre monolito modular",
  cleanLite: [
    "Casos de uso como única orquestación",
    "Regla de dependencia hacia adentro",
    "Dominio mínimo: authz + estados de órdenes/proyectos",
  ],
  exclude: "No exigir entities / presenters / mappers en cada endpoint GIS",
};

type FatKind = "router" | "pipeline" | "tasks" | "uc-gordo" | "gis" | "frontend";

const FAT: { label: string; value: number; kind: FatKind }[] = [
  { label: "modules/fire/process_dnbr.py", value: 1911, kind: "pipeline" },
  { label: "frontend AdvancedDashboard.jsx", value: 1978, kind: "frontend" },
  { label: "frontend RgbTimeSeriesGallery.jsx", value: 1932, kind: "frontend" },
  { label: "frontend PreprocessPanel.jsx", value: 1640, kind: "frontend" },
  { label: "api/v1/preprocess.py", value: 1253, kind: "router" },
  { label: "tasks/jobs.py", value: 1238, kind: "tasks" },
  { label: "application/agro/soilplus.py", value: 1015, kind: "uc-gordo" },
  { label: "services/satellite_clustering.py", value: 855, kind: "gis" },
  { label: "services/soilplus.py", value: 822, kind: "gis" },
  { label: "services/s2_vegetation_indices.py", value: 803, kind: "gis" },
  { label: "api/v1/rasters.py", value: 795, kind: "router" },
  { label: "services/raster_geo.py", value: 740, kind: "gis" },
  { label: "modules/fire/validate_firms.py", value: 635, kind: "pipeline" },
  { label: "api/v1/fire_orders.py", value: 547, kind: "router" },
  { label: "services/sentinel1.py", value: 547, kind: "gis" },
  { label: "application/agro/rasters.py", value: 539, kind: "uc-gordo" },
  { label: "modules/fire/download_s2.py", value: 479, kind: "pipeline" },
  { label: "frontend App.jsx", value: 854, kind: "frontend" },
];

type Phase = {
  id: string;
  track: string;
  title: string;
  goal: string;
  weeks: string;
  outcomes: string[];
  fat: string[];
  exit: string;
};

const PHASES: Phase[] = [
  {
    id: "H0",
    track: "Gobierno",
    title: "Congelar reglas Hexagonal-first + Clean-lite",
    goal: "A",
    weeks: "3–5 días",
    outcomes: [
      "ADR-002: Hexagonal-first, Clean-lite, Modular A ahora / B después",
      "Regla PR: código nuevo api → application → port → infrastructure|algoritmo",
      "Mapa bounded contexts: Identity | Agro | Fire | Shared GIS",
      "DoD por feature: UC + test; puerto si hay I/O externo (sin presenters GIS)",
    ],
    fat: ["Ninguno — solo gobierno"],
    exit: "ADR + checklist en docs/architecture.md; equipo alineado",
  },
  {
    id: "H1",
    track: "Modular A",
    title: "Monolito modular legible (APIs internas claras)",
    goal: "A",
    weeks: "1–2 sprints",
    outcomes: [
      "Vaciar residuales de delivery: preprocess (landing markdown) → application",
      "Partir rasters: rutas mapa cliente vs browse/admin (módulos o routers hermanos)",
      "Owners: application/{agro,fire}; modules/fire = solo pipeline legacy",
      "FE espejo: features/{agro,fire,auth} + shared/map (mover sin reescribir UX)",
      "Prohibir imports nuevos api → services saltando application",
    ],
    fat: [
      "preprocess.py ~1253",
      "rasters.py ~795",
      "fire_orders.py ~547",
      "PreprocessPanel ~1640",
      "App.jsx ~854",
    ],
    exit: "Routers nuevos/refactors < ~400 LOC o partidos; inventarios solo vía UC",
  },
  {
    id: "H2",
    track: "Clean-lite",
    title: "Dominio mínimo + UC como única orquestación",
    goal: "A → Hex",
    weeks: "1–2 sprints",
    outcomes: [
      "domain/identity: políticas publicado + ownership/share (hoy en deps.py)",
      "domain/agro + domain/fire: estados Project / FireOrder / StudyOrder + transiciones",
      "deps.py solo glue HTTP/DB; asserts de negocio en dominio testeable",
      "Todo flujo nuevo: UC.execute; cero reglas de negocio en routers",
    ],
    fat: ["deps.py (authz)", "soilplus UC: separar orquestación vs algoritmo"],
    exit: "Authz testeable sin FastAPI; routers sin if role/status de producto",
  },
  {
    id: "H3",
    track: "Hexagonal",
    title: "Puertos núcleo (persistencia, disco, cola, tiles)",
    goal: "Hex fuerte",
    weeks: "2–3 sprints",
    outcomes: [
      "Ports: ProjectRepository, RasterStoragePort, JobQueuePort, TileRenderPort, MailPort",
      "Adapters: SQLAlchemy, disco EXTERNAL_DATA, Celery, XYZ+MVT (ya existen piezas)",
      "Composition root: cablea adapters → UC → routers/tasks",
      "Pilotos: list+preview raster, enqueue S2, FIRMS, MVT sync, Fire tiles",
    ],
    fat: ["tasks/jobs.py ~1238 vía JobQueuePort", "raster_geo / xyz_tiles → TileRenderPort"],
    exit: "≥5 flujos críticos solo por ports; tests UC con mocks",
  },
  {
    id: "H4",
    track: "Adelgazar gordos",
    title: "Pipelines y GIS detrás de adapters (sin Clean theater)",
    goal: "Hex + A",
    weeks: "2–4 sprints",
    outcomes: [
      "process_dnbr + download_s2 + validate_firms: solo desde application/fire",
      "services GIS = libraries puras; I/O/HTTP/DB → infrastructure",
      "SoilPlus/cluster: algoritmo en services; UC orquesta; enqueue JobQueue si p95 alto",
      "Eliminar facades duplicadas (cdse services vs infrastructure)",
      "jobs.py = dispatch a UC (sin lógica de pipeline inline)",
    ],
    fat: [
      "process_dnbr ~1911",
      "validate_firms ~635",
      "download_s2 ~479",
      "soilplus UC+svc ~1015+822",
      "clustering ~855",
      "s2_vegetation_indices ~803",
    ],
    exit: "modules/fire sin imports desde api; jobs solo dispatch",
  },
  {
    id: "H5",
    track: "Hex total (monolito)",
    title: "Hexagonal completo dentro del deploy único",
    goal: "Hex total",
    weeks: "1–2 sprints",
    outcomes: [
      "domain/ sin pandas/FastAPI/SQLAlchemy en firmas de puertos (DTOs propios)",
      "application/ sin Session directa (UnitOfWork o repos)",
      "import-linter (o equivalente) + cobertura application con umbral subido",
      "Dockerfile API slim vs worker GIS (mismo repo) — escala sin microservicios",
    ],
    fat: ["Imagen única xeniamap-backend (deps GIS también en API)"],
    exit: "Checklist hexagonal total en monolito; p95 mapa no degradado",
  },
  {
    id: "B1",
    track: "Modular B",
    title: "Extractable: contratos listos para sacar un contexto",
    goal: "B",
    weeks: "1 sprint + triggers",
    outcomes: [
      "Contrato estable por BC: API interna + cola/eventos (Fire pipeline, SoilPlus job)",
      "Colas Celery separadas agro / fire (hoy concurrency=1 global)",
      "Límites de datos documentados (tablas + paths EXTERNAL_DATA del contexto)",
      "Extracción solo con trigger real: dNBR/SNAP, SoilPlus/GPU, ingest CDSE",
    ],
    fat: ["Worker concurrency=1", "Redis/DB/disco compartidos"],
    exit: "Se puede extraer Fire GIS o SoilPlus sin reescribir el mapa cliente",
  },
];

const METRICS = [
  {
    metric: "Routers delgados",
    target: "Nuevos/refactors < ~400 LOC o partidos por rol (mapa vs admin)",
  },
  {
    metric: "Orquestación",
    target: "0 lógica de negocio nueva fuera de application/",
  },
  {
    metric: "Puertos",
    target: "I/O externo nuevo → Protocol en domain/",
  },
  {
    metric: "Latencia cliente",
    target: "p95 preview/tiles; SoilPlus sync → job si p95 alto",
  },
  {
    metric: "Latencia admin",
    target: "Profundidad cola Celery; colas agro/fire en B1",
  },
  {
    metric: "Hex total",
    target: "import-linter verde; UC testeables con mocks de ports",
  },
];

const TODO_H0 = [
  {
    id: "1",
    content: "Redactar ADR-002 Hexagonal-first + Clean-lite + Modular A/B",
    status: "pending" as const,
  },
  {
    id: "2",
    content: "Actualizar docs/architecture.md con DoD y regla de imports",
    status: "pending" as const,
  },
  {
    id: "3",
    content: "Inventario owners Identity / Agro / Fire / Shared GIS",
    status: "pending" as const,
  },
];

const TODO_NEAR = [
  {
    id: "a",
    content: "H1: vaciar preprocess residual + partir rasters admin vs map",
    status: "pending" as const,
  },
  {
    id: "b",
    content: "H1: features FE agro/fire/auth (mover carpetas)",
    status: "pending" as const,
  },
  {
    id: "c",
    content: "H2: domain policies authz (publicado / share / fire own)",
    status: "pending" as const,
  },
  {
    id: "d",
    content: "H3: JobQueuePort + ProjectRepository piloto",
    status: "pending" as const,
  },
  {
    id: "e",
    content: "H4: encapsular process_dnbr solo vía application/fire",
    status: "pending" as const,
  },
];

function phaseFatLabel(kind: FatKind): string {
  if (kind === "router" || kind === "frontend") return "H1";
  if (kind === "pipeline" || kind === "tasks") return "H3–H4";
  if (kind === "uc-gordo" || kind === "gis") return "H4";
  return "H1–H4";
}

function shortName(label: string): string {
  const base = label.replace(/^.*\//, "").replace(/^frontend /, "");
  return base.length > 28 ? `${base.slice(0, 26)}…` : base;
}

export default function XeniaMapHexagonalModularRoadmap() {
  return (
    <Stack gap={24} style={{ padding: 24, maxWidth: 1120 }}>
      <Stack gap={8}>
        <H1>XeniaMAP — Roadmap Hexagonal + Modular</H1>
        <Text tone="secondary">
          Plan por fases hacia hexagonal total sobre monolito modular (A), luego contratos
          extractables (B). Clean Architecture solo en tres puntos. Sin cambios de código en este
          canvas — es el plan de trabajo.
        </Text>
        <Row gap={8} style={{ flexWrap: "wrap" }}>
          <Pill tone="info" active>
            Hexagonal-first
          </Pill>
          <Pill tone="neutral" active>
            Clean-lite
          </Pill>
          <Pill tone="success" active>
            Modular A ahora
          </Pill>
          <Pill tone="warning" active>
            Modular B después
          </Pill>
        </Row>
      </Stack>

      <Callout tone="info" title="Arquitectura objetivo">
        {DECISION.primary}. Clean-lite: {DECISION.cleanLite.join("; ")}. Excluido:{" "}
        {DECISION.exclude}.
      </Callout>

      <Grid columns={4} gap={12}>
        <Stat value="7" label="Fases H0–H5 + B1" />
        <Stat value={String(FAT.length)} label="Archivos gordos rastreados" />
        <Stat value="A → B" label="Camino modular" tone="info" />
        <Stat value="1 deploy" label="Hasta Hex total (H5)" tone="success" />
      </Grid>

      <Stack gap={6}>
        <UsageBar
          total={10}
          topLeftLabel="Esfuerzo relativo estimado"
          topRightLabel="H0–H5 + B1"
          segments={[
            { id: "modA", value: 2, color: "blue" },
            { id: "ports", value: 3, color: "green" },
            { id: "hex", value: 3, color: "orange" },
            { id: "extB", value: 2, color: "gray" },
          ]}
        />
        <Text size="small" tone="secondary">
          Segmentos: Modular A (H0–H1) · Clean-lite + ports (H2–H3) · Hex total (H4–H5) ·
          Extractable B1. Source: plan · 2026-09-06.
        </Text>
      </Stack>

      <Divider />

      <H2>A vs B — modular</H2>
      <Grid columns={2} gap={16}>
        <Card>
          <CardHeader trailing={<Pill tone="success" size="sm" active>Ahora</Pill>}>
            A — Modular monolito
          </CardHeader>
          <CardBody>
            <Stack gap={8}>
              <Text size="small">Un deploy. Módulos con APIs internas claras.</Text>
              <Text size="small" tone="secondary">
                Fases H0–H5. Misma base de datos. Opcional: imagen API slim vs worker GIS sin partir
                dominio.
              </Text>
              <Text size="small">
                Éxito: lectura por contexto; UC únicos; puertos para I/O; gordos encapsulados.
              </Text>
            </Stack>
          </CardBody>
        </Card>
        <Card>
          <CardHeader trailing={<Pill tone="warning" size="sm" active>Después</Pill>}>
            B — Modular + extractable
          </CardHeader>
          <CardBody>
            <Stack gap={8}>
              <Text size="small">Contratos listos para sacar un bounded context.</Text>
              <Text size="small" tone="secondary">
                Fase B1 tras Hex en monolito. No microservicios por moda.
              </Text>
              <Text size="small">
                Triggers: dNBR/SNAP, SoilPlus pesado, ingest CDSE con ciclo distinto al mapa.
              </Text>
            </Stack>
          </CardBody>
        </Card>
      </Grid>

      <Divider />

      <H2>Procesos / archivos aún gordos</H2>
      <Text tone="secondary">
        Siguen existiendo nodos muy grandes: pipelines Fire, routers Agro, tasks Celery, UC/GIS
        SoilPlus y paneles FE. Prioridad: routers+FE (H1), jobs+ports (H3), pipelines/GIS (H4).
      </Text>
      <H3>Top archivos por líneas de código</H3>
      <BarChart
        categories={FAT.slice(0, 12).map((f) => shortName(f.label))}
        series={[{ name: "Líneas (LOC)", data: FAT.slice(0, 12).map((f) => f.value) }]}
        height={300}
      />
      <Text size="small" tone="secondary">
        Eje X: archivo · Eje Y: líneas. Source: inventario backend/app + frontend/src · 2026-09-06.
      </Text>
      <Table
        headers={["Archivo", "LOC", "Tipo", "Fase"]}
        rows={FAT.map((f) => [f.label, String(f.value), f.kind, phaseFatLabel(f.kind)])}
      />

      <Divider />

      <H2>Fases — resumen</H2>
      <Table
        headers={["ID", "Título", "Track", "Meta", "Esfuerzo", "Criterio de salida"]}
        rows={PHASES.map((p) => [p.id, p.title, p.track, p.goal, p.weeks, p.exit])}
      />

      <H3>Entregables por fase</H3>
      <Table
        headers={["Fase", "Entregables", "Gordos que toca"]}
        rows={PHASES.map((p) => [
          `${p.id} · ${p.title}`,
          p.outcomes.map((o) => `· ${o}`).join("\n"),
          p.fat.join(" · "),
        ])}
      />

      <Divider />

      <H2>Dependencias entre fases</H2>
      <Text>
        H0 → H1 (Modular A) → H2 (Clean-lite dominio) → H3 (Ports) → H4 (Adelgazar pipelines/GIS) →
        H5 (Hex total en monolito) → B1 (Extractable, solo con trigger)
      </Text>
      <Text size="small" tone="secondary">
        No saltar H3 antes de H2: los puertos deben servir políticas de dominio ya extraídas. No
        abrir B1 antes de H5 salvo urgencia operativa (p. ej. SNAP tumba la API).
      </Text>

      <Divider />

      <H2>Métricas de avance</H2>
      <Table
        headers={["Métrica", "Target"]}
        rows={METRICS.map((m) => [m.metric, m.target])}
      />

      <Divider />

      <Grid columns={2} gap={16}>
        <Card>
          <CardHeader>Arranque H0</CardHeader>
          <CardBody>
            <TodoList todos={TODO_H0} />
          </CardBody>
        </Card>
        <Card>
          <CardHeader>Próximos sprints (H1–H4)</CardHeader>
          <CardBody>
            <TodoList todos={TODO_NEAR} />
          </CardBody>
        </Card>
      </Grid>

      <Callout tone="warning" title="Fuera de alcance de este plan">
        Microservicios generales; Clean completo con presenters/mappers GIS; renombrar volumen
        Postgres legacy; cambiar nombres Celery tasks.fire_*.
      </Callout>

      <Spacer height={4} />
      <Text size="small" tone="secondary">
        Canvas roadmap · XeniaMAP · 2026-09-06 · Complementa xeniamap-architecture-audit.canvas.tsx
      </Text>
    </Stack>
  );
}
