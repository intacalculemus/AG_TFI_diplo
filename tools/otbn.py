"""
Herramienta de Consulta del Ordenamiento Territorial de Bosques Nativos (OTBN - Ley N.° 26.331)
y Cruce Espacial Cobertura del Suelo x Categoría OTBN.
"""
import json
from services.otbn_service import analyze_otbn_for_bbox, DEFAULT_BBOX


def analyze_otbn_zoning(tool_input: str) -> str:
    """
    Consulta la capa oficial del Ordenamiento Territorial de Bosques Nativos (OTBN - Ley N.° 26.331)
    vía GeoServer SNMB (bosques:otbn_nacional) y calcula la distribución en hectáreas de Categorías
    I (Rojo), II (Amarillo) y III (Verde), metadatos legales provinciales y cruce Cobertura x OTBN.
    Input esperado: coordenadas [min_lon, min_lat, max_lon, max_lat]
    Ejemplo: Action: consultar_otbn_bosques | [-62.30, -26.10, -62.10, -25.90]
    """
    raw = (tool_input or "").strip()
    bbox = DEFAULT_BBOX

    if "[" in raw and "]" in raw:
        try:
            start = raw.index("[")
            end = raw.rindex("]") + 1
            candidate = json.loads(raw[start:end])
            if isinstance(candidate, list) and len(candidate) == 4:
                bbox = [float(x) for x in candidate]
        except Exception:
            bbox = DEFAULT_BBOX

    try:
        resultado = analyze_otbn_for_bbox(bbox=bbox)
        return json.dumps(resultado, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "mensaje": f"Error al consultar la capa OTBN (Ley N.° 26.331): {str(e)}"
        }, ensure_ascii=False)
