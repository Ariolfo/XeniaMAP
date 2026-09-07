import { useCallback, useEffect, useState } from "react";
import api, {
  clearAuthTokens,
  loadStoredAuth,
  persistAuthTokens,
  setAuthToken,
} from "../api";
import { clearViewerEmail, persistViewerEmail, usesGeovisorBrand } from "../branding";
import { normalizeUserRole } from "../utils/userRole";

/**
 * Sesión: login/OTP/logout + restauración de token.
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
    const { access, refresh } = loadStoredAuth();
    if (access && refresh) {
      setToken(access);
      persistAuthTokens(access, refresh);
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
    const onRefreshed = (e) => {
      if (e.detail?.access_token) setToken(e.detail.access_token);
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

  const registerAndLogin = useCallback(async () => {
    const effectiveEmail = email.trim();
    const effectivePassword = password.trim();
    if (!effectiveEmail || !effectivePassword) {
      setMessage("Error: ingresa email y password para crear cuenta.");
      return;
    }
    setLoading(true);
    setMessage("");
    const tenantName = effectiveEmail.split("@")[1] || "default";
    try {
      const res = await api.post("/auth/register", {
        tenant_name: tenantName,
        email: effectiveEmail,
        password: effectivePassword,
      });
      const accessToken = res.data.access_token;
      setToken(accessToken);
      setUserRole(normalizeUserRole(res.data?.role));
      persistAuthTokens(accessToken, res.data.refresh_token);
      persistViewerEmail(effectiveEmail);
      const userProjects = await fetchProjects(accessToken);
      setMessage(`Cuenta creada. ${userProjects.length} proyecto(s) encontrado(s).`);
      navigate("/app");
    } catch (error) {
      const detail = error?.response?.data?.detail || error.message || "Error al crear cuenta";
      setMessage(`Error: ${detail}`);
    } finally {
      setLoading(false);
    }
  }, [email, fetchProjects, navigate, password, setLoading, setMessage]);

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
      const accessToken = res.data.access_token;
      const role = normalizeUserRole(res.data?.role);
      setToken(accessToken);
      setUserRole(role);
      persistAuthTokens(accessToken, res.data.refresh_token);
      persistViewerEmail(effectiveEmail);
      const userProjects = await fetchProjects(accessToken, "agro");
      const fireProjects = await fetchProjects(accessToken, "fire");
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
        const accessToken = res.data.access_token;
        const role = normalizeUserRole(res.data?.role);
        setToken(accessToken);
        setUserRole(role);
        persistAuthTokens(accessToken, res.data.refresh_token);
        persistViewerEmail(pendingRegEmail);
        const userProjects = await fetchProjects(accessToken, "agro");
        const fireProjects = await fetchProjects(accessToken, "fire");
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
          error?.response?.data?.detail || error.message || "Código incorrecto o expirado";
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
    registerAndLogin,
    loginWithCredentials,
    resetEmailAuthStep,
    continueEmailFlow,
    verifyOtpRegister,
    logoutSession,
  };
}
