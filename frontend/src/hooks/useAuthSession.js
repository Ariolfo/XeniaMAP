import { useCallback, useEffect, useState } from "react";
import api, {
  AUTH_SESSION_MARKER,
  clearAuthTokens,
  loadStoredAuth,
  logoutOnServer,
  persistAuthTokens,
  setAuthToken,
} from "../api";
import { clearViewerEmail, persistViewerEmail, usesGeovisorBrand } from "../branding";
import { normalizeUserRole } from "../utils/userRole";

/**
 * Sesión: login/OTP/logout + restauración vía cookies HttpOnly (F5).
 */
export default function useAuthSession({
  navigate,
  fetchProjects,
  selectProject,
  clearAllMapLayers,
  location,
  setProjectId,
  setProjects,
  setTargetRasterId,
  setFireFocusOrderId,
  setActiveDomain,
  setSidebarTab,
  setUserMgmtOpen,
  setStudyRequestOpen,
  setStudyOrdersOpen,
  setStudyDraw,
  setMessage,
  setLoading,
}) {
  const [token, setToken] = useState("");
  const [userRole, setUserRole] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authStep, setAuthStep] = useState("email");
  const [pendingRegEmail, setPendingRegEmail] = useState("");
  const [otpDebug, setOtpDebug] = useState(null);
  const [otpHint, setOtpHint] = useState("");

  const normalizedUserRole = normalizeUserRole(userRole);
  const isAdmin = normalizedUserRole === "admin";
  const isCliente = normalizedUserRole === "cliente";

  useEffect(() => {
    const { access } = loadStoredAuth();
    if (access) {
      setToken(AUTH_SESSION_MARKER);
      persistAuthTokens(AUTH_SESSION_MARKER);
    }
  }, []);

  useEffect(() => {
    if (usesGeovisorBrand(email)) {
      document.title = "Geovisor Agricola";
      return () => {
        document.title = "XeniaMAP";
      };
    }
    document.title = "XeniaMAP";
    return undefined;
  }, [email]);

  useEffect(() => {
    if (!token) {
      setUserRole("");
      setProjects([]);
      return undefined;
    }
    let cancelled = false;
    const restoreSession = async () => {
      try {
        setAuthToken(token);
        const [meRes, projectList] = await Promise.all([
          api.get("/auth/me"),
          fetchProjects(token),
        ]);
        if (cancelled) return;
        setUserRole(normalizeUserRole(meRes.data?.role));
        if (meRes.data?.email) {
          setEmail(meRes.data.email);
          persistViewerEmail(meRes.data.email);
        }
        const restoreId = location.state?.restoreProjectId;
        if (restoreId && (projectList || []).some((p) => Number(p.id) === Number(restoreId))) {
          await selectProject(Number(restoreId), token);
          navigate(location.pathname || "/app", { replace: true, state: {} });
        }
      } catch (_) {
        if (!cancelled) setUserRole("");
      }
    };
    void restoreSession();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    if (!token) return;
    if (normalizedUserRole === "admin") {
      setSidebarTab((tab) => (tab === "dashboard" ? "admin" : tab));
    } else if (normalizedUserRole === "cliente") {
      setSidebarTab((tab) =>
        ["admin", "cargar", "s1", "prepro", "ps", "smart", "capas"].includes(tab)
          ? "dashboard"
          : tab
      );
    }
  }, [token, normalizedUserRole, setSidebarTab]);

  useEffect(() => {
    const onRefreshed = () => {
      setToken(AUTH_SESSION_MARKER);
    };
    const onExpired = () => {
      setToken("");
      setProjectId("");
      setProjects([]);
      setTargetRasterId("");
      setFireFocusOrderId(null);
      setActiveDomain("ingreso");
      setAuthStep("email");
      setMessage("Sesion expirada. Vuelve a iniciar sesion.");
    };
    window.addEventListener("xeniamap:auth-refreshed", onRefreshed);
    window.addEventListener("xeniamap:auth-expired", onExpired);
    return () => {
      window.removeEventListener("xeniamap:auth-refreshed", onRefreshed);
      window.removeEventListener("xeniamap:auth-expired", onExpired);
    };
  }, [
    setActiveDomain,
    setFireFocusOrderId,
    setMessage,
    setProjectId,
    setProjects,
    setTargetRasterId,
  ]);

  const loginWithCredentials = useCallback(async () => {
    setLoading(true);
    setMessage("");
    const effectiveEmail = email.trim();
    const effectivePassword = password.trim();
    if (!effectiveEmail || !effectivePassword) {
      setMessage("Error: ingresa email y password para iniciar sesion.");
      setLoading(false);
      return;
    }
    try {
      const res = await api.post("/auth/login", {
        email: effectiveEmail,
        password: effectivePassword,
      });
      const role = normalizeUserRole(res.data?.role);
      setToken(AUTH_SESSION_MARKER);
      setUserRole(role);
      persistAuthTokens(AUTH_SESSION_MARKER);
      persistViewerEmail(effectiveEmail);
      const userProjects = await fetchProjects(AUTH_SESSION_MARKER, "agro");
      const fireProjects = await fetchProjects(AUTH_SESSION_MARKER, "fire");
      const fireCount = (fireProjects || []).length;
      setMessage(
        fireCount
          ? `Sesión iniciada. Agro: ${userProjects.length} · Fire: ${fireCount}.`
          : `Sesión iniciada. ${userProjects.length} proyecto(s) Agro.`
      );
      setSidebarTab(role === "admin" ? "admin" : "dashboard");
      setActiveDomain("agro");
      setAuthStep("email");
      setOtpDebug(null);
      setOtpHint("");
      setPendingRegEmail("");
      navigate("/app");
    } catch (error) {
      const detail = error?.response?.data?.detail || error.message || "Error al iniciar sesion";
      setMessage(`Error: ${detail}`);
    } finally {
      setLoading(false);
    }
  }, [
    email,
    fetchProjects,
    navigate,
    password,
    setActiveDomain,
    setLoading,
    setMessage,
    setSidebarTab,
  ]);

  const resetEmailAuthStep = useCallback(() => {
    setAuthStep("email");
    setPendingRegEmail("");
    setOtpDebug(null);
    setOtpHint("");
    setPassword("");
    setMessage("");
  }, [setMessage]);

  const continueEmailFlow = useCallback(async () => {
    const em = email.trim();
    if (!em) {
      setMessage("Ingrese su correo electrónico.");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      const r = await api.post("/auth/check-email", { email: em });
      if (r.data?.exists) {
        const adminHit =
          !!r.data?.is_admin || String(r.data?.role || "").toLowerCase() === "admin";
        if (adminHit) {
          setAuthStep("password");
          setMessage("Correo admin detectado. Ingrese su contraseña para continuar.");
        } else {
          const o = await api.post("/auth/request-otp", { email: em });
          setPendingRegEmail(em);
          setAuthStep("otp");
          setOtpDebug(o.data?.debug_otp ?? null);
          setOtpHint(o.data?.message || "");
          setMessage(o.data?.message || "Se enviará un código de verificación a su correo.");
        }
      } else {
        const o = await api.post("/auth/request-otp", { email: em });
        setPendingRegEmail(em);
        setAuthStep("otp");
        setOtpDebug(o.data?.debug_otp ?? null);
        setOtpHint(o.data?.message || "");
        setMessage(o.data?.message || "Se enviará un código de verificación a su correo.");
      }
    } catch (error) {
      const detail =
        error?.response?.data?.detail || error.message || "Error al comprobar el correo";
      setMessage(`Error: ${detail}`);
    } finally {
      setLoading(false);
    }
  }, [email, setLoading, setMessage]);

  const verifyOtpRegister = useCallback(
    async (code) => {
      const c = String(code || "").trim();
      if (!pendingRegEmail || !c) {
        setMessage("Ingrese el código recibido.");
        return;
      }
      setLoading(true);
      setMessage("");
      try {
        const res = await api.post("/auth/verify-otp", { email: pendingRegEmail, code: c });
        const role = normalizeUserRole(res.data?.role);
        setToken(AUTH_SESSION_MARKER);
        setUserRole(role);
        persistAuthTokens(AUTH_SESSION_MARKER);
        persistViewerEmail(pendingRegEmail);
        const userProjects = await fetchProjects(AUTH_SESSION_MARKER, "agro");
        const fireProjects = await fetchProjects(AUTH_SESSION_MARKER, "fire");
        const fireCount = (fireProjects || []).length;
        const tpw = res.data.temporary_password;
        if (tpw) {
          setMessage(
            `Cuenta creada. Guarde su contraseña para próximos accesos: ${tpw} (${userProjects.length} proyecto(s).)`
          );
        } else {
          setMessage(
            fireCount
              ? `Sesión iniciada. Agro: ${userProjects.length} · Fire: ${fireCount}.`
              : `Código verificado. Sesión iniciada. ${userProjects.length} proyecto(s) Agro.`
          );
        }
        setSidebarTab(role === "admin" ? "admin" : "dashboard");
        setActiveDomain("agro");
        setAuthStep("email");
        setOtpDebug(null);
        setOtpHint("");
        setPendingRegEmail("");
        navigate("/app");
      } catch (error) {
        const detail =
          error?.response?.data?.detail || error.message || "Error al verificar el código";
        setMessage(`Error: ${detail}`);
      } finally {
        setLoading(false);
      }
    },
    [
      fetchProjects,
      navigate,
      pendingRegEmail,
      setActiveDomain,
      setLoading,
      setMessage,
      setSidebarTab,
    ]
  );

  const logoutSession = useCallback(() => {
    void logoutOnServer();
    setToken("");
    setUserRole("");
    clearAuthTokens();
    clearViewerEmail();
    setProjectId("");
    setProjects([]);
    setTargetRasterId("");
    setFireFocusOrderId(null);
    setUserMgmtOpen(false);
    setStudyRequestOpen(false);
    setStudyOrdersOpen(false);
    setStudyDraw(null);
    setAuthStep("email");
    setPendingRegEmail("");
    setOtpDebug(null);
    setOtpHint("");
    setActiveDomain("ingreso");
    clearAllMapLayers();
    setMessage("Sesion cerrada.");
    navigate("/");
  }, [
    clearAllMapLayers,
    navigate,
    setActiveDomain,
    setFireFocusOrderId,
    setMessage,
    setProjectId,
    setProjects,
    setStudyDraw,
    setStudyOrdersOpen,
    setStudyRequestOpen,
    setTargetRasterId,
    setUserMgmtOpen,
  ]);

  return {
    token,
    setToken,
    userRole,
    setUserRole,
    email,
    setEmail,
    password,
    setPassword,
    authStep,
    otpDebug,
    otpHint,
    normalizedUserRole,
    isAdmin,
    isCliente,
    loginWithCredentials,
    resetEmailAuthStep,
    continueEmailFlow,
    verifyOtpRegister,
    logoutSession,
  };
}
