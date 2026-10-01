"""
Herramienta de Análisis Estadístico y Detección de Anomalías en Series Temporales de NDVI / EVI
"""
import json
import pandas as pd
from pathlib import Path
from config import DATA_DIR

def analyze_ndvi_timeseries(tool_input: str) -> str:
    """
    Analiza la serie temporal de índices espectrales (NDVI y EVI) para una zona o cobertura.
    Input: nombre de la zona (ej: 'Copo_Bosque_Nativo', 'Marcos_Juarez_Agricola') | parametro_opcional
    """
    parts = [p.strip() for p in tool_input.split("|")]
    zona = parts[0] if len(parts) > 0 and parts[0] else "Copo_Bosque_Nativo"
    
    csv_file = DATA_DIR / "mock_timeseries_ndvi.csv"
    if not csv_file.exists():
        return json.dumps({"error": "Dataset de series temporales no encontrado."})

    df = pd.read_csv(csv_file)
    
    # Filtrar por zona (coincidencia parcial)
    df_filtered = df[df["zona"].str.lower().str.contains(zona.lower())].copy()
    
    if df_filtered.empty:
        zonas_disponibles = df["zona"].unique().tolist()
        return json.dumps({
            "error": f"No se encontraron registros para la zona '{zona}'.",
            "zonas_disponibles": zonas_disponibles
        }, ensure_ascii=False)

    df_filtered["fecha"] = pd.to_datetime(df_filtered["fecha"])
    df_filtered = df_filtered.sort_values("fecha")

    ndvi_mean = float(df_filtered["ndvi"].mean())
    ndvi_min = float(df_filtered["ndvi"].min())
    ndvi_max = float(df_filtered["ndvi"].max())
    
    # Evaluar tendencia entre primer y último año
    primer_ndvi = float(df_filtered.iloc[0]["ndvi"])
    ultimo_ndvi = float(df_filtered.iloc[-1]["ndvi"])
    delta_total_pct = round(((ultimo_ndvi - primer_ndvi) / primer_ndvi) * 100, 2)
    
    # Detección de caída drástica
    alerta_degradacion = bool(delta_total_pct < -30.0)

    resumen = {
        "zona_analizada": zona,
        "cantidad_observaciones": len(df_filtered),
        "rango_fechas": f"{df_filtered.iloc[0]['fecha'].strftime('%Y-%m-%d')} a {df_filtered.iloc[-1]['fecha'].strftime('%Y-%m-%d')}",
        "estadisticas_ndvi": {
            "media": round(ndvi_mean, 3),
            "minimo": round(ndvi_min, 3),
            "maximo": round(ndvi_max, 3),
            "valor_inicial": round(primer_ndvi, 3),
            "valor_final": round(ultimo_ndvi, 3),
            "variacion_porcentual_total": f"{delta_total_pct}%"
        },
        "diagnostico_biofisico": {
            "alerta_degradacion_o_desmonte": alerta_degradacion,
            "interpretacion": (
                f"Se detectó un descenso severo del NDVI ({delta_total_pct}%), compatible con pérdida de cobertura arbórea o cambio de uso de suelo hacia barbecho/cultivo."
                if alerta_degradacion
                else "La dinámica de NDVI muestra estacionalidad típica sin pérdida estructural de vigor vegetal a largo plazo."
            )
        }
    }
    return json.dumps(resumen, indent=2, ensure_ascii=False)
