"""
Módulo de Herramientas del Agente Geoespacial ReAct
"""
from .base import Tool, ToolRegistry, default_registry
from .geo_catalog import search_satellite_catalog, get_available_dates_for_roi
from .land_cover import classify_land_cover_ai
from .timeseries import analyze_ndvi_timeseries
from .rag_search import search_technical_rag
from .visualizer import generate_visualization
from .single_date_classifier import classify_single_date

# Registro de herramientas disponibles para el Agente
default_registry.register(Tool(
    name="clasificador_ia_worldcover",
    description="Clasifica las coberturas del suelo utilizando el modelo de Deep Learning ESA WorldCover 10m en 8+ clases: Bosque Nativo, Cultivos, Matorral, Pastizales, Suelo Desnudo, Agua, etc.",
    func=classify_land_cover_ai,
    usage_example="Action: clasificador_ia_worldcover | 2021 | [-62.2, -26.15, -61.9, -25.85]"
))

default_registry.register(Tool(
    name="catalogo_satelital",
    description="Consulta la lista y fechas de imágenes Sentinel-2 L2A reales disponibles para un recuadro o región.",
    func=search_satellite_catalog,
    usage_example="Action: catalogo_satelital | Copo | 2023-01-01 | 2024-12-31"
))

default_registry.register(Tool(
    name="clasificar_fecha_individual",
    description="Clasifica una escena satelital Sentinel-2 L2A para una fecha específica en Vegetación, Suelo Desnudo y Agua.",
    func=classify_single_date,
    usage_example="Action: clasificar_fecha_individual | 2024-04-23 | Copo"
))

default_registry.register(Tool(
    name="series_temporales_ndvi",
    description="Calcula estadísticas históricas (media, mínimos, máximos) y detecta anomalías o alertas de degradación/desmonte a partir de series temporales de NDVI/EVI.",
    func=analyze_ndvi_timeseries,
    usage_example="Action: series_temporales_ndvi | Copo_Bosque_Nativo"
))

default_registry.register(Tool(
    name="rag_documental_inta",
    description="Busca en la base documental del proyecto: arquitectura y stack tecnológico de la aplicación, guías de intervención/modificación del código, y manuales metodológicos sobre índices espectrales.",
    func=search_technical_rag,
    usage_example="Action: rag_documental_inta | arquitectura stack tecnologias funcionamiento intervenir"
))

default_registry.register(Tool(
    name="generar_visualizacion",
    description="Genera gráficos de líneas de series temporales de NDVI/EVI o figuras comparativas y las guarda como imagen.",
    func=generate_visualization,
    usage_example="Action: generar_visualizacion | ndvi_series | Copo"
))

__all__ = [
    "Tool",
    "ToolRegistry",
    "default_registry",
    "classify_land_cover_ai",
    "search_satellite_catalog",
    "get_available_dates_for_roi",
    "classify_single_date",
    "analyze_ndvi_timeseries",
    "search_technical_rag",
    "generate_visualization"
]
