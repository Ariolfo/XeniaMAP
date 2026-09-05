import AuthPanel from "./AuthPanel";
import BrandHeader from "./BrandHeader";

export default function IngresoPanel({
  token,
  userRole,
  email,
  setEmail,
  password,
  setPassword,
  loading,
  authStep,
  otpDebug,
  onContinueEmail,
  onVerifyOtp,
  onResetEmailStep,
  onLogin,
  onLogout,
}) {
  return (
    <aside className="panel ingreso-panel">
      <BrandHeader email={email} />
      <h2 className="ingreso-panel-title">Ingreso</h2>
      <p className="ingreso-panel-sub">Inicie sesión para acceder a Agro, Fire y el resto de módulos.</p>
      {!token ? (
        <AuthPanel
          email={email}
          setEmail={setEmail}
          password={password}
          setPassword={setPassword}
          loading={loading}
          authStep={authStep}
          otpDebug={otpDebug}
          onContinueEmail={onContinueEmail}
          onVerifyOtp={onVerifyOtp}
          onResetEmailStep={onResetEmailStep}
          onLogin={onLogin}
        />
      ) : (
        <div className="session-info">
          <span>
            {email} ({userRole || "sin rol"})
          </span>
          <button type="button" onClick={onLogout} disabled={loading} className="btn-link">
            Cerrar sesion
          </button>
        </div>
      )}
    </aside>
  );
}
