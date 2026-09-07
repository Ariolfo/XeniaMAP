import axios from "axios";

/**
 * Sin VITE_API_URL: mismo origen que la página + `/api/v1` (p. ej. :5173). En dev, Vite reenvía `/api` al
 * backend (`BACKEND_PROXY_URL` en Docker, por defecto `http://127.0.0.1:8000` en el host). Así el navegador
 * no depende de que el puerto 8000 esté expuesto ni de CORS hacia :8000.
 */
const DEV_API_PORT = import.meta.env.VITE_DEV_API_PORT || "8000";

function resolveApiBase() {
  const v = import.meta.env.VITE_API_URL;
  if (v != null && String(v).trim() !== "") {
    let u = String(v).trim().replace(/\/$/, "");
    // Ya incluye /api/v1
    if (/\/api\/v1$/i.test(u)) {
      return u;
    }
    // Caso típico erróneo: http://host:8000/api → debe ser .../api/v1 (no .../api/api/v1)
    if (/\/api$/i.test(u)) {
      return `${u}/v1`;
    }
    // Raíz del backend (p. ej. http://localhost:8000) → añadir prefijo API
    return `${u}/api/v1`;
  }
  if (typeof window !== "undefined" && window.location?.origin) {
    return `${window.location.origin}/api/v1`;
  }
  return `http://127.0.0.1:${DEV_API_PORT}/api/v1`;
}

export const API_URL = resolveApiBase();

/** Marcador de sesión en React; los JWT viven solo en cookies HttpOnly (F5). */
export const AUTH_SESSION_MARKER = "cookie";

const SK_ACCESS = "xeniamap_access";
const SK_REFRESH = "xeniamap_refresh";
const SK_SESSION = "xeniamap_session";

const EVT_AUTH_REFRESHED = "xeniamap:auth-refreshed";
const EVT_AUTH_EXPIRED = "xeniamap:auth-expired";

const api = axios.create({ baseURL: API_URL, withCredentials: true });

/** Petición sin interceptores (evita bucles al renovar token). */
const rawClient = axios.create({ baseURL: API_URL, withCredentials: true });

let refreshInFlight = null;

function readSessionKey(key) {
  return sessionStorage.getItem(key);
}

export function isCookieAuthToken(token) {
  return !token || token === AUTH_SESSION_MARKER;
}

/**
 * Opciones para `fetch` autenticado: cookies HttpOnly + credentials.
 * Solo añade Bearer si `token` es un JWT real (compat / tests).
 */
export function authFetchInit(token, extra = {}) {
  const headers = { ...(extra.headers || {}) };
  if (token && !isCookieAuthToken(token)) {
    headers.Authorization = `Bearer ${token}`;
  }
  return {
    ...extra,
    credentials: "include",
    headers,
  };
}

/**
 * F5: la app usa cookies HttpOnly. Si se pasa un JWT real, se mantiene Bearer
 * (compatibilidad puntual); el marcador de sesión no escribe Authorization.
 */
export function setAuthToken(token) {
  if (token && !isCookieAuthToken(token)) {
    api.defaults.headers.common["Authorization"] = `Bearer ${token}`;
  } else {
    delete api.defaults.headers.common["Authorization"];
  }
}

function purgeLegacyJwtStorage() {
  sessionStorage.removeItem(SK_ACCESS);
  sessionStorage.removeItem(SK_REFRESH);
  sessionStorage.removeItem("bioagromap_access");
  sessionStorage.removeItem("bioagromap_refresh");
}

/** Marca sesión activa en sessionStorage sin guardar JWT. */
export function persistAuthTokens(access, _refresh) {
  if (access) {
    purgeLegacyJwtStorage();
    sessionStorage.setItem(SK_SESSION, "1");
    setAuthToken(null);
  } else {
    clearAuthTokens();
  }
}

export function clearAuthTokens() {
  purgeLegacyJwtStorage();
  sessionStorage.removeItem(SK_SESSION);
  setAuthToken(null);
}

export function loadStoredAuth() {
  // Migración F5: si quedaron JWT en sessionStorage, solo conservar flag de sesión.
  if (readSessionKey(SK_ACCESS) || readSessionKey(SK_REFRESH)) {
    purgeLegacyJwtStorage();
    sessionStorage.setItem(SK_SESSION, "1");
  }
  const ok = readSessionKey(SK_SESSION) === "1";
  return {
    access: ok ? AUTH_SESSION_MARKER : null,
    refresh: null,
  };
}

export async function logoutOnServer() {
  try {
    await rawClient.post("/auth/logout");
  } catch {
    /* cookie puede ya haber caducado */
  }
}

function dispatchAuthEvent(name, detail) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(name, detail != null ? { detail } : undefined));
}

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const status = error.response?.status;
    const config = error.config;
    if (status !== 401 || !config || config._retry) {
      return Promise.reject(error);
    }
    const reqUrl = String(config.url || "");
    if (
      reqUrl.includes("/auth/refresh") ||
      reqUrl.includes("/auth/login") ||
      reqUrl.includes("/auth/register") ||
      reqUrl.includes("/auth/verify-otp") ||
      reqUrl.includes("/auth/request-otp") ||
      reqUrl.includes("/auth/logout")
    ) {
      return Promise.reject(error);
    }
    const hasSession = readSessionKey(SK_SESSION) === "1";
    if (!hasSession) {
      return Promise.reject(error);
    }
    config._retry = true;
    try {
      if (!refreshInFlight) {
        refreshInFlight = rawClient
          .post("/auth/refresh", {})
          .then((res) => res.data)
          .finally(() => {
            refreshInFlight = null;
          });
      }
      await refreshInFlight;
      persistAuthTokens(AUTH_SESSION_MARKER);
      if (config.headers) {
        delete config.headers.Authorization;
        delete config.headers.authorization;
      }
      dispatchAuthEvent(EVT_AUTH_REFRESHED, {
        access_token: AUTH_SESSION_MARKER,
      });
      return api(config);
    } catch (e) {
      clearAuthTokens();
      dispatchAuthEvent(EVT_AUTH_EXPIRED);
      return Promise.reject(e);
    }
  }
);

/** Texto legible para errores de Axios/FastAPI (detail string, lista 422, u objeto). */
/** URL efectiva de la petición (útil para depurar 404). */
function resolvedRequestUrl(error) {
  const c = error?.config;
  if (!c) return "";
  try {
    const raw = c.url != null ? String(c.url) : "";
    if (/^https?:\/\//i.test(raw)) return raw;
    const base = c.baseURL ? String(c.baseURL).replace(/\/$/, "") : "";
    const path = raw.replace(/^\//, "");
    if (base && path) {
      return new URL(path, `${base}/`).href;
    }
    return path || base;
  } catch {
    return [c.baseURL, c.url].filter(Boolean).join("");
  }
}

export function formatApiErrorDetail(error) {
  if (!error) return "Error desconocido";
  if (
    !error.response &&
    (error.code === "ERR_NETWORK" || String(error.message || "").includes("Network Error"))
  ) {
    const tried = resolvedRequestUrl(error);
    return `No se pudo conectar con el API (${tried || "URL no deducible"}). Comprueba que el backend esté en marcha (p. ej. \`docker compose up -d backend\` o uvicorn en el puerto configurado). Con Vite en dev, las peticiones van al mismo origen que la página + /api; el proxy debe apuntar al API. Si deseas llamar directo al puerto del API, define VITE_API_URL (p. ej. http://127.0.0.1:8000).`;
  }
  const d = error.response?.data?.detail;
  if (d == null) return error.message || "Error de red o servidor";
  if (typeof d === "string") {
    if (d === "Not Found" && error.response?.status === 404) {
      const tried = resolvedRequestUrl(error);
      const hint =
        "Comprueba VITE_API_URL (debe acabar en /api/v1 o en /api; p. ej. http://localhost:8000), que el backend esté en marcha y reiniciado tras actualizar código, y en dev que Vite haga proxy de /api al puerto 8000.";
      return `${d}. Petición: ${tried || "?"}. ${hint}`;
    }
    return d;
  }
  if (Array.isArray(d)) {
    return d
      .map((e) => {
        if (e == null) return "";
        if (typeof e === "string") return e;
        const loc = Array.isArray(e.loc) ? e.loc.join(".") : "";
        const msg = e.msg ?? e.message ?? JSON.stringify(e);
        return loc ? `${loc}: ${msg}` : msg;
      })
      .filter(Boolean)
      .join("; ");
  }
  if (typeof d === "object") return d.message || JSON.stringify(d);
  return String(d);
}

export default api;
