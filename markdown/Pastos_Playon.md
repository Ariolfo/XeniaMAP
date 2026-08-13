# Pastos_Playon

Resultados satelitales del cultivo, en el mismo orden y agrupación que la **landing narrativa** de XeniaMAP.

- **Proyecto ID:** 19
- **Estado:** publicado
- **Generado:** 2026-07-15 04:24 UTC

---

## Resumen

| Indicador | Valor |
|-----------|-------|
| Escenas S1 | 23 |
| Escenas S2 | 58 |
| Alta resolución (PS) | 20 |
| Periodo S1 | 2025-07-02 – 2026-06-28 |
| Periodo S2 | 2025-07-06 – 2026-06-11 |
| Periodo PS | 2025-07-27 – 2026-06-24 |

---

## Tabla de contenidos

1. [Alta resolución](#1-ps)
   - 1.1 [Vista interactiva temporal](#1-ps-interactive)
   - 1.2 [Vista temporal visible](#1-ps-rgb)
   - 1.3 [Índices de vegetación](#1-ps-indices)
      - 1.3.1 [Vigor](#1-ps-vigor)
      - 1.3.2 [Nutrición](#1-ps-nutricion)
      - 1.3.3 [Agua](#1-ps-agua)
      - 1.3.4 [Estructura](#1-ps-estructura)
   - 1.4 [Clusters generales](#1-ps-clusters)
   - 1.5 [Clusters inteligentes](#1-ps-smart-clusters)
   - 1.6 [Agrogeofísica](#1-ps-agrogeofisica)
   - 1.7 [Informe inteligente](#1-ps-ia)
2. [Sentinel 1](#2-s1)
   - 2.1 [Vista interactiva temporal](#2-s1-interactive)
   - 2.2 [Vista temporal visible](#2-s1-rgb)
   - 2.3 [Índices de vegetación](#2-s1-indices)
      - 2.3.1 [Vigor](#2-s1-vigor)
      - 2.3.2 [Nutrición](#2-s1-nutricion)
      - 2.3.3 [Agua](#2-s1-agua)
   - 2.4 [Clusters generales](#2-s1-clusters)
   - 2.5 [Informe inteligente](#2-s1-ia)
3. [Sentinel 2](#3-s2)
   - 3.1 [Vista interactiva temporal](#3-s2-interactive)
   - 3.2 [Vista temporal visible](#3-s2-rgb)
   - 3.3 [Índices de vegetación](#3-s2-indices)
      - 3.3.1 [Vigor](#3-s2-vigor)
      - 3.3.2 [Nutrición](#3-s2-nutricion)
      - 3.3.3 [Agua](#3-s2-agua)
      - 3.3.4 [Estructura](#3-s2-estructura)
   - 3.4 [Clusters generales](#3-s2-clusters)
   - 3.5 [Informe inteligente](#3-s2-ia)

---

## 1. Alta resolución {#1-ps}

### 1.1 Vista interactiva temporal {#1-ps-interactive}

_Compare índice y RGB, explore el timelapse y las series de clima._

**Contenido en la landing:** panel interactivo de timelapse, series de índices y clima.

Índices con series temporales: EVI, GIYI, KNDVI, MCARI, MSAVI2, MTVI2, NDRE, NDVI, NDWI, RSTRUCTURE, TGI, VARI (10 fechas por stack).

**Narrativa del administrador**

_Sin texto narrativo publicado para esta sección._

---

### 1.2 Vista temporal visible {#1-ps-rgb}

_Galería de escenas en color natural (RGB) a lo largo del tiempo._

**Escenas RGB en recortes:** 20

_En la aplicación se muestra la galería temporal RGB / VV (S1)._

**Narrativa del administrador**

_Sin texto narrativo publicado para esta sección._

---

### 1.3 Índices de vegetación {#1-ps-indices}

_Índices agrupados por función agronómica._

#### 1.3.1 Vigor {#1-ps-vigor}

Indican qué tan activa y productiva está la vegetación. Valores altos suelen corresponder a palmas con buen vigor.

##### NDVI — salud general del cultivo

- **Escenas disponibles:** 10 fechas (2025-07-27 – 2026-06-24)
- **Fechas:** 2025-07-27, 2025-08-23, 2025-09-20, 2025-10-29, 2025-11-10, 2025-12-27, 2026-03-29, 2026-04-30, 2026-05-22, 2026-06-24
- **Archivo:** `indecesPS/NDVI/NDVI_20250727_20260624.tif`

**Cómo leerlo:** Verde intenso = dosel denso y activo. Amarillo/naranja = estrés o baja cobertura. Rojo/marrón = suelo desnudo o vegetación muy débil.

**Interpretación:** Es el índice más conocido: resume cuánta biomasa verde hay y qué tan sana parece. En palma, caídas bruscas entre fechas pueden anticipar mortalidad o fallas de riego.

**Bajo:** suelo expuesto / vegetación débil · **Alto:** dosel denso / mayor vigor

**NDVI — salud general del cultivo (Explicación teórica)**

Índice de vegetación de diferencia normalizada (NIR−rojo)/(NIR+rojo). Resume biomasa verde y actividad fotosintética. Rango típico ≈ −1 a +1. Los colores de la galería son relativos a cada escena (percentiles): compare el mismo índice entre fechas.

##### EVI — vigor en dosel denso

- **Escenas disponibles:** 10 fechas (2025-07-27 – 2026-06-24)
- **Fechas:** 2025-07-27, 2025-08-23, 2025-09-20, 2025-10-29, 2025-11-10, 2025-12-27, 2026-03-29, 2026-04-30, 2026-05-22, 2026-06-24
- **Archivo:** `indecesPS/EVI/EVI_20250727_20260624.tif`

**Cómo leerlo:** Similar al NDVI, pero más sensible cuando el dosel es muy cerrado (palmas adultas).

**Interpretación:** Ayuda a distinguir palmas productivas de áreas con fotosíntesis reducida en lotes ya formados.

**Bajo:** baja biomasa / suelo visible · **Alto:** dosel activo y estructurado

**EVI — vigor en dosel denso (Explicación teórica)**

Índice de vegetación mejorado: reduce saturación del NDVI en doseles densos y atenúa efectos de suelo/atmósfera. Útil en palma adulta o cobertura cerrada. Colores relativos a cada escena.

##### KNDVI — vigor fino del dosel

- **Escenas disponibles:** 10 fechas (2025-07-27 – 2026-06-24)
- **Fechas:** 2025-07-27, 2025-08-23, 2025-09-20, 2025-10-29, 2025-11-10, 2025-12-27, 2026-03-29, 2026-04-30, 2026-05-22, 2026-06-24
- **Archivo:** `indecesPS/KNDVI/KNDVI_20250727_20260624.tif`

**Cómo leerlo:** Valores altos = vegetación vigorosa; bajos = estrés o baja actividad foliar.

**Interpretación:** Complementa al NDVI para ver variaciones sutiles de vigor dentro del mismo lote.

**Bajo:** baja actividad foliar · **Alto:** vegetación vigorosa

**KNDVI — vigor fino del dosel (Explicación teórica)**

Kernel NDVI: transforma el NDVI con un kernel (p. ej. tanh) para resaltar contrastes finos de vigor. Complementa al NDVI cuando las diferencias dentro del lote son sutiles. Colores relativos a cada escena.

##### MSAVI2 — vigor en etapas tempranas

- **Escenas disponibles:** 10 fechas (2025-07-27 – 2026-06-24)
- **Fechas:** 2025-07-27, 2025-08-23, 2025-09-20, 2025-10-29, 2025-11-10, 2025-12-27, 2026-03-29, 2026-04-30, 2026-05-22, 2026-06-24
- **Archivo:** `indecesPS/MSAVI2/MSAVI2_20250727_20260624.tif`

**Cómo leerlo:** Funciona bien cuando hay suelo visible entre plantas jóvenes.

**Interpretación:** Útil si hay replantes o zonas con cobertura parcial.

**Bajo:** suelo desnudo / plántulas dispersas · **Alto:** mayor cobertura verde temprana

**MSAVI2 — vigor en etapas tempranas (Explicación teórica)**

MSAVI2 (Qi et al., 1994): índice ajustado al suelo sin factor L manual. Reduce el ruido del suelo cuando hay mucha superficie desnuda (emergencia, replantes, dosel incompleto). Orientativo: −1…0,2 suelo; 0,2…0,4 plántulas; 0,4…0,6 cobertura moderada; >0,6 dosel más denso (entonces NDVI suele aportar más). Colores relativos a cada escena.

##### MTVI2 — biomasa y estructura

- **Escenas disponibles:** 10 fechas (2025-07-27 – 2026-06-24)
- **Fechas:** 2025-07-27, 2025-08-23, 2025-09-20, 2025-10-29, 2025-11-10, 2025-12-27, 2026-03-29, 2026-04-30, 2026-05-22, 2026-06-24
- **Archivo:** `indecesPS/MTVI2/MTVI2_20250727_20260624.tif`

**Cómo leerlo:** Valores altos indican mayor desarrollo de biomasa verde.

**Interpretación:** Permite comparar bloques con distinta edad o manejo.

**Bajo:** poca biomasa / dosel abierto · **Alto:** mayor biomasa y estructura foliar

**MTVI2 — biomasa y estructura (Explicación teórica)**

MTVI2 (Haboudane et al., 2004): índice triangular modificado que estima biomasa verde / LAI con corrección de fondo. Útil para comparar bloques de distinta edad o manejo. Colores relativos a cada escena.

#### 1.3.2 Nutrición {#1-ps-nutricion}

Reflejan clorofila y posibles deficiencias nutricionales. Caídas sostenidas sugieren nutrición limitada.

##### CIre — clorofila en borde rojo

**Cómo leerlo:** Sensibles a variaciones de clorofila en hojas.

**Interpretación:** Zonas persistentemente bajas merecen muestreo foliar o de suelo.

**Bajo:** menor clorofila / posible deficiencia · **Alto:** mayor clorofila / mejor estado nutricional

**CIre — clorofila en borde rojo (Explicación teórica)**

Chlorophyll Index – red edge: (NIR/borde rojo)−1 (Gitelson et al.). Proxy de clorofila y estado nutricional. Zonas bajas de forma sostenida conviene contrastar con muestreo foliar. Colores relativos a cada escena.

##### MCARI — absorción de clorofila

- **Escenas disponibles:** 10 fechas (2025-07-27 – 2026-06-24)
- **Fechas:** 2025-07-27, 2025-08-23, 2025-09-20, 2025-10-29, 2025-11-10, 2025-12-27, 2026-03-29, 2026-04-30, 2026-05-22, 2026-06-24
- **Archivo:** `indecesPS/MCARI/MCARI_20250727_20260624.tif`

**Cómo leerlo:** Resalta diferencias de clorofila entre plantas vecinas.

**Interpretación:** Ideal para detectar manchas nutricionales heterogéneas.

**Bajo:** menor absorción de clorofila · **Alto:** mayor absorción de clorofila

**MCARI — absorción de clorofila (Explicación teórica)**

Modified Chlorophyll Absorption Ratio Index (Daughtry et al.): resalta absorción de clorofila con corrección de fondo. Útil para manchas nutricionales heterogéneas dentro del lote. Colores relativos a cada escena.

##### NDRE — clorofila y nutrición

- **Escenas disponibles:** 10 fechas (2025-07-27 – 2026-06-24)
- **Fechas:** 2025-07-27, 2025-08-23, 2025-09-20, 2025-10-29, 2025-11-10, 2025-12-27, 2026-03-29, 2026-04-30, 2026-05-22, 2026-06-24
- **Archivo:** `indecesPS/NDRE/NDRE_20250727_20260624.tif`

**Cómo leerlo:** Tonos altos = buen contenido de clorofila; bajos = posible deficiencia nutricional.

**Interpretación:** Caídas localizadas pueden señalar falta de nitrógeno u otros nutrientes antes de síntomas visibles claros.

**Bajo:** menor clorofila / posible déficit nutricional · **Alto:** mayor clorofila / mejor nutrición

**NDRE — clorofila y nutrición (Explicación teórica)**

Normalized Difference Red Edge (NIR−borde rojo)/(NIR+borde rojo). Sensible a clorofila y nitrógeno foliar; suele detectar deficiencias antes que el NDVI en doseles medios–altos. Colores relativos a cada escena.

##### TGI — triángulo verde (clorofila)

- **Escenas disponibles:** 10 fechas (2025-07-27 – 2026-06-24)
- **Fechas:** 2025-07-27, 2025-08-23, 2025-09-20, 2025-10-29, 2025-11-10, 2025-12-27, 2026-03-29, 2026-04-30, 2026-05-22, 2026-06-24
- **Archivo:** `indecesPS/TGI/TGI_20250727_20260624.tif`

**Cómo leerlo:** Relacionado con el amarillamiento por falta de clorofila.

**Interpretación:** Incrementos pueden anticipar clorosis o estrés nutricional.

**Bajo:** tendencia a amarillamiento / menos clorofila · **Alto:** mayor verdor / más clorofila

**TGI — triángulo verde (clorofila) (Explicación teórica)**

Triangular Greenness Index (Hunt et al.): usa bandas visibles (azul, verde, rojo) para estimar clorofila y amarillamiento. Valores bajos anticipan clorosis o estrés nutricional visible. Colores relativos a cada escena.

#### 1.3.3 Agua {#1-ps-agua}

Contenido hídrico foliar y estrés por sequía o riego insuficiente.

##### NDWI — agua en la vegetación

- **Escenas disponibles:** 10 fechas (2025-07-27 – 2026-06-24)
- **Fechas:** 2025-07-27, 2025-08-23, 2025-09-20, 2025-10-29, 2025-11-10, 2025-12-27, 2026-03-29, 2026-04-30, 2026-05-22, 2026-06-24
- **Archivo:** `indecesPS/NDWI/NDWI_20250727_20260624.tif`

**Cómo leerlo:** Valores bajos = menor contenido hídrico foliar (sequía o riego insuficiente).

**Interpretación:** Se analiza en detalle en la sección de Análisis Hídrico.

**Bajo:** menor agua / posible estrés hídrico · **Alto:** mayor contenido hídrico

**NDWI — agua en la vegetación (Explicación teórica)**

Índice de diferencia normalizada de agua. En Sentinel-2 (Gao) usa NIR–SWIR y prioriza agua en el dosel; en PlanetScope (McFeeters) usa verde–NIR y responde también a humedad superficial. Valores bajos sugieren menor agua disponible o estrés hídrico. Colores relativos a cada escena.

#### 1.3.4 Estructura {#1-ps-estructura}

Uniformidad del dosel: huecos, plantas faltantes o copas desbalanceadas.

##### VARI — color visible del follaje

- **Escenas disponibles:** 10 fechas (2025-07-27 – 2026-06-24)
- **Fechas:** 2025-07-27, 2025-08-23, 2025-09-20, 2025-10-29, 2025-11-10, 2025-12-27, 2026-03-29, 2026-04-30, 2026-05-22, 2026-06-24
- **Archivo:** `indecesPS/VARI/VARI_20250727_20260624.tif`

**Cómo leerlo:** Verde = follaje sano; tonos pálidos = posible estrés.

**Interpretación:** Complementa índices de vigor con la apariencia visual de las copas.

**Bajo:** follaje pálido / poco verde · **Alto:** follaje más verde y vigoroso

**VARI — color visible del follaje (Explicación teórica)**

Visible Atmospherically Resistant Index (Gitelson et al.): verdor visible con cierta resistencia a atmósfera. Complementa índices NIR con la apariencia del follaje. Colores relativos a cada escena.

##### GIYI — verdor amarillento

- **Escenas disponibles:** 10 fechas (2025-07-27 – 2026-06-24)
- **Fechas:** 2025-07-27, 2025-08-23, 2025-09-20, 2025-10-29, 2025-11-10, 2025-12-27, 2026-03-29, 2026-04-30, 2026-05-22, 2026-06-24
- **Archivo:** `indecesPS/GIYI/GIYI_20250727_20260624.tif`

**Cómo leerlo:** Contrasta verde vs. amarillo en el follaje.

**Interpretación:** Cambios bruscos pueden indicar estrés hídrico o nutricional visible.

**Bajo:** predominio amarillento · **Alto:** predominio verde

**GIYI — verdor amarillento (Explicación teórica)**

Índice verde–amarillo (producto): contrasta bandas de verdor y amarillo del sensor. Cambios bruscos pueden indicar estrés hídrico, nutricional o senescencia visible. Colores relativos a cada escena.

##### R_structure — uniformidad del dosel

- **Escenas disponibles:** 10 fechas (2025-07-27 – 2026-06-24)
- **Fechas:** 2025-07-27, 2025-08-23, 2025-09-20, 2025-10-29, 2025-11-10, 2025-12-27, 2026-03-29, 2026-04-30, 2026-05-22, 2026-06-24
- **Archivo:** `indecesPS/RSTRUCTURE/RSTRUCTURE_20250727_20260624.tif`

**Cómo leerlo:** Valores altos = dosel uniforme; bajos = huecos, plantas faltantes o estrés estructural.

**Interpretación:** Caídas en el tiempo pueden señalar mortalidad o fallas de establecimiento.

**Bajo:** dosel menos uniforme / posibles huecos · **Alto:** dosel más uniforme y estructurado

**R_structure — uniformidad del dosel (Explicación teórica)**

Cociente NDRE/NDVI (índice de producto): proxy de uniformidad/estructura relativa del dosel. Valores bajos pueden indicar huecos, plantas faltantes o estrés estructural. Interpretar comparando fechas del mismo lote. Colores relativos a cada escena.

**Narrativa del administrador**

_Sin texto narrativo publicado para esta sección._

---

### 1.4 Clusters generales {#1-ps-clusters}

_Segmentación GMM por índice y multibanda._

**Resultados GMM guardados:**

- `EVI_gmm_k4.tif`
- `GIYI_gmm_k4.tif`
- `KNDVI_gmm_k4.tif`
- `MCARI_gmm_k4.tif`
- `MSAVI2_gmm_k4.tif`
- `MTVI2_gmm_k4.tif`
- `NDRE_gmm_k4.tif`
- `NDVI_gmm_k4.tif`
- `NDWI_gmm_k4.tif`
- `RSTRUCTURE_gmm_k4.tif`
- `TGI_gmm_k4.tif`
- `VARI_gmm_k4.tif`

**Narrativa del administrador**

_Sin texto narrativo publicado para esta sección._

---

### 1.5 Clusters inteligentes {#1-ps-smart-clusters}

_Clusters espacio-temporales Smart (PlanetScope)._

**smart1**
- Clusters: 4
- Pasos temporales: 10
- Índices: NDVI, NDRE, NDWI, VARI

**smart2**
- Clusters: 4
- Pasos temporales: 10
- Índices: EVI, NDRE, NDWI, VARI

**smart3**
- Clusters: 4
- Pasos temporales: 10
- Índices: KNDVI, MCARI, NDWI, VARI

**Narrativa del administrador**

_Sin texto narrativo publicado para esta sección._

---

### 1.6 Agrogeofísica {#1-ps-agrogeofisica}

_Análisis Soil Plus (Mat) guardado._

**Soil Plus (Mat, guardado)**
- Clusters: 4
- Muestras totales: 12
- Píxeles por cluster: [33, 49, 32, 14]

_En la landing se muestran miniaturas: DEM, CV, aspect, slope, cluster, bars, qchart._

**Narrativa del administrador**

_Sin texto narrativo publicado para esta sección._

---

### 1.7 Informe inteligente {#1-ps-ia}

_Texto narrativo del equipo (sin panel IA automático en este proyecto)._

_Este proyecto no muestra el panel de IA automático; solo el texto narrativo del administrador._

**Narrativa del administrador**

_Sin texto narrativo publicado para esta sección._

---

## 2. Sentinel 1 {#2-s1}

### 2.1 Vista interactiva temporal {#2-s1-interactive}

_Compare índice y RGB, explore el timelapse y las series de clima._

**Contenido en la landing:** panel interactivo de timelapse, series de índices y clima.

Índices con series temporales: NRPB, RFDI, RVI, VH_VV, VV_VH (23 fechas por stack).

**Narrativa del administrador**

_Sin texto narrativo publicado para esta sección._

---

### 2.2 Vista temporal visible {#2-s1-rgb}

_Galería de escenas en color natural (RGB) a lo largo del tiempo._

**Escenas RGB en recortes:** 23

_En la aplicación se muestra la galería temporal RGB / VV (S1)._

**Narrativa del administrador**

_Sin texto narrativo publicado para esta sección._

---

### 2.3 Índices de vegetación {#2-s1-indices}

_Índices agrupados por función agronómica._

#### 2.3.1 Vigor {#2-s1-vigor}

Indican qué tan activa y productiva está la vegetación. Valores altos suelen corresponder a palmas con buen vigor.

##### RVI — radar de volumen (Sentinel-1)

- **Escenas disponibles:** 23 fechas (2025-07-02 – 2026-06-28)
- **Fechas:** 2025-07-02, 2025-07-26, 2025-08-01, 2025-08-31, 2025-09-06, 2025-09-30, 2025-10-06, 2025-11-05, 2025-11-29, 2025-12-05, 2025-12-29, 2026-01-04, 2026-01-28, 2026-02-03, 2026-02-27, 2026-03-05, 2026-03-29, 2026-04-04, 2026-04-29, 2026-05-04, 2026-05-28, 2026-06-03, 2026-06-28
- **Archivo:** `s1indices/RVI/RVI_20250702_20260628.tif`

**Cómo leerlo:** Valores altos = mayor dispersión del radar, asociada a biomasa y estructura.

**Interpretación:** Observa el cultivo a través de nubes; útil cuando la óptica no está disponible.

**Bajo:** menor respuesta de vegetación · **Alto:** mayor biomasa / estructura radar

**RVI — radar de volumen (Sentinel-1) (Explicación teórica)**

Radar Vegetation Index: 4×VH/(VH+VV) en potencia lineal. Proxies de biomasa y estructura del dosel a través de nubes. Colores relativos a cada escena.

##### RFDI — contraste polarimétrico (Sentinel-1)

- **Escenas disponibles:** 23 fechas (2025-07-02 – 2026-06-28)
- **Fechas:** 2025-07-02, 2025-07-26, 2025-08-01, 2025-08-31, 2025-09-06, 2025-09-30, 2025-10-06, 2025-11-05, 2025-11-29, 2025-12-05, 2025-12-29, 2026-01-04, 2026-01-28, 2026-02-03, 2026-02-27, 2026-03-05, 2026-03-29, 2026-04-04, 2026-04-29, 2026-05-04, 2026-05-28, 2026-06-03, 2026-06-28
- **Archivo:** `s1indices/RFDI/RFDI_20250702_20260628.tif`

**Cómo leerlo:** Valores altos = mayor contraste VV–VH; bajos = menor contraste estructural.

**Interpretación:** Complementa al RVI para detectar cambios de estructura del cultivo con radar.

**Bajo:** menor contraste polarimétrico · **Alto:** mayor contraste estructural

**RFDI — contraste polarimétrico (Sentinel-1) (Explicación teórica)**

Radar Forest Degradation Index: (VV−VH)/(VV+VH) en lineal. Resalta contraste polarimétrico asociado a estructura. Interpretar cambios en el tiempo, no valores absolutos aislados. Colores relativos a cada escena.

#### 2.3.2 Nutrición {#2-s1-nutricion}

Reflejan clorofila y posibles deficiencias nutricionales. Caídas sostenidas sugieren nutrición limitada.

##### VV/VH — cociente polarimétrico (Sentinel-1)

- **Escenas disponibles:** 23 fechas (2025-07-02 – 2026-06-28)
- **Fechas:** 2025-07-02, 2025-07-26, 2025-08-01, 2025-08-31, 2025-09-06, 2025-09-30, 2025-10-06, 2025-11-05, 2025-11-29, 2025-12-05, 2025-12-29, 2026-01-04, 2026-01-28, 2026-02-03, 2026-02-27, 2026-03-05, 2026-03-29, 2026-04-04, 2026-04-29, 2026-05-04, 2026-05-28, 2026-06-03, 2026-06-28
- **Archivo:** `s1indices/VV_VH/VV_VH_20250702_20260628.tif`

**Cómo leerlo:** Valores altos = mayor cociente VV respecto a VH en esta escena.

**Interpretación:** Compare fechas del mismo lote: cambios pueden indicar variación de estructura o humedad.

**Bajo:** cociente polarimétrico bajo · **Alto:** cociente polarimétrico alto

**VV/VH — cociente polarimétrico (Sentinel-1) (Explicación teórica)**

Cociente VV/VH en potencia lineal. Describe la relación entre polarizaciones; no es un índice de «vigor» óptico. Interpretar tendencias temporales. Colores relativos a cada escena.

##### VH/VV — cociente polarimétrico (Sentinel-1)

- **Escenas disponibles:** 23 fechas (2025-07-02 – 2026-06-28)
- **Fechas:** 2025-07-02, 2025-07-26, 2025-08-01, 2025-08-31, 2025-09-06, 2025-09-30, 2025-10-06, 2025-11-05, 2025-11-29, 2025-12-05, 2025-12-29, 2026-01-04, 2026-01-28, 2026-02-03, 2026-02-27, 2026-03-05, 2026-03-29, 2026-04-04, 2026-04-29, 2026-05-04, 2026-05-28, 2026-06-03, 2026-06-28
- **Archivo:** `s1indices/VH_VV/VH_VV_20250702_20260628.tif`

**Cómo leerlo:** Valores altos = mayor cociente VH respecto a VV en esta escena.

**Interpretación:** Complementa VV/VH; útil para seguir cambios de estructura con radar bajo nubes.

**Bajo:** cociente polarimétrico bajo · **Alto:** cociente polarimétrico alto

**VH/VV — cociente polarimétrico (Sentinel-1) (Explicación teórica)**

Cociente VH/VV en potencia lineal. Relación polarimétrica complementaria a VV/VH. Preferir comparación entre fechas del mismo lote. Colores relativos a cada escena.

#### 2.3.3 Agua {#2-s1-agua}

Contenido hídrico foliar y estrés por sequía o riego insuficiente.

##### NRPB — índice polarimétrico normalizado (Sentinel-1)

- **Escenas disponibles:** 23 fechas (2025-07-02 – 2026-06-28)
- **Fechas:** 2025-07-02, 2025-07-26, 2025-08-01, 2025-08-31, 2025-09-06, 2025-09-30, 2025-10-06, 2025-11-05, 2025-11-29, 2025-12-05, 2025-12-29, 2026-01-04, 2026-01-28, 2026-02-03, 2026-02-27, 2026-03-05, 2026-03-29, 2026-04-04, 2026-04-29, 2026-05-04, 2026-05-28, 2026-06-03, 2026-06-28
- **Archivo:** `s1indices/NRPB/NRPB_20250702_20260628.tif`

**Cómo leerlo:** Valores altos = mayor contraste VH−VV normalizado; bajos = menor contraste.

**Interpretación:** Útil cuando la óptica falla por nubes; seguir cambios de humedad/estructura en el tiempo.

**Bajo:** señal polarimétrica más baja · **Alto:** señal polarimétrica más alta

**NRPB — índice polarimétrico normalizado (Sentinel-1) (Explicación teórica)**

Normalized Ratio Procedure between Bands: (VH−VV)/(VH+VV) en lineal. Índice polarimétrico ligado a humedad y estructura según el contexto del lote. Colores relativos a cada escena.

**Narrativa del administrador**

_Sin texto narrativo publicado para esta sección._

---

### 2.4 Clusters generales {#2-s1-clusters}

_Segmentación GMM por índice y multibanda._

_No hay resultados GMM para este sensor._

**Narrativa del administrador**

_Sin texto narrativo publicado para esta sección._

---

### 2.5 Informe inteligente {#2-s1-ia}

_Texto narrativo del equipo (sin panel IA automático en este proyecto)._

_Este proyecto no muestra el panel de IA automático; solo el texto narrativo del administrador._

**Narrativa del administrador**

_Sin texto narrativo publicado para esta sección._

---

## 3. Sentinel 2 {#3-s2}

### 3.1 Vista interactiva temporal {#3-s2-interactive}

_Compare índice y RGB, explore el timelapse y las series de clima._

**Contenido en la landing:** panel interactivo de timelapse, series de índices y clima.

Índices con series temporales: CIre, EVI, MCARI, NDVI, NDWI (12 fechas por stack).

**Narrativa del administrador**

_Sin texto narrativo publicado para esta sección._

---

### 3.2 Vista temporal visible {#3-s2-rgb}

_Galería de escenas en color natural (RGB) a lo largo del tiempo._

**Escenas RGB en recortes:** 58

_En la aplicación se muestra la galería temporal RGB / VV (S1)._

**Narrativa del administrador**

_Sin texto narrativo publicado para esta sección._

---

### 3.3 Índices de vegetación {#3-s2-indices}

_Índices agrupados por función agronómica._

#### 3.3.1 Vigor {#3-s2-vigor}

Indican qué tan activa y productiva está la vegetación. Valores altos suelen corresponder a palmas con buen vigor.

##### NDVI — salud general del cultivo

- **Escenas disponibles:** 12 fechas (2025-07-06 – 2026-06-11)
- **Fechas:** 2025-07-06, 2025-07-26, 2025-08-22, 2025-09-11, 2025-10-21, 2025-11-03, 2025-12-10, 2025-12-13, 2025-12-30, 2026-01-22, 2026-02-21, 2026-06-11
- **Archivo:** `indices/NDVI/NDVI_20250706_20260611.tif`

**Cómo leerlo:** Verde intenso = dosel denso y activo. Amarillo/naranja = estrés o baja cobertura. Rojo/marrón = suelo desnudo o vegetación muy débil.

**Interpretación:** Es el índice más conocido: resume cuánta biomasa verde hay y qué tan sana parece. En palma, caídas bruscas entre fechas pueden anticipar mortalidad o fallas de riego.

**Bajo:** suelo expuesto / vegetación débil · **Alto:** dosel denso / mayor vigor

**NDVI — salud general del cultivo (Explicación teórica)**

Índice de vegetación de diferencia normalizada (NIR−rojo)/(NIR+rojo). Resume biomasa verde y actividad fotosintética. Rango típico ≈ −1 a +1. Los colores de la galería son relativos a cada escena (percentiles): compare el mismo índice entre fechas.

##### EVI — vigor en dosel denso

- **Escenas disponibles:** 12 fechas (2025-07-06 – 2026-06-11)
- **Fechas:** 2025-07-06, 2025-07-26, 2025-08-22, 2025-09-11, 2025-10-21, 2025-11-03, 2025-12-10, 2025-12-13, 2025-12-30, 2026-01-22, 2026-02-21, 2026-06-11
- **Archivo:** `indices/EVI/EVI_20250706_20260611.tif`

**Cómo leerlo:** Similar al NDVI, pero más sensible cuando el dosel es muy cerrado (palmas adultas).

**Interpretación:** Ayuda a distinguir palmas productivas de áreas con fotosíntesis reducida en lotes ya formados.

**Bajo:** baja biomasa / suelo visible · **Alto:** dosel activo y estructurado

**EVI — vigor en dosel denso (Explicación teórica)**

Índice de vegetación mejorado: reduce saturación del NDVI en doseles densos y atenúa efectos de suelo/atmósfera. Útil en palma adulta o cobertura cerrada. Colores relativos a cada escena.

##### KNDVI — vigor fino del dosel

**Cómo leerlo:** Valores altos = vegetación vigorosa; bajos = estrés o baja actividad foliar.

**Interpretación:** Complementa al NDVI para ver variaciones sutiles de vigor dentro del mismo lote.

**Bajo:** baja actividad foliar · **Alto:** vegetación vigorosa

**KNDVI — vigor fino del dosel (Explicación teórica)**

Kernel NDVI: transforma el NDVI con un kernel (p. ej. tanh) para resaltar contrastes finos de vigor. Complementa al NDVI cuando las diferencias dentro del lote son sutiles. Colores relativos a cada escena.

##### MSAVI2 — vigor en etapas tempranas

**Cómo leerlo:** Funciona bien cuando hay suelo visible entre plantas jóvenes.

**Interpretación:** Útil si hay replantes o zonas con cobertura parcial.

**Bajo:** suelo desnudo / plántulas dispersas · **Alto:** mayor cobertura verde temprana

**MSAVI2 — vigor en etapas tempranas (Explicación teórica)**

MSAVI2 (Qi et al., 1994): índice ajustado al suelo sin factor L manual. Reduce el ruido del suelo cuando hay mucha superficie desnuda (emergencia, replantes, dosel incompleto). Orientativo: −1…0,2 suelo; 0,2…0,4 plántulas; 0,4…0,6 cobertura moderada; >0,6 dosel más denso (entonces NDVI suele aportar más). Colores relativos a cada escena.

##### MTVI2 — biomasa y estructura

**Cómo leerlo:** Valores altos indican mayor desarrollo de biomasa verde.

**Interpretación:** Permite comparar bloques con distinta edad o manejo.

**Bajo:** poca biomasa / dosel abierto · **Alto:** mayor biomasa y estructura foliar

**MTVI2 — biomasa y estructura (Explicación teórica)**

MTVI2 (Haboudane et al., 2004): índice triangular modificado que estima biomasa verde / LAI con corrección de fondo. Útil para comparar bloques de distinta edad o manejo. Colores relativos a cada escena.

#### 3.3.2 Nutrición {#3-s2-nutricion}

Reflejan clorofila y posibles deficiencias nutricionales. Caídas sostenidas sugieren nutrición limitada.

##### CIre — clorofila en borde rojo

- **Escenas disponibles:** 12 fechas (2025-07-06 – 2026-06-11)
- **Fechas:** 2025-07-06, 2025-07-26, 2025-08-22, 2025-09-11, 2025-10-21, 2025-11-03, 2025-12-10, 2025-12-13, 2025-12-30, 2026-01-22, 2026-02-21, 2026-06-11
- **Archivo:** `indices/CIre/CIre_20250706_20260611.tif`

**Cómo leerlo:** Sensibles a variaciones de clorofila en hojas.

**Interpretación:** Zonas persistentemente bajas merecen muestreo foliar o de suelo.

**Bajo:** menor clorofila / posible deficiencia · **Alto:** mayor clorofila / mejor estado nutricional

**CIre — clorofila en borde rojo (Explicación teórica)**

Chlorophyll Index – red edge: (NIR/borde rojo)−1 (Gitelson et al.). Proxy de clorofila y estado nutricional. Zonas bajas de forma sostenida conviene contrastar con muestreo foliar. Colores relativos a cada escena.

##### MCARI — absorción de clorofila

- **Escenas disponibles:** 12 fechas (2025-07-06 – 2026-06-11)
- **Fechas:** 2025-07-06, 2025-07-26, 2025-08-22, 2025-09-11, 2025-10-21, 2025-11-03, 2025-12-10, 2025-12-13, 2025-12-30, 2026-01-22, 2026-02-21, 2026-06-11
- **Archivo:** `indices/MCARI/MCARI_20250706_20260611.tif`

**Cómo leerlo:** Resalta diferencias de clorofila entre plantas vecinas.

**Interpretación:** Ideal para detectar manchas nutricionales heterogéneas.

**Bajo:** menor absorción de clorofila · **Alto:** mayor absorción de clorofila

**MCARI — absorción de clorofila (Explicación teórica)**

Modified Chlorophyll Absorption Ratio Index (Daughtry et al.): resalta absorción de clorofila con corrección de fondo. Útil para manchas nutricionales heterogéneas dentro del lote. Colores relativos a cada escena.

##### NDRE — clorofila y nutrición

**Cómo leerlo:** Tonos altos = buen contenido de clorofila; bajos = posible deficiencia nutricional.

**Interpretación:** Caídas localizadas pueden señalar falta de nitrógeno u otros nutrientes antes de síntomas visibles claros.

**Bajo:** menor clorofila / posible déficit nutricional · **Alto:** mayor clorofila / mejor nutrición

**NDRE — clorofila y nutrición (Explicación teórica)**

Normalized Difference Red Edge (NIR−borde rojo)/(NIR+borde rojo). Sensible a clorofila y nitrógeno foliar; suele detectar deficiencias antes que el NDVI en doseles medios–altos. Colores relativos a cada escena.

##### TGI — triángulo verde (clorofila)

**Cómo leerlo:** Relacionado con el amarillamiento por falta de clorofila.

**Interpretación:** Incrementos pueden anticipar clorosis o estrés nutricional.

**Bajo:** tendencia a amarillamiento / menos clorofila · **Alto:** mayor verdor / más clorofila

**TGI — triángulo verde (clorofila) (Explicación teórica)**

Triangular Greenness Index (Hunt et al.): usa bandas visibles (azul, verde, rojo) para estimar clorofila y amarillamiento. Valores bajos anticipan clorosis o estrés nutricional visible. Colores relativos a cada escena.

#### 3.3.3 Agua {#3-s2-agua}

Contenido hídrico foliar y estrés por sequía o riego insuficiente.

##### NDWI — agua en la vegetación

- **Escenas disponibles:** 12 fechas (2025-07-06 – 2026-06-11)
- **Fechas:** 2025-07-06, 2025-07-26, 2025-08-22, 2025-09-11, 2025-10-21, 2025-11-03, 2025-12-10, 2025-12-13, 2025-12-30, 2026-01-22, 2026-02-21, 2026-06-11
- **Archivo:** `indices/NDWI/NDWI_20250706_20260611.tif`

**Cómo leerlo:** Valores bajos = menor contenido hídrico foliar (sequía o riego insuficiente).

**Interpretación:** Se analiza en detalle en la sección de Análisis Hídrico.

**Bajo:** menor agua / posible estrés hídrico · **Alto:** mayor contenido hídrico

**NDWI — agua en la vegetación (Explicación teórica)**

Índice de diferencia normalizada de agua. En Sentinel-2 (Gao) usa NIR–SWIR y prioriza agua en el dosel; en PlanetScope (McFeeters) usa verde–NIR y responde también a humedad superficial. Valores bajos sugieren menor agua disponible o estrés hídrico. Colores relativos a cada escena.

#### 3.3.4 Estructura {#3-s2-estructura}

Uniformidad del dosel: huecos, plantas faltantes o copas desbalanceadas.

##### VARI — color visible del follaje

**Cómo leerlo:** Verde = follaje sano; tonos pálidos = posible estrés.

**Interpretación:** Complementa índices de vigor con la apariencia visual de las copas.

**Bajo:** follaje pálido / poco verde · **Alto:** follaje más verde y vigoroso

**VARI — color visible del follaje (Explicación teórica)**

Visible Atmospherically Resistant Index (Gitelson et al.): verdor visible con cierta resistencia a atmósfera. Complementa índices NIR con la apariencia del follaje. Colores relativos a cada escena.

##### GIYI — verdor amarillento

**Cómo leerlo:** Contrasta verde vs. amarillo en el follaje.

**Interpretación:** Cambios bruscos pueden indicar estrés hídrico o nutricional visible.

**Bajo:** predominio amarillento · **Alto:** predominio verde

**GIYI — verdor amarillento (Explicación teórica)**

Índice verde–amarillo (producto): contrasta bandas de verdor y amarillo del sensor. Cambios bruscos pueden indicar estrés hídrico, nutricional o senescencia visible. Colores relativos a cada escena.

##### R_structure — uniformidad del dosel

**Cómo leerlo:** Valores altos = dosel uniforme; bajos = huecos, plantas faltantes o estrés estructural.

**Interpretación:** Caídas en el tiempo pueden señalar mortalidad o fallas de establecimiento.

**Bajo:** dosel menos uniforme / posibles huecos · **Alto:** dosel más uniforme y estructurado

**R_structure — uniformidad del dosel (Explicación teórica)**

Cociente NDRE/NDVI (índice de producto): proxy de uniformidad/estructura relativa del dosel. Valores bajos pueden indicar huecos, plantas faltantes o estrés estructural. Interpretar comparando fechas del mismo lote. Colores relativos a cada escena.

**Narrativa del administrador**

_Sin texto narrativo publicado para esta sección._

---

### 3.4 Clusters generales {#3-s2-clusters}

_Segmentación GMM por índice y multibanda._

**Resultados GMM guardados:**

- `CIre_gmm_k4.tif`
- `EVI_gmm_k4.tif`
- `MCARI_gmm_k4.tif`
- `NDVI_gmm_k4.tif`
- `NDWI_gmm_k4.tif`

**Narrativa del administrador**

_Sin texto narrativo publicado para esta sección._

---

### 3.5 Informe inteligente {#3-s2-ia}

_Texto narrativo del equipo (sin panel IA automático en este proyecto)._

_Este proyecto no muestra el panel de IA automático; solo el texto narrativo del administrador._

**Narrativa del administrador**

_Sin texto narrativo publicado para esta sección._

---

_Documento generado automáticamente desde la estructura de la landing narrativa (XeniaMAP)._