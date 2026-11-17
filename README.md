# TFI_Grupo_6_2026: Clasificación de Coberturas del suelo con Agentes IA

**Trabajo Final Integrador (TFI)**  
*Diplomatura Universitaria en Ingeniería de Soluciones Basadas en Inteligencia Artificial (ISBIA) - Lidesia*  
**FCEFyN - Universidad Nacional de Córdoba (UNC) / Grupo_6_2026**

### Autoría y Créditos Institucionales
- **Desarrollo, Implementación y Despliegue (asistido con IA):** Dr. Federico J. Letourneau *(IFAB INTA - CONICET)*
- **Desarrollo Conceptual:** Producto de la discusión colaborativa del **Grupo 6 (2026)**
- **Directora de la Diplomatura ISBIA:** Dra. Laura Cecilia Díaz Dávila *(LIDeSIA - FCEFyN - UNC)*
- **Antecedente / Base del Agente ReAct:** Notebook base de los docentes **Ing. Sandro Mauricio Comerci** y **Dra. Laura Cecilia Díaz Dávila** *(LIDeSIA - FCEFyN)*
- **Repositorio Oficial:** `https://github.com/intacalculemus/AG_TFI_diplo.git`

---

## 1. Descripción del Proyecto

Esta aplicación es una plataforma interactiva de teledetección y modelado hidro-territorial asistida por Inteligencia Artificial y Agentes ReAct (*Reasoning + Acting*), diseñada para profesionales de las áreas **agronómica, forestal, urbana, hídrica y ambiental**:

1. **Modelos de IA de Cobertura Terrestre (10m - Deep Learning):** Clasificación multiclase mediante **ESA WorldCover 10m** y **Esri / Impact Observatory 10m Annual LULC** (*Bosque Nativo/Árboles, Cultivos Agrícolas, Matorral, Pastizales, Suelo Desnudo, Área Urbana/Construida, Agua, Humedales, Nieve/Hielo*), con cálculo métrico de hectáreas ajustado geodésicamente por latitud.
2. **Procesador Radiométrico Sentinel-2 L2A (10m) con Selector Dinámico:** Consulta en tiempo real de escenas históricas (desde 2017 hasta la actualidad), filtrado por nubosidad y análisis espectral con bandas B04 (Rojo) y B08 (NIR) vía STAC y Cloud-Optimized GeoTIFFs (COGs).
3. **Modelado Hidrológico y Cruce Espacial `Cobertura × Pendiente` (Copernicus DEM 30m):** Cálculo de red de drenaje superficial (*Streamlines*), dirección de flujo, 6 rangos de pendiente terrestre con **enmascaramiento de cuerpos de agua**, clasificación automática de **Régimen Territorial** (*Agropecuario, Forestal de Montaña/Llanura, Urbano/Pie de Monte, Mixto, Estepa*) y módulos de diagnóstico pertinentes (*Protección de Cuencas y Ley N.° 26.331*, *Riesgo Hídrico Urbano-Aluvional*, *Interfaz Urbano-Forestal / Ley N.° 26.815* y *Manejo Agrícola*).
4. **Visor Cartográfico Multicapa con Georreferenciación Estable:** Capa base satelital híbrida con superposición de coberturas y líneas de drenaje (`ImageOverlay`), herramientas de dibujo vectorial (`Draw`) y persistencia de encuadre territorial.
5. **Geocodificación Administrativa Oficial en Argentina:** Detección automática de Provincia, Departamento/Partido y Municipio (API Georef IGN Argentina con fallback a OSM) y buscador de localidades.
6. **Asistente (Consultas y RAG):** Diálogo interactivo para interpretar métricas cuantitativas reales, matrices de cruce espacial y normativas territoriales, además de consultar la documentación del stack tecnológico y guías de intervención.
7. **Capas de Ingeniería de IA (Agent Harness, Ciberseguridad OWASP, Sandbox y Contenedores):** Orquestación con telemetría y banco de evaluación automatizado (*Golden Dataset*, 7 casos), Guardrails de entrada/salida, aislamiento de recursos satelitales y contenerización con Docker.

---

## 2. Estructura Modular del Proyecto

```text
AG_TFI_diplo/
│
├── app.py                      # Frontend Web interactivo (Streamlit + Folium + Auditoría Harness)
├── main.py                     # Demostración en consola / CLI
├── eval_harness.py             # Ejecutor CLI del Agent Evaluation Harness y Seguridad
├── config.py                   # Configuración central, rutas y parámetros
├── requirements.txt            # Dependencias completas del proyecto
├── Dockerfile                  # Contenedor endurecido (non-root appuser + GDAL)
├── docker-compose.yml          # Orquestación con límites de RAM/CPU y Sandbox de volúmenes
├── INFORME_INTEGRAL_TFI_ISBIA.md   # Informe Técnico y Arquitectónico Integral (Markdown)
├── INFORME_INTEGRAL_TFI_ISBIA.docx # Informe Integral del TFI listo para entrega (Word)
├── INFORME_ARQUITECTONICO_TFI.md   # Informe Arquitectónico de Ingeniería de IA (Markdown)
├── INFORME_ARQUITECTONICO_TFI.docx # Informe Arquitectónico listo para entrega (Word)
├── ejecutar_app.bat            # Iniciador automático en 1 clic (Windows)
├── ejecutar_app.sh             # Iniciador automático para Mac / Linux
├── INSTRUCCIONES_COMPARTIR.md  # Guía para compartir vía Google Drive
├── README.md                   # Documentación técnica general
│
├── services/                   # Motores Satelitales, Hidrológicos y Geocodificación
│   ├── __init__.py
│   ├── real_satellite_service.py # Inferencia ESA WorldCover / Esri LULC 10m, Sentinel-2 COG y caché .npz
│   ├── drainage_service.py     # Modelado DEM 30m, cruce espacial Cobertura × Pendiente y diagnóstico multi-dominio
│   └── geo_admin_service.py    # Geocodificación inversa (IGN Georef Argentina)
│
├── agent/                      # Núcleo del Asistente ReAct, Harness y Ciberseguridad
│   ├── core.py                 # GeoReActAgent + Runtime Harness con telemetría
│   ├── security.py             # Guardrails OWASP LLM (Prompt Injection, Secretos y Sandbox)
│   ├── harness.py              # Evaluation Harness automatizado (Golden Dataset)
│   ├── prompts.py              # System Prompt territorialmente neutral para Grupo_6_2026
│   └── parser.py               # Extracción determinista de herramientas y respuestas
│
├── tools/                      # Herramientas modulares con Sandbox de Ejecución
│   ├── base.py                 # Dataclass Tool (con Timeout y validación Sandbox) y ToolRegistry
│   ├── land_cover.py           # Invocación de modelos IA ESA WorldCover / Esri LULC 10m
│   ├── drainage.py             # Herramienta de red de drenaje, pendientes y cruce espacial
│   ├── geo_catalog.py          # Consulta al catálogo satelital STAC
│   ├── single_date_classifier.py # Procesamiento de bandas B04/B08 Sentinel-2
│   ├── timeseries.py           # Series temporales de NDVI y detección de tendencias
│   ├── rag_search.py           # Búsqueda RAG en stack, guías técnicas y marco normativo
│   └── visualizer.py           # Generación de gráficos temporales
│
├── rag/                        # Base de Conocimiento Documental (RAG)
│   ├── vector_store.py         # Motor de recuperación documental local
│   └── data/
│       └── corpus_ejemplo.txt  # Corpus técnico (10 bloques [DOC_ID]: stack, seguridad, harness, cuencas/Ley 26.331/IUF)
│
└── outputs/                    # Rásters clasificados y mapas generados (Filesystem Jail)
```

---

## 3. Puesta en Marcha

### Opción 1: Ejecución en 1 Clic (Windows)
Hacer doble clic sobre el archivo **`ejecutar_app.bat`**.

### Opción 2: Ejecución en 1 Clic (Mac / Linux)
```bash
chmod +x ejecutar_app.sh
./ejecutar_app.sh
```

### Opción 3: Ejecución Manual
1. **Crear y activar entorno virtual:**
   ```bash
   python -m venv venv
   venv\Scripts\activate   # Windows
   # source venv/bin/activate  # Mac / Linux
   ```
2. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Ejecutar Streamlit:**
   ```bash
   streamlit run app.py
   ```

---

## 4. Flujo de Uso
1. **Delimitar el Área de Interés:** Buscar una localidad argentina vía IGN Georef o dibujar un rectángulo sobre el mapa satelital.
2. **Clasificar Coberturas del Suelo (10m):**
   - **Modelo IA (Esri Annual LULC / ESA WorldCover):** Seleccionar fuente y año disponible en STAC y ejecutar la clasificación multiclase.
   - **Sentinel-2 L2A (NDVI):** Seleccionar año o rango de fechas (2017–presente), filtrar nubosidad, elegir la escena y procesar las bandas B04/B08.
3. **Modelar Red de Drenaje y Cruce Espacial `Cobertura × Pendiente` (30m):** Presionar *🌊 Red de Drenaje y Pendientes* para calcular escurrimiento, pendientes terrestres en 6 rangos (con agua enmascarada), matriz de tabulación cruzada, cartografía funcional y diagnóstico adaptado al régimen territorial (agrícola, forestal/cuencas, urbano o IUF).
4. **Consultar al Asistente:** Utilizar los botones de consulta rápida (*Coberturas*, *Drenaje y Pendiente*, *Stack y Código*, *Harness y Seguridad*) o formular preguntas personalizadas incluyendo criterios normativos (Ley N.° 26.331 / IUF).
