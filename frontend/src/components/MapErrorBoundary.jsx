import { Component } from "react";

/**
 * Evita pantalla en blanco si un hijo (p. ej. MapLibre/WebGL) lanza en render/effect.
 */
export default class MapErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("MapErrorBoundary", error, info?.componentStack);
  }

  render() {
    if (this.state.error) {
      const msg = this.state.error?.message || String(this.state.error);
      return (
        <main className="map-container">
          <div className="map-webgl-fallback" role="alert">
            <h2>Error en el mapa</h2>
            <p>
              La interfaz del mapa falló. El resto de XeniaMAP puede seguir usable tras
              recargar. Si el mensaje menciona WebGL, activa aceleración por hardware.
            </p>
            <p className="map-webgl-fallback-detail">{msg}</p>
            <button type="button" onClick={() => window.location.reload()}>
              Recargar
            </button>
          </div>
        </main>
      );
    }
    return this.props.children;
  }
}
