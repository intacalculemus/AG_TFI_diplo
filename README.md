# TFI_Grupo_6_2026: Clasificación de Coberturas del suelo con Agentes IA

**Trabajo Final Integrador (TFI)**  
*Diplomatura Universitaria en Ingeniería de Soluciones Basadas en Inteligencia Artificial (ISBIA) - Lidesia*  
**FCEFyN - Universidad Nacional de Córdoba (UNC) / Grupo_6_2026**

---

## 1. Descripción del Proyecto

Esta aplicación es una plataforma interactiva de teledetección asistida por Inteligencia Artificial y Agentes ReAct (*Reasoning + Acting*), diseñada como protocolo para profesionales de las áreas agronómica, hídrica y ambiental:

1. **Modelos de IA de Cobertura Terrestre (ESA WorldCover 10m - Deep Learning):** Clasificación multiclase en 8+ categorías taxonómicas a 10 metros de resolución espacial (*Bosque Nativo/Árboles, Cultivos Agrícolas, Matorral, Pastizales, Suelo Desnudo, Construido, Agua, Humedales*).
2. **Procesador Radiométrico Sentinel-2 L2A (10m) con Selector Histórico:** Consulta en tiempo real de escenas históricas (años 2020 a 2024), filtrado por nubosidad y análisis espectral con bandas B04 (Rojo) y B08 (NIR) vía STAC y Cloud-Optimized GeoTIFFs (COGs).
3. **Visor Cartográfico Multicapa con Georreferenciación Estable:** Selector de capas base (Google Híbrido, Google Maps Calles, Google Terreno, Google Satélite Puro, OpenStreetMap, Esri World Imagery), herramientas de dibujo vectorial (Draw) y persistencia de encuadre territorial.
4. **Geocodificación Administrativa Oficial en Argentina:** Detección automática de Provincia, Departamento/Partido y Municipio (API Georef IGN Argentina con fallback a OSM).
5. **Asistente (Consultas y RAG):** Diálogo interactivo para interpretar diagnósticos cuantitativos de cobertura (hectáreas y porcentajes exactos) y consultar la documentación del stack tecnológico y guías de intervención.

---

## 2. Estructura Modular del Proyecto

```text
AG_TFI_diplo/
│
├── app.py                      # Frontend Web interactivo (Streamlit + Folium)
├── main.py                     # Demostración en consola / CLI
├── config.py                   # Configuración central, rutas y parámetros
├── requirements.txt            # Dependencias completas del proyecto
├── ejecutar_app.bat            # Iniciador automático en 1 clic (Windows)
├── ejecutar_app.sh             # Iniciador automático para Mac / Linux
├── INSTRUCCIONES_COMPARTIR.md  # Guía para compartir vía Google Drive
├── README.md                   # Documentación técnica general
│
├── services/                   # Motores de IA y Conexión Satelital
│   ├── __init__.py
│   ├── real_satellite_service.py # Inferencia ESA WorldCover 10m y streaming Sentinel-2 COG
│   └── geo_admin_service.py    # Geocodificación inversa (IGN Georef Argentina)
│
├── agent/                      # Núcleo del Asistente ReAct
│   ├── core.py                 # GeoReActAgent (bucle Thought-Action-Observation)
│   ├── prompts.py              # System Prompt especializado para Grupo_6_2026
│   └── parser.py               # Extracción de herramientas y respuestas
│
├── tools/                      # Herramientas modulares del Asistente
│   ├── base.py                 # Dataclass Tool y ToolRegistry
│   ├── land_cover.py           # Invocación de modelo IA ESA WorldCover
│   ├── geo_catalog.py          # Consulta al catálogo satelital STAC
│   ├── single_date_classifier.py # Procesamiento de bandas B04/B08 Sentinel-2
│   ├── timeseries.py           # Series temporales de NDVI y detección de tendencias
│   ├── rag_search.py           # Búsqueda RAG en el stack y guías técnicas
│   └── visualizer.py           # Generación de gráficos temporales
│
├── rag/                        # Base de Conocimiento Documental (RAG)
│   ├── vector_store.py         # Motor de recuperación documental local
│   └── data/
│       └── corpus_ejemplo.txt  # Documentación del stack, guía de intervención y métodos
│
└── outputs/                    # Rásters clasificados y mapas generados
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
1. **Delimitar el Área de Interés:** Dibujar un rectángulo o polígono sobre el mapa satelital.
2. **Seleccionar el Motor y la Fecha:**
   - **ESA WorldCover 10m:** Seleccionar año de referencia (2021 / 2020) y presionar *Ejecutar Modelo de IA*.
   - **Sentinel-2 L2A (NDVI):** Seleccionar año histórico, filtrar nubosidad, elegir la escena de la lista y presionar *Procesar Bandas*.
3. **Analizar los Resultados:** Visualizar las métricas en hectáreas, la tabla de coberturas y la capa proyectada directamente sobre el mapa sin perder el zoom ni la extensión territorial.
4. **Consultar al Asistente:** Utilizar los botones de consulta rápida (*Diagnóstico de Coberturas* o *Stack y Arquitectura*) o formular preguntas personalizadas.
