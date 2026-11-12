# INFORME FINAL INTEGRADOR — SÍNTESIS EJECUTIVA Y ARTICULACIÓN DE DESARROLLOS
**Diplomatura Universitaria en Ingeniería de Soluciones Basadas en Inteligencia Artificial (ISBIA — Cohorte 2026)**  
**Laboratorio de Investigación y Desarrollo en Ingeniería de Soluciones Basadas en IA (LIDESIA)**  
**Facultad de Ciencias Exactas, Físicas y Naturales (FCEFyN) — Universidad Nacional de Córdoba (UNC)**  
**Filiación Institucional:** Instituto Nacional de Tecnología Agropecuaria (INTA) — EEA Bariloche / El Bolsón  
**Autor:** Dr. / Ing. Federico Jorge Letourneau (`Grupo_6_2026`)  
**Fecha:** Noviembre de 2026

---

## 1. Introducción General y Tesis Rectora del Trabajo Final Integrador

El presente documento sintetiza y articula los tres trabajos de ingeniería, desarrollo y diagnóstico estratégico elaborados en el marco de la **Diplomatura en Ingeniería de Soluciones Basadas en Inteligencia Artificial (ISBIA)**. Aunque abordan distintos recortes operativos de la labor científica y territorial en el **Instituto Nacional de Tecnología Agropecuaria (INTA)** —la teledetección satelital y el modelado hidro-ambiental, la automatización ejecutiva multimodal de la gestión científica diaria y la evolución de sistemas de simulación dasométrica y silvícola—, los tres desarrollos responden a una **misma tesis de ingeniería de software e inteligencia artificial**:

> **Principio Rector (Arquitectura Neuro-Simbólica y Gobernanza en Producción):**  
> En dominios científico-técnicos e institucionales críticos, los Grandes Modelos de Lenguaje (LLMs) no deben emplearse como generadores libres de datos numéricos ni operar sin supervisión sobre infraestructura real. Su valor reside en actuar como **orquestadores cognitivos y semánticos** (*Patrón ReAct* y *Structured Tool-Calling*) acoplados a **motores de cálculo deterministas y auditables** (álgebra matricial geoespacial, algoritmos dasométricos o rutinas algorítmicas exactas), envueltos en capas estrictas de **ciberseguridad, ética y control humano** (*Guardrails OWASP LLM Top 10*, *Zero-Trust*, *RBAC*, *Sandboxing* y *Human-in-the-Loop*).

### Estructura Jerárquica del Informe Final
El Informe Final se estructura en tres secciones ordenadas según su **grado de importancia, nivel de madurez tecnológica y alcance de implementación**:

1. **Sección 1 (Prioridad 1 — Núcleo Principal en Producción):** *Clasificación de Coberturas del Suelo, Monitoreo Radiométrico y Modelado Hidrológico con Agentes de IA (`AG_TFI_diplo`)*. Sistema agéntico geoambiental *end-to-end* desplegado en la nube y contenerizado en Docker, con Agente ReAct nativo en Python, lectura satelital *Cloud-Native* (STAC/COG), tres motores analíticos multiescala y validación del 100% en su *Evaluation Harness*.
2. **Sección 2 (Prioridad 2 — Pilar de Orquestación Agéntica y Gobernanza Zero-Trust):** *Diseño, Evolución y Optimización de un Sistema Agéntico Ejecutivo Multimodal 360° bajo Arquitectura Zero-Trust (`v1` a `v8`)*. Infraestructura operativa diaria para la gestión científico-técnica (n8n, Google Workspace OAuth2, Visión IA y puente bidireccional endurecido con Telegram), evolucionada a lo largo de 8 versiones hasta alcanzar enrutamiento constante $O(1)$, paralelismo real y defensa en profundidad sin secretos expuestos.
3. **Sección 3 (Prioridad 3 — Diagnóstico Estratégico y Proyección Tecnológica):** *Plataforma Forestal Inteligente (`PFI`) — Diagnóstico estratégico y estudio preliminar de prefactibilidad*. Planificación arquitectónica, análisis PESTEL/FODA, marco económico incremental (ROI/VAN) y hoja de ruta en 5 fases para evolucionar el sistema de cálculo y simulación forestal **calcuLEMUs** (MATLAB y migración parcial web con enlace a NotebookLM) hacia una plataforma web modular con integración progresiva de asistencia conversacional y agéntica.

---

## 2. Accesos Directos a Desarrollos, Repositorios y Documentos

| Componente | Orden / Rol | Accesos a Desarrollos en Vivo y Repositorios | Documento Base |
| :--- | :---: | :--- | :--- |
| **1. Sistema Agéntico Geoambiental (`AG_TFI_diplo`)** | **1° (Principal)** | • **Aplicación en Vivo (Streamlit Cloud):** [https://tfi62026.streamlit.app/](https://tfi62026.streamlit.app/)<br>• **Repositorio GitHub:** [https://github.com/intacalculemus/AG_TFI_diplo.git](https://github.com/intacalculemus/AG_TFI_diplo.git) | `INFORME_INTEGRAL_TFI_ISBIA.docx` |
| **2. Agente Ejecutivo Multimodal 360° (`v1`–`v8`)** | **2° (Secundario)** | • **Arquitectura Zero-Trust Auditada:** Exhibida mediante diagramas de arquitectura $O(1)$, paralelismo *Fan-Out/Fan-In* y evidencia empírica verificada en casos reales de ISBIA (sin exponer archivos `.json` ni endpoints privados). | `Informe_Integrador_ISBIA_Agente_Ejecutivo_v1_a_v8.pdf` |
| **3. Plataforma Forestal Inteligente (`PFI` / `calcuLEMUs`)** | **3° (Complementario)** | • **Calculadora Web Interactiva:** [https://intacalculemus.github.io/web/calculadora.html](https://intacalculemus.github.io/web/calculadora.html)<br>• **Portal General `calcuLEMUs`:** [https://intacalculemus.github.io/web/index.html](https://intacalculemus.github.io/web/index.html)<br>• **Módulos:** [Plantaciones](https://intacalculemus.github.io/web/Page3.html) \| [Bosque Nativo](https://intacalculemus.github.io/web/Page11.html) \| [Simulador Piltriquitrón](https://intacalculemus.github.io/web/Page17.html)<br>• **Registro Zenodo (DOI):** [https://doi.org/10.5281/zenodo.22661942](https://doi.org/10.5281/zenodo.22661942) | `PFI_informe_actualizado.md` |

---

## 3. Síntesis de cada Sección según su Orden de Importancia

### 3.1. SECCIÓN 1 (Prioridad 1): Clasificación de Coberturas del Suelo, Monitoreo Radiométrico y Modelado Hidrológico con Agentes de IA (`AG_TFI_diplo`)

#### Problema que aborda
Los profesionales del sector agronómico, forestal e hídrico enfrentan tres barreras críticas al emplear teledetección tradicional: (1) el **alto costo computacional y de ancho de banda** de descargar escenas satelitales completas (~1 GB por tesela Sentinel-2) en conexiones rurales; (2) la **complejidad técnica** de reproyecciones cartográficas (EPSG:4326 a UTM), álgebra de bandas espectrales, inferencia con modelos de Deep Learning y cálculo de gradientes sobre modelos digitales de elevación (DEM); y (3) la **brecha entre un mapa rasterizado crudo y un diagnóstico cuantitativo integrado** con superficies exactas en hectáreas, jurisdicción administrativa y evaluación de riesgo agrohidrológico.

#### Solución de Ingeniería e Inteligencia Artificial implementada
Se diseñó, implementó y desplegó en producción (`https://tfi62026.streamlit.app/`) una plataforma web interactiva (`Streamlit` + `Folium`) asistida por un **Agente ReAct nativo en Python (`GeoReActAgent`)**, estructurada en **6 capas concéntricas desacopladas**:

1. **Procesamiento Geoespacial Cloud-Native (`STAC` + `Windowed COG`):** Consume en tiempo real el catálogo de *Microsoft Planetary Computer* vía protocolo STAC, firma criptográficamente los assets en Azure Blob Storage (`planetary_computer.sign_inplace`), reproyecta las coordenadas del polígono a UTM y ejecuta lectura parcial HTTP por ventanas (`rasterio.windows.from_bounds`) sobre archivos *Cloud-Optimized GeoTIFF (COG)*. Esto **reduce la transferencia de datos en más de un 99%** y resuelve clasificaciones a 10 metros en **2 a 6 segundos**.
2. **Tres Motores Analíticos Multiescala + Geocodificación Oficial:**
   - **Clasificación Multiclase con Deep Learning (10m):** Integra **ESA WorldCover 10m** (fusión óptica Sentinel-2 + radar SAR Sentinel-1 en 10 clases taxonómicas) y **Esri / Impact Observatory Annual LULC 10m** (serie interanual 2017–2023 en 9 clases).
   - **Monitoreo Radiométrico Multiespectral Sentinel-2 L2A (10m):** Búsqueda de escenas históricas por fecha y nubosidad, descarga de bandas B04 (Rojo) y B08 (NIR), cálculo matricial de $\text{NDVI} = \frac{B08 - B04}{B08 + B04}$ y zonificación fenológica en vegetación activa ($\text{NDVI} \ge 0,35$), suelo desnudo ($0,05 \le \text{NDVI} < 0,35$) y agua/sombras ($\text{NDVI} < 0,05$).
   - **Modelado Hidro-Topográfico y Erosión Hídrica (30m):** Opera sobre **Copernicus DEM GLO-30** (con fallback a NASADEM), calculando cotas, sombreado 3D (*Hillshade*), pendientes en 5 rangos agronómicos, vectores de escurrimiento, líneas de corriente (*Streamlines*) y cruce automático cobertura–pendiente para diagnosticar el riesgo de erosión hídrica.
   - **Geocodificación Administrativa Oficial:** Identificación en vivo de Provincia, Departamento y Municipio mediante la **API Georef del Instituto Geográfico Nacional (IGN)** con fallback a Nominatim.
3. **Agente ReAct Nativo vs. Frameworks Genéricos y *Graceful Degradation*:** Implementar el ciclo `Thought -> Action -> Observation -> FINAL` en Python puro con expresiones regulares precompiladas (`< 1 ms` de sobrecarga frente a `15–80 ms` en LangChain) reduce entre un 30% y un 50% el consumo de tokens de prompt y ofrece trazabilidad de caja blanca. Opera con arquitectura **Multi-LLM** (`Groq gpt-oss-120b`, `HuggingFace Qwen2.5-72B` y `OpenAI gpt-4o-mini`) y cuenta con un **sintetizador determinístico local de contingencia (`_synthesize_real_data`)** que garantiza disponibilidad continua y **cero alucinación numérica** ante caídas de red o límites de cuota.
4. **Ciberseguridad OWASP, RBAC, Sandbox, Contenedores y *Evaluation Harness* (100%):**
   - **Capa 0 (RBAC):** Autenticación con hash irreversible `SHA-256` + *Salt*, bloqueo por fuerza bruta (máx. 5 intentos), cuotas por sesión y log de auditoría.
   - **Capas 2 y 4 (Guardrails OWASP y Sandbox):** Mitigación activa de **OWASP LLM01** (*Prompt Injection*), **LLM02** (enmascaramiento de claves `gsk_*`, `hf_*`, `sk-*`), **LLM04** (cuota espacial máxima de `100.000 ha` y timeout de `45 s` en `ThreadPoolExecutor`) y **LLM07** (*Filesystem Jail* en `/outputs` anti *Path Traversal*).
   - **Despliegue Dual:** Nube pública en *Streamlit Community Cloud* y despliegue soberano en *Docker Compose* (`python:3.11-slim-bookworm` con GDAL, usuario sin privilegios `appuser` y límite de 2 GB de RAM).
   - **Validación Cuantitativa (`agent/harness.py`):** Tasa de éxito global del **100,0% (6/6 casos aprobados)** en el *Golden Dataset* (`TEST-01` a `TEST-06`), auditando tanto precisión en selección de herramientas y RAG como intercepción en tiempo cero de ataques OWASP.

---

### 3.2. SECCIÓN 2 (Prioridad 2): Sistema Agéntico Ejecutivo Multimodal 360° bajo Arquitectura Zero-Trust (`v1` a `v8`)

#### Problema que aborda
El trabajo de investigación en el INTA exige coordinar diariamente múltiples fuentes fragmentadas (correos técnicos de colegas de INTA, CIEFAP, CONICET y universidades; planillas presupuestarias y de muestreo en Excel/Sheets; cronogramas académicos en PDF; enlaces a carpetas compartidas en Drive; compromisos en Calendar y entregables en Tasks). Esto ocasiona pérdida de horas de concentración en triaje manual, riesgo de omisión de compromisos críticos y la imposibilidad de utilizar chatbots convencionales que carecen de acceso en vivo o que, sin controles deterministas, introducirían riesgos severos de fuga de credenciales, borrado accidental o envío de respuestas no autorizadas.

#### Solución de Ingeniería e Inteligencia Artificial implementada (`v1` $\rightarrow$ `v8`)
El sistema evolucionó empíricamente a través de **ocho iteraciones (`v1` a `v8`)** sobre **n8n**, **OpenRouter (`openai/gpt-6-luna` y `gpt-4o-mini`)**, **Google Workspace APIs (OAuth2)** y un **Puente Bidireccional Endurecido con Telegram**, consolidando cuatro pilares arquitectónicos:

1. **Arquitectura Cognitiva Híbrida (Neuro-Simbólica):**
   - **Orquestación con Esquemas JSON Tipados (`$fromAI` / Zod):** Las 8 herramientas del agente utilizan `DynamicStructuredTool`, eliminando la fragilidad de las cadenas separadas por tuberías (`|`) de las versiones `v3`–`v7`.
   - **Cálculo Determinista en Nodos `Code` (JavaScript V8):** Las estadísticas de planillas Excel (`suma`, `promedio`, `mínimo`, `máximo`), el cruce de husos horarios ISO-8601 (`-03:00`) y la detección matemática exacta de conflictos en Google Calendar ($\text{Conflicto} \iff t_{\text{inicio\_evento}} < t_{\text{fin\_solicitado}} \land t_{\text{fin\_evento}} > t_{\text{inicio\_solicitado}}$) son ejecutados algorítmicamente antes de entregar el resultado al LLM.
2. **Optimización Algorítmica: Enrutamiento Constante $O(1)$ y Paralelismo Real:**
   - **Router Principal $O(1)$ (`Switch` de 8 salidas):** Reemplaza una cascada secuencial $O(N)$ de 25 nodos `If`, asignando un índice determinista (`routeIndex` $\in \{0..7\}$), eliminando la colisión del prefijo `DRIVE|` y **reduciendo el peso del flujo JSON en un 50,4%** (de `354.262 bytes` a `175.686 bytes`).
   - **Paralelismo *Fan-Out / Fan-In* (`Merge`):** En `seguimiento_proyecto_360`, dispara 4 ramas simultáneas (*Gmail, Tasks, Drive y Calendar*) reduciendo la latencia de $\sum t_i \approx 12\text{–}16\text{ s}$ a $\max(t_i) \approx 4\text{–}5\text{ s}$ (**~65% más rápido**). En el *Briefing Matutino (L-V 08:00)*, pre-hidrata en paralelo agenda, tareas y correos pasando de **4 rondas de LLM a 1 sola ronda (-75% en inferencia)**.
3. **Pipeline Multimodal y *Document Relevance Scoring*:**
   - Unifica 4 orígenes autenticados (*Telegram móvil*, *archivos y carpetas privadas de Drive vía OAuth2*, y *adjuntos MIME de Gmail*), incluyendo desencriptación automática de PDFs con clave bancaria y Visión por Computadora (`gpt-4o-mini`).
   - Resuelve la contaminación por firmas corporativas e íconos en correos reenviados mediante un **Algoritmo de Puntuación de Relevancia Documental** que penaliza micro-imágenes (`< 15 kB` $\rightarrow$ `10 pts`) y prioriza documentos sustantivos (`EXCEL: 500`, `PDF: 480`, más `+1.000` / `+2.000 pts` por coincidencia semántica). **Evidencia real verificada (Caso Correo `1a1cf2fba4e7b91c` — Diplomatura ISBIA):** asignó `1.480 puntos` al cronograma `Talleres NOVIEMBRE 26.pdf` (`49,5 kB`) frente a `10 puntos` del ícono de firma `image.png` (`1,27 kB`), extrayendo con éxito las fechas de los talleres.
4. **Gobernanza Ética y Defensa en Profundidad Zero-Trust (6 Controles en Código Duro):**
   - **(1) Modo 100% Solo Borrador (*Human-in-the-Loop*):** Cero nodos `send` en todo el flujo; toda respuesta crea únicamente un borrador (`draft create`) en Gmail para revisión humana.
   - **(2) Resolución inteligente de `Reply-To`:** Inspecciona cabeceras completas para responder al colega real y no a casillas `noreply@google.com`.
   - **(3) 5 Reglas Anti-Borrado en código duro:** Bloquea cualquier eliminación de correos con archivos de Drive, dominios `.gob.ar`/`.edu.ar`/`.org.ar` (INTA, CIEFAP, CONICET), pagos/facturas, formularios o alertas de seguridad.
   - **(4) Privacidad estricta:** Eventos forzados a `visibility: "private"` y `sendUpdates: "none"`.
   - **(5) Sanitización Anti-Prompt Injection:** Filtrado regex de directivas maliciosas antes de pasar correos al LLM.
   - **(6) Zero Hardcoded Secrets y Enclave Local:** Cero secretos en el archivo `.json`; credenciales aisladas fuera de OneDrive con permisos NTFS (`icacls`) y validación `HMAC-SHA256` con ventana *anti-replay* de 5 minutos.

---

### 3.3. SECCIÓN 3 (Prioridad 3): Plataforma Forestal Inteligente (`PFI`) — Diagnóstico Estratégico y Estudio de Prefactibilidad

#### Problema y Oportunidad Tecnológica
**calcuLEMUs** es un sistema informático científicamente validado para el procesamiento de inventarios forestales y la simulación del crecimiento y producción silvícola. Su versión de referencia en **MATLAB** comprende tres módulos: (1) *Inventarios de plantaciones*, (2) *Inventarios de bosque nativo* (vinculado a parcelas permanentes de ciprés de la cordillera y coihue en Loma del Medio–Río Azul) y (3) el *Simulador de crecimiento y producción Piltriquitrón* (aplicable a pino oregón, ponderosa, murrayana, elliottii y taeda). Sin embargo, depende de un entorno propietario e instalación local. Durante la diplomatura ISBIA se inició mediante programación asistida con *Google Antigravity* su migración parcial hacia **calcuLEMUs WEB** (`https://intacalculemus.github.io/web/calculadora.html`), que hoy permite procesar inventarios CSV/XLSX, calcular métricas dasométricas, simular raleos, cubicar trozas y enlazar externamente a **NotebookLM** para consulta bibliográfica (antecedente acotado de asistencia de Nivel 1), pero aún no integra el módulo de bosque nativo ni la simulación temporal de crecimiento.

#### Propuesta Estratégica y Metodológica (PFI)
El estudio de prefactibilidad aplica el rigor metodológico de ISBIA —distinguiendo explícitamente entre **hecho documentado**, **información del desarrollador**, **hipótesis** y **evidencia pendiente de verificación**— para planificar la evolución hacia una **Plataforma Forestal Inteligente (PFI)** de tercera generación:

1. **Tres Niveles Progresivos de Integración de IA (bajo separación estricta IA / Motor Científico):**
   - **Nivel 1 — Asistencia Conversacional Documental:** Consultas en lenguaje natural sobre definiciones dasométricas, modelos y supuestos científicos (evolucionando desde el enlace externo actual a NotebookLM hacia un asistente integrado).
   - **Nivel 2 — Asistencia con Herramientas (*Tool-Calling* sobre Motor Determinista):** Prioridad de experimentación; el LLM interpreta instrucciones (ej. *«Calculá el área basal por clase diamétrica»*) e invoca de forma controlada los algoritmos forestales validados.
   - **Nivel 3 — Coordinación Agéntica de Procesos:** Planificación y comparación supervisada de múltiples escenarios silvícolas (ej. *«Compará tres intensidades de raleo durante 20 años»*), condicionada a validación técnica y beneficio incremental demostrado.
2. **Diagnóstico Estratégico (PESTEL, FODA y Evaluación Incremental de Alternativas A–D):**
   - Evalúa cuatro alternativas de inversión: **A (Continuidad MATLAB + Web parcial)**, **B (Migración Web completa de los 3 módulos sin IA operativa)**, **C (Web + Asistencia Niveles 1–2)** y **D (Web + Coordinación Agéntica Nivel 3)**.
   - Establece un marco económico transparente de **ROI simple** y **VAN** mediante tres comparaciones incrementales (**B–A**: valor de migración; **C–B**: valor del asistente; **D–C**: valor adicional de agentes), sin inventar cifras previas a los ensayos de usuario.
3. **Hoja de Ruta en 5 Etapas (Fases 0 a 4):**
   - **Fase 0:** Inventario funcional exhaustivo y batería de pruebas patrón frente a MATLAB.
   - **Fase 1:** Consolidación web de los tres módulos con validación de equivalencia numérica.
   - **Fase 2:** Piloto de usabilidad y carga operativa con perfiles reales de usuarios.
   - **Fase 3:** Integración conversacional y de herramientas (Niveles 1 y 2) midiendo tiempos y errores frente a la interfaz convencional.
   - **Fase 4:** Coordinación agéntica (Nivel 3) y expansión hacia datos espaciales y climáticos.

---

## 4. Matriz Comparativa Transversal de los Tres Componentes del Informe Final

| Dimensión de Ingeniería ISBIA | 1° `AG_TFI_diplo` (TFI Geoambiental) | 2° Agente Ejecutivo 360° (`v1`–`v8`) | 3° Plataforma Forestal Inteligente (`PFI` / `calcuLEMUs`) |
| :--- | :--- | :--- | :--- |
| **Nivel de Prioridad y Estado** | **Prioridad 1 (50%)** — En producción Cloud y Docker (`v1.0`). | **Prioridad 2 (30%)** — En producción operativa diaria (`v8`). | **Prioridad 3 (20%)** — Base MATLAB/Web activa + Estudio de Prefactibilidad (`v0.1`). |
| **Dominio de Aplicación en INTA** | Teledetección satelital (10m), monitoreo NDVI y modelado hidro-topográfico (30m). | Gestión ejecutiva científico-técnica, triaje multimodal y coordinación interinstitucional. | Procesamiento dasométrico de inventarios forestales y simulación silvícola (*Piltriquitrón*). |
| **Arquitectura Agéntica / IA** | Agente **ReAct nativo en Python** (`< 1 ms` parser regex) + RAG local + Multi-LLM (Groq, HF, OpenAI). | Agente **ReAct / Tool-Calling en n8n** con esquemas JSON tipados (`$fromAI` / Zod) + Visión IA (`gpt-4o-mini`). | Evolución en **3 niveles**: (1) RAG documental (antecedente NotebookLM), (2) *Tool-Calling* dasométrico y (3) Agentes de escenarios. |
| **Motor Científico / Determinista** | `rasterio`, `GDAL`, `numpy`, `shapely`, STAC/COG, ESA WorldCover, Esri LULC, Copernicus DEM e IGN Georef. | Nodos `Code` (JS V8) para aritmética de planillas, intersección exacta de intervalos horarios y *Document Relevance Scoring*. | Algoritmos forestales validados en MATLAB (3 módulos) y calculadora web JS/HTML para métricas de rodal, raleo y trozado. |
| **Ciberseguridad, Ética y Gobernanza** | **6 Capas Concéntricas:** RBAC (`SHA-256`+Salt), Guardrails **OWASP LLM01/02/04/07**, Sandbox (`100.000 ha`, `45s`) y contenedor no-root. | **Arquitectura Zero-Trust:** Modo *100% Solo Borrador*, *5 Reglas Anti-Borrado*, sanitizador Anti-Prompt Injection, `0 secretos` en JSON y `HMAC-SHA256`. | Separación estricta IA/motor científico, supervisión humana obligatoria, trazabilidad de supuestos y disponibilidad sin IA. |
| **Métricas de Validación e Impacto** | **100% de éxito (6/6)** en *Evaluation Harness* (`TEST-01` a `TEST-06`); **>99%** menos tráfico de red vía Windowed COG (2–6 s). | **-50,4%** tamaño JSON; ruteo constante **$O(1)$**; **~65%** menos latencia (`Merge` paralelo); **-75%** turnos LLM; **100%** acierto en PDF+firma. | Sistema MATLAB de referencia (3 módulos), calculadora web publicada con DOI Zenodo y hoja de ruta en 5 fases (Fases 0–4). |
