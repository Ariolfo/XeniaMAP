/**
 * LayerStore (F6) — registro único de descriptores de capas de mapa.
 * MapLibre sigue pintando en hooks; aquí vive solo el estado de capas (sin base64 pesado).
 */

export function createLayerDescriptor({
  id,
  name,
  kind,
  geojsonData = null,
  serverId = null,
  options = {},
  bbox = null,
}) {
  return {
    id,
    name,
    kind,
    visible: options.visible !== false,
    geojsonData,
    bbox,
    serverId: serverId || null,
    metadata: options.metadata ?? null,
    displayName: options.displayName ?? name,
  };
}

export function createLayerStore(initial = []) {
  let layers = Array.isArray(initial) ? [...initial] : [];
  let nextId = 1;
  const listeners = new Set();

  function emit() {
    const snapshot = layers;
    listeners.forEach((fn) => {
      try {
        fn(snapshot);
      } catch (_) {
        /* ignore subscriber errors */
      }
    });
  }

  return {
    list() {
      return layers;
    },

    get(id) {
      return layers.find((l) => l.id === id) || null;
    },

    nextLayerId() {
      return `layer_${nextId++}`;
    },

    /** Reemplaza la lista (p. ej. sync React → store). */
    replaceAll(next) {
      layers = Array.isArray(next) ? [...next] : [];
      emit();
      return layers;
    },

    add(entry, { append = false } = {}) {
      layers = append ? [...layers, entry] : [entry, ...layers];
      emit();
      return entry.id;
    },

    remove(id) {
      const removed = layers.find((l) => l.id === id) || null;
      layers = layers.filter((l) => l.id !== id);
      emit();
      return removed;
    },

    patch(id, patch) {
      layers = layers.map((l) => {
        if (l.id !== id) return l;
        const meta =
          patch.metadata !== undefined
            ? { ...(l.metadata || {}), ...(patch.metadata || {}) }
            : l.metadata;
        return { ...l, ...patch, metadata: meta, id: l.id };
      });
      emit();
      return this.get(id);
    },

    setVisible(id, visible) {
      return this.patch(id, { visible: !!visible });
    },

    clear() {
      layers = [];
      nextId = 1;
      emit();
    },

    resetIdCounter(n = 1) {
      nextId = n;
    },

    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
  };
}
