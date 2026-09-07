// Feature Fire — superficie pública (H1). Implementación sigue en hooks/components.

export { default as useFireMap } from "../../hooks/useFireMap";
export { default as FirePanel } from "../../components/fire/FirePanel";
export { default as FireLayersPanel } from "../../components/fire/FireLayersPanel";
export {
  fireRasterTilesTemplate,
  fetchFireRasterMapPayload,
} from "../../utils/fireLazyLoad";
