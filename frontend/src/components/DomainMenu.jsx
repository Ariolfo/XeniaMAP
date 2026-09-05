export const DOMAIN_OPTIONS = [
  {
    id: "ingreso",
    label: "Ingreso",
    title: "Inicio de sesión y cuenta",
    ready: true,
  },
  {
    id: "agro",
    label: "Agro",
    title: "Agricultura y monitoreo de cultivos",
    ready: true,
  },
  {
    id: "og",
    label: "O&G",
    title: "Oil & Gas",
    ready: false,
  },
  {
    id: "fire",
    label: "Fire",
    title: "Detección y severidad de incendios",
    ready: true,
  },
  {
    id: "ch4",
    label: "CH4",
    title: "Monitoreo de metano",
    ready: false,
  },
];

/** Submenú Agro (admin): mismos ítems que la antigua fila de pestañas del panel. */
export const AGRO_ADMIN_SUBMENUS = [
  { id: "admin", label: "Gestión", title: "Gestión de usuarios, órdenes y proyecto" },
  { id: "cargar", label: "Cargar", title: "Cargar lotes y rasters" },
  { id: "s1", label: "SI", title: "Sentinel-1" },
  { id: "prepro", label: "S2", title: "Sentinel-2" },
  { id: "ps", label: "PS", title: "PlanetScope / alta resolución" },
  { id: "smart", label: "Smart", title: "Análisis Smart" },
  { id: "dashboard", label: "Dash", title: "Abrir dashboard de resultados", action: "dashboard" },
  {
    id: "informe",
    label: "Informe",
    title: "Informe narrativo (edición admin)",
    action: "informe",
  },
  { id: "capas", label: "Capas", title: "Mostrar u ocultar capas del mapa" },
];

function DomainIcon({ id }) {
  const common = {
    width: 22,
    height: 22,
    viewBox: "0 0 24 24",
    fill: "none",
    xmlns: "http://www.w3.org/2000/svg",
    "aria-hidden": true,
    className: "domain-menu-icon-svg",
  };

  if (id === "ingreso") {
    return (
      <svg {...common}>
        <path
          d="M10 17v-1.5H5.5A1.5 1.5 0 0 1 4 14V6.5A1.5 1.5 0 0 1 5.5 5H10V3.5L15 7.25 10 11V9.5H5.5v4.5H10z"
          fill="currentColor"
        />
        <path
          d="M14 5h3.5A1.5 1.5 0 0 1 19 6.5v11a1.5 1.5 0 0 1-1.5 1.5H14"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  if (id === "agro") {
    return (
      <svg {...common}>
        <path
          d="M12 20c0-6 4-10 9-11-1 7-5 11-9 11z"
          fill="currentColor"
          opacity="0.9"
        />
        <path
          d="M12 20C12 14 8 10 3 9c1 7 5 11 9 11z"
          fill="currentColor"
          opacity="0.7"
        />
        <path d="M12 20V9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }
  if (id === "og") {
    return (
      <svg {...common}>
        <path
          d="M8 21h8M10 21V10.5L12 4l2 6.5V21"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M7 12h10M6.5 15.5h11"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
        <circle cx="12" cy="4" r="1.5" fill="currentColor" />
      </svg>
    );
  }
  if (id === "fire") {
    return (
      <svg {...common}>
        <circle cx="8" cy="11" r="4.2" stroke="currentColor" strokeWidth="1.7" />
        <circle cx="16" cy="11" r="4.2" stroke="currentColor" strokeWidth="1.7" />
        <path
          d="M11.6 11h.8M5.2 9.2 3.8 7.6M18.8 9.2l1.4-1.6"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
        <path
          d="M6.2 14.8 4.5 17.2M17.8 14.8l1.7 2.4"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
        <circle cx="8" cy="11" r="1.6" fill="currentColor" opacity="0.35" />
        <circle cx="16" cy="11" r="1.6" fill="currentColor" opacity="0.35" />
      </svg>
    );
  }
  if (id === "ch4") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="3.2" fill="currentColor" />
        <circle cx="6.5" cy="8.5" r="2.2" fill="currentColor" opacity="0.85" />
        <circle cx="17.5" cy="8.5" r="2.2" fill="currentColor" opacity="0.85" />
        <circle cx="7.5" cy="16.5" r="2" fill="currentColor" opacity="0.75" />
        <circle cx="16.5" cy="16.5" r="2" fill="currentColor" opacity="0.75" />
        <path
          d="M9.8 10.2 12 12m0 0 2.2-1.8M12 12l-2.2 2.6M12 12l2.2 2.6"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinecap="round"
          opacity="0.55"
        />
      </svg>
    );
  }
  return null;
}

export default function DomainMenu({
  activeDomain = "ingreso",
  onSelectDomain,
  isAdmin = false,
  agroSubTab = "admin",
  onSelectAgroSub,
  agroActionsDisabled = false,
}) {
  const showAgroSub = isAdmin && activeDomain === "agro";

  return (
    <aside className={`domain-menu${showAgroSub ? " domain-menu--agro-open" : ""}`} aria-label="Dominios XeniaMAP">
      <div className="domain-menu-inner" role="tablist" aria-orientation="vertical">
        {DOMAIN_OPTIONS.map((domain) => {
          const isActive = activeDomain === domain.id;
          const isAgro = domain.id === "agro";

          return (
            <div
              key={domain.id}
              className={`domain-menu-group${isAgro && showAgroSub ? " domain-menu-group--expanded" : ""}`}
            >
              <button
                type="button"
                role="tab"
                aria-selected={isActive}
                aria-expanded={isAgro ? showAgroSub : undefined}
                className={`domain-menu-btn domain-menu-btn--${domain.id}${isActive ? " active" : ""}`}
                title={domain.title}
                onClick={() => onSelectDomain?.(domain.id)}
              >
                <span className="domain-menu-icon">
                  <DomainIcon id={domain.id} />
                </span>
                <span className="domain-menu-label">{domain.label}</span>
                {!domain.ready ? <span className="domain-menu-soon">Pronto</span> : null}
              </button>

              {isAgro && showAgroSub ? (
                <div className="domain-menu-sub" role="group" aria-label="Herramientas Agro">
                  {AGRO_ADMIN_SUBMENUS.map((item) => {
                    const isAction = Boolean(item.action);
                    const isSubActive = !isAction && agroSubTab === item.id;
                    const disabled = isAction && agroActionsDisabled;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        className={`domain-menu-sub-btn${isSubActive ? " active" : ""}${
                          item.id === "s1" || item.id === "ps" ? ` domain-menu-sub-btn--${item.id}` : ""
                        }`}
                        title={item.title}
                        disabled={disabled}
                        onClick={() => onSelectAgroSub?.(item)}
                      >
                        <span className="domain-menu-sub-label">{item.label}</span>
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
