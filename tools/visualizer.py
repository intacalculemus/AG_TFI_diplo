"""
Herramienta de Generación de Visualizaciones y Gráficos Geoespaciales
"""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path
from config import DATA_DIR, OUTPUTS_DIR

def generate_visualization(tool_input: str) -> str:
    """
    Genera gráficos de series temporales de NDVI o comparativas de cobertura y los guarda en disco.
    Input: tipo_grafico (ej: 'ndvi_series', 'cobertura_barras') | parametro (ej: 'Copo')
    """
    parts = [p.strip() for p in tool_input.split("|")]
    tipo = parts[0].lower() if len(parts) > 0 and parts[0] else "ndvi_series"
    param = parts[1] if len(parts) > 1 else "Copo"

    try:
        if "ndvi" in tipo:
            csv_file = DATA_DIR / "mock_timeseries_ndvi.csv"
            if not csv_file.exists():
                return "Error: archivo de datos de NDVI no encontrado."

            df = pd.read_csv(csv_file)
            df_sub = df[df["zona"].str.lower().str.contains(param.lower())].copy()

            if df_sub.empty:
                df_sub = df.copy()

            df_sub["fecha"] = pd.to_datetime(df_sub["fecha"])
            df_sub = df_sub.sort_values("fecha")

            plt.figure(figsize=(9, 4.5))
            plt.plot(df_sub["fecha"], df_sub["ndvi"], marker="o", color="#2e7d32", linewidth=2, label="NDVI")
            if "evi" in df_sub.columns:
                plt.plot(df_sub["fecha"], df_sub["evi"], marker="s", color="#81c784", linestyle="--", label="EVI")

            plt.title(f"Dinámica Temporal de NDVI/EVI - Zona: {param}", fontsize=12, fontweight="bold")
            plt.xlabel("Fecha")
            plt.ylabel("Valor de Índice")
            plt.grid(True, linestyle=":", alpha=0.6)
            plt.legend()
            plt.tight_layout()

            output_file = OUTPUTS_DIR / f"serie_ndvi_{param.replace(' ', '_').lower()}.png"
            plt.savefig(output_file, dpi=150)
            plt.close()

            return json.dumps({
                "status": "success",
                "tipo": "grafico_serie_temporal",
                "archivo_generado": str(output_file),
                "mensaje": f"Se generó y guardó correctamente el gráfico de series temporales en {output_file.name}."
            }, ensure_ascii=False)

        else:
            return json.dumps({
                "status": "warning",
                "mensaje": f"Tipo de gráfico '{tipo}' no reconocido. Opciones: 'ndvi_series'."
            }, ensure_ascii=False)

    except Exception as e:
        return f"Error al generar visualización: {str(e)}"
