import { useEffect, useState } from "react";

export default function AuthPanel({
  email,
  setEmail,
  password,
  setPassword,
  loading,
  authStep,
  otpDebug,
  otpHint,
  onContinueEmail,
  onVerifyOtp,
  onLogin,
  onResetEmailStep,
}) {
  const [otpLocal, setOtpLocal] = useState("");
  useEffect(() => {
    if (authStep !== "otp") setOtpLocal("");
  }, [authStep]);

  return (
    <div className="auth-simplified">
      <p className="auth-step-hint" role="status" aria-live="polite">
        {loading
          ? "Procesando…"
          : authStep === "email"
            ? "Paso 1: indique su correo. Continuará con código o contraseña según su cuenta."
            : authStep === "password"
              ? "Ingrese su contraseña para continuar."
              : otpHint || "Paso 2: introduzca el código de verificación enviado a su correo."}
      </p>
      <label>
        Correo electrónico
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="correo@ejemplo.com"
          disabled={loading || authStep === "otp"}
          autoComplete="username"
        />
      </label>

      {authStep === "email" ? (
        <div className="auth-buttons">
          <button type="button" onClick={onContinueEmail} disabled={loading}>
            {loading ? "Comprobando…" : "Continuar"}
          </button>
        </div>
      ) : null}

      {authStep === "password" ? (
        <>
          <label>
            Contraseña
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              autoComplete="current-password"
            />
          </label>
          <div className="auth-buttons">
            <button type="button" onClick={onLogin} disabled={loading}>
              Iniciar sesión
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={loading}
              onClick={() => {
                setPassword("");
                onResetEmailStep?.();
              }}
            >
              Cambiar correo
            </button>
          </div>
        </>
      ) : null}

      {authStep === "otp" ? (
        <>
          {otpHint ? <p className="auth-otp-hint">{otpHint}</p> : null}
          {!otpHint ? (
            <p className="auth-otp-hint">Revise su correo e ingrese el código de 8 dígitos.</p>
          ) : null}
          {otpDebug ? (
            <p className="auth-otp-debug">
              <strong>Modo desarrollo:</strong> código <code>{otpDebug}</code>
            </p>
          ) : null}
          <label>
            Código de verificación
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="Código de 8 dígitos"
              value={otpLocal}
              onChange={(e) => setOtpLocal(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && otpLocal.trim()) onVerifyOtp?.(otpLocal.trim());
              }}
            />
          </label>
          <div className="auth-buttons">
            <button
              type="button"
              disabled={loading}
              onClick={() => {
                const v = otpLocal.trim();
                if (v) onVerifyOtp?.(v);
              }}
            >
              {loading ? "Verificando…" : "Verificar código"}
            </button>
            <button type="button" className="btn-secondary" disabled={loading} onClick={() => onResetEmailStep?.()}>
              Cambiar correo
            </button>
          </div>
        </>
      ) : null}
    </div>
  );
}
