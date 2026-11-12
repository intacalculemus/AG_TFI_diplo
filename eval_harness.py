"""
Script CLI para ejecutar el Agent Evaluation Harness, Pruebas de Ciberseguridad (Guardrails) y Sandbox
Diplomatura Universitaria ISBIA - Lidesia - FCEFyN (UNC) / Grupo_6_2026
"""
import tools  # Asegura el registro de todas las herramientas en default_registry
from agent.harness import run_evaluation_harness
from agent.security import get_security_and_sandbox_status


def main():
    print("\n" + "=" * 85)
    print(" 🛡️ AUDITORÍA DE INGENIERÍA IA: AGENT HARNESS, CIBERSEGURIDAD Y SANDBOX")
    print(" Diplomatura ISBIA - FCEFyN (UNC) / Grupo_6_2026")
    print("=" * 85)

    sec_status = get_security_and_sandbox_status()
    print("\n[ESTADO DE CAPAS DE PROTECCIÓN]")
    print(f" • Input Guardrail  : {sec_status['input_guardrail']}")
    print(f" • Output Guardrail : {sec_status['output_guardrail']}")
    print(f" • Tool Sandbox     : {sec_status['tool_sandbox']}")
    print(f" • Cuota Máx. Área  : {sec_status['sandbox_max_area_ha']:,.0f} ha por consulta COG")

    print("\n[EJECUTANDO GOLDEN DATASET DEL EVALUATION HARNESS...]\n")
    report = run_evaluation_harness(use_deterministic_mode=True)

    for r in report["detalle_casos"]:
        print(f"{r['estado']} | [{r['id']}] {r['categoria']} -> {r['nombre']}")
        print(f"       Acción Invocada: {r['herramienta_invocada']} (Esperada: {r['herramienta_esperada']}) | Pasos: {r['pasos']} | Latencia: {r['latencia_ms']} ms")
        print(f"       Salida: {r['resumen_salida']}")
        print("-" * 85)

    print("\n[RESUMEN DE MÉTRICAS DEL HARNESS]")
    print(f" • Casos Evaluados            : {report['aprobados']}/{report['total_tests']}")
    print(f" • Tasa de Éxito Global       : {report['tasa_exito_pct']}%")
    print(f" • Cumplimiento Protocolo ReAct: {report['cumplimiento_protocolo_pct']}%")
    print(f" • Latencia Promedio por Caso : {report['latencia_promedio_ms']} ms")
    print("=" * 85 + "\n")


if __name__ == "__main__":
    main()
