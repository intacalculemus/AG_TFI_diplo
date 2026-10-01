"""
Script Principal de Ejecución y Demostración del Agente GeoReAct (TFI ISBIA / INTA)
"""
import sys
from agent.core import GeoReActAgent
from tools.base import default_registry

def print_trace(trace):
    """Muestra la traza paso a paso del agente de forma estructurada y legible."""
    print("\n" + "="*70)
    print(" TRAZA DE EJECUCIÓN DEL AGENTE (Reasoning + Acting)")
    print("="*70)
    for step in trace:
        print(f"\n[PASO {step['step']}]")
        print(">> Salida del Modelo:")
        print(step['thought_and_output'])
        if step.get('action'):
            print(f"\n>> Herramienta Invocada: {step['action']}")
            print(f">> Parámetros: {step['input']}")
            print(">> Observación (Resultado):")
            # Truncar visualización si es muy larga
            obs_preview = str(step['observation'])
            if len(obs_preview) > 300:
                print(obs_preview[:300] + " ... [truncado]")
            else:
                print(obs_preview)
        print("-" * 50)

def main():
    print("\n" + "#"*70)
    print(" AGENTE INTELIGENTE PARA DETECCIÓN Y ANÁLISIS DE COBERTURA Y USO DEL SUELO")
    print(" Diplomatura Universitaria ISBIA - UNC / INTA")
    print("#"*70)

    agent = GeoReActAgent(registry=default_registry)

    # Consulta 1: Análisis integrado de cambio de cobertura y normativa
    query_1 = "¿Cuál fue la pérdida de bosque nativo en el departamento Copo entre 2018 y 2024 y qué categorías de la Ley de Bosques regulan este territorio?"
    print(f"\n>>> CONSULTA 1: {query_1}")
    
    answer_1, trace_1 = agent.run(query_1)
    print_trace(trace_1)
    print("\n>>> RESPUESTA FINAL:")
    print(answer_1)

    print("\n" + "#"*70)

    # Consulta 2: Análisis de series temporales de NDVI y generación de gráfico
    query_2 = "Analizá la serie temporal de NDVI en Copo_Bosque_Nativo y decime si se detecta degradación."
    print(f"\n>>> CONSULTA 2: {query_2}")
    
    answer_2, trace_2 = agent.run(query_2)
    print_trace(trace_2)
    print("\n>>> RESPUESTA FINAL:")
    print(answer_2)

    # Generar visualización
    print("\n>>> Generando gráfico de respaldo...")
    viz_tool = default_registry.get("generar_visualizacion")
    if viz_tool:
        res = viz_tool.run("ndvi_series | Copo_Bosque_Nativo")
        print(res)

if __name__ == "__main__":
    main()
