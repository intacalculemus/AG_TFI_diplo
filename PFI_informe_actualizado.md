# Plataforma Forestal Inteligente (PFI)
## Diagnóstico estratégico y estudio preliminar de prefactibilidad — Versión 0.1
**Fecha:** 6 de noviembre de 2026  
**Estado:** Documento de trabajo; no constituye una evaluación económica definitiva.  
**Ámbito:** Diplomatura ISBIA y planificación de un desarrollo tecnológico forestal.

## Resumen ejecutivo
La Plataforma Forestal Inteligente (PFI) se propone como la evolución de calcuLEMUs, un sistema de cálculo forestal existente y funcional, hacia una arquitectura web modular, con potencial incorporación de asistentes conversacionales y agentes de inteligencia artificial. La versión MATLAB constituye la referencia funcional: posee tres módulos (procesamiento de inventarios de plantaciones, procesamiento de inventarios de bosque nativo y simulación del crecimiento y producción de plantaciones mediante Piltriquitrón). La versión web, desarrollada posteriormente, facilita el acceso desde un navegador, pero no reproduce todavía todo el alcance de MATLAB. Incluye un acceso externo a NotebookLM para consultas bibliográficas, antecedente acotado del primer nivel de asistencia conversacional propuesto para la PFI.

El diagnóstico identifica una oportunidad tecnológica plausible, sustentada en software y conocimiento científico preexistentes. No obstante, la conveniencia económica de la migración, la demanda de usuarios, la sostenibilidad operativa y el valor incremental de la IA permanecen sin demostrar. Se recomienda una implementación por etapas, con pruebas de equivalencia frente a MATLAB y evaluación separada de los beneficios de migración, interfaz conversacional y automatización agentica.

## 1. Alcance, metodología y criterios de evidencia
Este informe combina: (a) información aportada por el responsable del proyecto; (b) documentación pública de calcuLEMUs y su calculadora web; y (c) hipótesis estratégicas explícitamente identificadas. No se realizó auditoría del código fuente, ensayo funcional automatizado, consulta de usuarios ni presupuesto detallado. Las calificaciones de impacto y riesgo son juicios exploratorios, no estimaciones estadísticas.

Se distingue entre **hecho documentado**, **información del desarrollador**, **hipótesis** y **pendiente de verificación**. El PESTEL caracteriza el contexto externo; el FODA integra factores internos y externos; el análisis de alternativas y el ROI evalúan decisiones de inversión distintas.

## 2. Antecedentes y evolución tecnológica
### 2.1. Presentación de calcuLEMUs
**calcuLEMUs** es una herramienta informática desarrollada para el procesamiento de inventarios forestales y la simulación del crecimiento y la producción de sistemas forestales, orientada a facilitar el análisis de información dasométrica y la evaluación de alternativas de manejo. Su versión original, desarrollada en MATLAB, comprende tres módulos funcionales: procesamiento de inventarios de plantaciones forestales, procesamiento de inventarios de bosque nativo y el simulador de crecimiento y producción Piltriquitrón. Mediante la integración de procedimientos de cálculo y modelos forestales, calcuLEMUs permite transformar datos de inventario en información útil para la investigación, la planificación silvícola y la toma de decisiones de manejo. Su desarrollo constituye el antecedente científico y tecnológico sobre el cual se plantea la evolución hacia una Plataforma Forestal Inteligente (PFI).

### 2.2. calcuLEMUs MATLAB: sistema de referencia
El desarrollador informa que la aplicación MATLAB permanece totalmente funcional y requiere descarga e instalación. Consta de tres módulos:

1. **Inventarios de plantaciones:** procesa datos de inventarios forestales, calcula parámetros de rodal y presenta resultados tabulados y gráficos. La documentación incluye configuración de productos de trozado.
2. **Inventarios de bosque nativo:** analiza estructura forestal por parcelas, especies, clases diamétricas, estratos verticales y estado sanitario. Su diseño inicial se vincula con parcelas permanentes de la Reserva Loma del Medio–Río Azul, con predominio de ciprés de la cordillera y coihue. La documentación identifica, además, funciones todavía no incorporadas a este módulo; por ello, “aplicación funcional” no debe confundirse con “todas las extensiones posibles implementadas”.
3. **Simulador Piltriquitrón:** estima crecimiento y producción de plantaciones; permite proyectar inventarios de diámetros y generar tablas de producción. La documentación menciona aplicaciones para pino oregón, ponderosa, murrayana, elliottii y taeda en ámbitos regionales específicos.

### 2.3. calcuLEMUs WEB: migración parcial
El calculador web fue iniciado durante la diplomatura ISBIA mediante programación asistida con Google Antigravity y su desarrollo se interrumpió para continuar con el clasificador de coberturas. Su objetivo inicial fue facilitar el acceso a funciones de calcuLEMUs desde el navegador, no resolver fallas de MATLAB.

La interfaz publicada admite inventarios CSV/XLSX, métricas dasométricas, simulación de raleos por objetivos de densidad/área basal/densidad relativa, criterios de extracción, cubicación/trozado, visualizaciones y exportaciones. Incluye un acceso a NotebookLM como asistente de consulta conversacional sobre documentación y bibliografía silvícola. Se trata de una herramienta externa enlazada desde WEB: no consta que pueda acceder al inventario activo, interpretar resultados calculados en la sesión ni ejecutar algoritmos forestales. Constituye un antecedente del nivel 1 de asistencia con IA, pero no un chatbot integrado al motor científico. El módulo de bosque nativo y la simulación temporal de crecimiento no se encuentran integrados en la versión web según lo informado por el desarrollador.

### 2.4. PFI: propuesta de tercera generación
La PFI plantea recuperar la cobertura funcional existente, modularizar modelos y especies, habilitar acceso web, mejorar la gestión de datos y evaluar la integración de una interfaz conversacional y posteriormente de agentes. El desarrollo agentico es una hipótesis de innovación, no una capacidad actualmente demostrada.

## 3. Problema, propuesta de valor y objetivos
**Problema tecnológico:** un sistema forestal científicamente desarrollado y funcional depende de un entorno propietario y de instalación local; su migración web permanece incompleta.

**Oportunidad adicional:** una interfaz de IA podría facilitar consultas, configuración de análisis, interpretación de resultados y orquestación de tareas. Debe demostrarse que estas mejoras compensan su complejidad y costos.

**Propuesta de valor:** acceso más sencillo y reproducible a cálculos y simulaciones forestales validados, con extensibilidad para múltiples especies/modelos y asistencia inteligente opcional.

**Objetivo general:** evolucionar calcuLEMUs hacia una plataforma web abierta y modular, recuperando sus funcionalidades existentes y evaluando rigurosamente la utilidad de integrar capacidades de IA.

**Objetivos específicos:** (1) inventariar y migrar funciones de los tres módulos; (2) validar resultados respecto de MATLAB; (3) desarrollar una interfaz web utilizable sin instalación; (4) documentar modelos, unidades, supuestos y dominios de aplicación; (5) evaluar un chatbot de consulta y operación; (6) analizar la conveniencia de agentes y de futuras ampliaciones funcionales.

**Usuarios potenciales, no validados:** investigadores, técnicos, productores, administradores forestales, instituciones educativas y organismos públicos.

## 4. Aplicaciones potenciales de la asistencia conversacional y agéntica
La IA podría facilitar una interacción en lenguaje natural con la documentación, los datos y las herramientas de la PFI. Conviene diferenciar las **capacidades ya disponibles** (acceso externo a NotebookLM desde WEB) de las **funcionalidades propuestas**, que todavía requieren diseño, implementación y validación. La incorporación de IA no reemplaza los formularios ni los algoritmos científicos existentes: constituye una vía opcional de interacción y coordinación.

### 4.1. Tres niveles de integración de IA
| Nivel | Alcance | Ejemplo de interacción | Situación en el proyecto |
|---|---|---|---|
| **1. Asistencia conversacional** | Consultas en lenguaje natural, explicación de procedimientos y recuperación de documentación técnica o científica, sin ejecutar modelos. | «¿Qué significa densidad relativa y cómo se interpreta?» | **Antecedente parcial existente:** WEB ofrece acceso externo a NotebookLM; no es un asistente integrado a la sesión de cálculo. |
| **2. Asistencia con herramientas** | Interpretación de instrucciones e invocación controlada de funciones de inventario, cálculo y simulación; resultados producidos por algoritmos validados. | «Calculá el área basal por clase diamétrica de este inventario». | **Propuesto; prioridad de experimentación**. |
| **3. Coordinación agéntica de procesos** | Planificación de tareas, encadenamiento de herramientas, ejecución y comparación de escenarios, y síntesis de resultados bajo supervisión. | «Compará tres intensidades de raleo durante 20 años y prepará un informe». | **Propuesto a mediano plazo**, condicionado a validación técnica y utilidad demostrada. |

Estos niveles expresan **grados de integración funcional**, no necesariamente tres productos independientes ni una obligación de incorporar autonomía creciente. El nivel 2 constituye una hipótesis de desarrollo prioritaria porque conecta directamente la interacción en lenguaje natural con las capacidades científicas ya existentes; su conveniencia debe comprobarse frente a una interfaz convencional.

### 4.2. Consultas y operaciones ilustrativas
| Aplicación | Consulta posible | Función requerida y condición |
|---|---|---|
| Consultas de inventarios | «¿Cuál es el área basal total y su distribución por clases diamétricas?» | Leer el inventario autorizado, invocar cálculos dasométricos y presentar resultados verificables. |
| Control de calidad | «Revisá unidades, datos faltantes y valores atípicos de este archivo». | Validación estructurada; toda corrección de datos originales requiere confirmación. |
| Selección de modelos | «¿Qué modelo es aplicable a esta especie y región?» | Catálogo de modelos con referencias, variables, parámetros y dominios de validez. |
| Simulaciones silvícolas | «Compará la producción de tres alternativas de raleo». | Ejecutar modelos deterministas y registrar supuestos y escenarios. |
| Apoyo a decisiones | «¿Qué escenario maximiza volumen comercial con densidad relativa ≤ 0,6?» | Comparación explícita de criterios y restricciones; no sustituye el juicio profesional. |
| Informes | «Generá un informe técnico de este inventario y las simulaciones». | Reunir tablas, gráficos, parámetros y procedencia de los resultados. |
| Documentación científica | «¿Qué supuestos utiliza Piltriquitrón?» | Recuperación de fuentes verificables; el acceso a NotebookLM es un antecedente limitado. |
| Integraciones futuras | «Contrastá la simulación con información climática disponible». | Requiere fuentes externas, interoperabilidad y controles de calidad adicionales. |

### 4.3. Principios de implementación y evaluación
- **Separación entre IA y motor científico:** los modelos de lenguaje interpretan solicitudes y organizan operaciones; los resultados numéricos proceden de algoritmos forestales validados.
- **Trazabilidad y reproducibilidad:** conservar datos de entrada, versión del modelo, unidades, parámetros, restricciones, ejecuciones y resultados.
- **Supervisión humana:** requerir autorización para modificar datos persistentes o ejecutar acciones con consecuencias sobre decisiones de manejo.
- **Uso sin IA:** mantener disponibles las funciones convencionales de la plataforma, incluso cuando el asistente no esté disponible.
- **Evaluación incremental:** comparar exactitud, tiempo de operación, errores, usabilidad y costos de cada nivel respecto de la alternativa inmediatamente anterior.

Las operaciones descriptas son **casos de uso potenciales**, no funciones actualmente disponibles en WEB. La existencia del enlace a NotebookLM no demuestra por sí sola acceso conversacional a datos o resultados de la calculadora.

## 5. Análisis PESTEL preliminar
| Dimensión | Factores y mecanismos | Oportunidad / riesgo | Evidencia pendiente |
|---|---|---|---|
| Política | Políticas de innovación, extensión, gestión forestal y cooperación institucional | Apoyo y adopción / discontinuidad de prioridades | Programas vigentes, convenios y elegibilidad |
| Económica | Costos de licencias, migración, hosting, mantenimiento y uso de IA | Menor barrera de acceso / costos recurrentes | Presupuesto, horas y costos reales |
| Social | Capacitación digital, heterogeneidad de usuarios y confianza en modelos | Ampliación de acceso / baja adopción | Entrevistas y pruebas de usabilidad |
| Tecnológica | Ecosistema Python/web, programación asistida, APIs de modelos de lenguaje | Modularidad / dependencia de proveedores y deuda técnica | Auditoría, prototipo, pruebas |
| Ecológica | Necesidad de evaluar crecimiento, manejo, productividad y sostenibilidad | Aplicaciones de interés / interpretaciones inadecuadas | Casos de uso y métricas ambientales |
| Legal | Licencias, titularidad de código/modelos/datos, privacidad y responsabilidad profesional | Reutilización abierta / restricciones de distribución | Revisión de licencias, políticas de datos y derechos |

**Lectura estratégica:** los factores tecnológicos y la existencia de un sistema de referencia favorecen un prototipo. La sostenibilidad económica, la adopción y la gobernanza de modelos constituyen incertidumbres relevantes. No se afirma que exista demanda cuantificada ni ausencia demostrada de competidores.

## 6. Matriz FODA
| Fortalezas (internas) | Debilidades (internas) |
|---|---|
| F1. Tres módulos MATLAB funcionales. | D1. Migración web funcionalmente incompleta. |
| F2. Experiencia científica y modelos existentes. | D2. Arquitectura multiusuario y agentica aún no validada. |
| F3. Versión web publicada con cálculos y simulación de raleos. | D3. Recursos de desarrollo y mantenimiento por cuantificar. |
| F4. Documentación técnica y referencia pública del software. | D4. Falta de mediciones de demanda, tiempos y costos. |

| Oportunidades (externas) | Amenazas (externas) |
|---|---|
| O1. Herramientas abiertas para desarrollo y despliegue. | A1. Cambios de precios o disponibilidad de proveedores de IA. |
| O2. Posibilidad de alianzas científicas e institucionales. | A2. Adopción insuficiente o escasa capacidad de soporte. |
| O3. Integración futura de información espacial, climática y económica. | A3. Riesgos de seguridad y tratamiento de datos. |
| O4. Potencial de extender acceso a usuarios sin MATLAB. | A4. Uso de modelos fuera de su dominio de validez. |

**Posicionamiento competitivo:** el responsable no conoce alternativas directamente equivalentes para el ámbito específico de calcuLEMUs. Este hecho se consigna como conocimiento del desarrollador, no como demostración de inexistencia de competidores. La comparación de mercado podrá realizarse en una etapa posterior, sin que sea requisito previo para reconocer el valor del software existente.

### 6.1. Estrategias FODA cruzadas
- **FO:** utilizar la base científica y documental existente para construir un prototipo web abierto y verificable.
- **DO:** migrar por módulos, empleando herramientas de desarrollo asistido, revisión humana y pruebas automatizadas.
- **FA:** mantener el motor científico independiente del LLM y exigir trazabilidad de modelos, unidades, parámetros y resultados.
- **DA:** acotar el alcance inicial, estimar mantenimiento, validar usuarios y evitar dependencia exclusiva de servicios externos.

## 7. Evaluación de alternativas
| Alternativa | Descripción | Ventaja | Límite principal |
|---|---|---|---|
| A. Continuidad | Mantener MATLAB y la web parcial | Menor inversión inmediata; referencia funcional | Instalación y dependencia tecnológica; web incompleta |
| B. Migración web | Completar los tres módulos en arquitectura web sin IA operativa | Accesibilidad y unificación funcional | Esfuerzo de migración y validación |
| C. Web + asistencia integrada (niveles 1–2) | Evolucionar del enlace externo a NotebookLM hacia consultas integradas y ejecución controlada de herramientas | Posible mejora de experiencia y productividad | Costos, errores y necesidad de evaluación |
| D. Web con coordinación agéntica (nivel 3) | Agentes capaces de planificar y coordinar herramientas y simulaciones con controles | Posible automatización de procesos complejos | Mayor complejidad, seguridad y gobernanza |

**Criterio de decisión:** B debe evaluarse por sus beneficios tecnológicos y operativos propios. C y D se justifican únicamente si aportan beneficios incrementales medibles respecto de B. La IA no debe calcular resultados científicos mediante generación libre: debe invocar funciones deterministas validadas.

## 8. Evaluación económica y ROI: marco sin cifras inventadas
Se proponen tres comparaciones incrementales: **B–A** (valor de migración), **C–B** (valor del asistente) y **D–C** (valor adicional de agentes). Para cada una se definirán un horizonte temporal común, tasa de descuento, costos de desarrollo, mantenimiento, infraestructura, APIs, formación y soporte.

**Beneficios potencialmente monetizables:** licencias efectivamente evitadas; tiempo de instalación, operación, análisis e informes; reducción demostrada de retrabajo; costos de soporte evitados. **Beneficios no monetizados inicialmente:** reproducibilidad, difusión, docencia, colaboración y acceso público.

**ROI simple:** `ROI = (beneficios monetarios acumulados − costos acumulados) / costos acumulados × 100`.

**VAN:** `VAN = Σ_t (beneficios_t − costos_t)/(1+r)^t`, donde `r` es la tasa de descuento y `t` el año.

**Escenarios:** conservador, base y favorable, variando adopción, horas ahorradas, costo de desarrollo, mantenimiento y consumo de servicios de IA. Los valores serán incorporados solo cuando exista evidencia o supuestos transparentes y acordados.

**Advertencia:** un ROI monetario positivo no demuestra automáticamente calidad científica; se requieren pruebas independientes de equivalencia, estabilidad y seguridad.

## 9. Riesgos y mitigaciones
| Riesgo | Consecuencia | Mitigación propuesta |
|---|---|---|
| Diferencias numéricas entre MATLAB y nueva implementación | Resultados científicos inconsistentes | Casos de referencia, tolerancias, pruebas de regresión |
| Alcance excesivo | Retrasos y mantenimiento inviable | Etapas y criterios de aceptación |
| Uso de modelos fuera de su dominio | Recomendaciones inválidas | Metadatos, restricciones, advertencias y revisión humana |
| Errores o alucinaciones del asistente | Interpretaciones incorrectas | Herramientas deterministas, citas, auditoría de acciones |
| Dependencia de proveedor | Costos y discontinuidad | Abstracción de APIs, opción sin IA |
| Falta de adopción | Beneficios inferiores a lo esperado | Pruebas con usuarios y pilotos controlados |
| Exposición de datos | Riesgos legales y reputacionales | Autenticación, permisos, minimización y política de datos |

Las prioridades definitivas requieren evaluar probabilidad, impacto y detectabilidad con evidencia; no se asignan puntuaciones arbitrarias.

## 10. Hoja de ruta propuesta
**Fase 0 — Inventario y línea base:** documentar los tres módulos, versiones, dependencias, modelos, datos de ejemplo y resultados MATLAB; definir pruebas patrón.

**Fase 1 — Consolidación web:** definir arquitectura, formatos y contratos de datos; recuperar funcionalidades faltantes por módulos, con validación de equivalencia.

**Fase 2 — Piloto de usuarios:** probar carga de inventarios, simulaciones, exportación, usabilidad y mantenimiento con perfiles de usuarios definidos.

**Fase 3 — Integración conversacional y asistencia con herramientas (niveles 1–2):** aprovechar la experiencia de NotebookLM como antecedente de consulta documental; desarrollar un asistente integrado con acceso controlado a funciones del motor científico y medir tiempos, errores y utilidad frente a la interfaz convencional.

**Fase 4 — Coordinación agéntica (nivel 3) y expansión:** incorporar planificación de procesos, comparación de escenarios y nuevas áreas solo tras cumplir criterios de seguridad, calidad y beneficio incremental.

**Criterios de avance:** exactitud numérica frente a referencia; cobertura funcional documentada; reproducibilidad; aceptación de usuarios; presupuesto de mantenimiento; valor adicional comprobado de IA.

## 11. Vacíos de información y agenda de validación
1. Descripción funcional exhaustiva de los tres módulos y sus subfunciones, incluidas las limitaciones internas documentadas.
2. Acceso al código fuente y casos de prueba de MATLAB y web para verificar correspondencia de algoritmos.
3. Estado de licencias y titularidad de cada componente; confirmar alcance de Apache 2.0 y dependencias.
4. Tiempo y costos de instalación, ejecución, actualización y soporte de la versión actual.
5. Perfiles de usuarios, frecuencia de uso, tareas críticas y demanda potencial.
6. Recursos disponibles para programación, validación, hosting y mantenimiento.
7. Diseño de ensayos comparativos entre interfaz convencional, nivel 1 integrado, nivel 2 con herramientas y nivel 3 agéntico; distinguir el acceso externo existente a NotebookLM.
8. Identificación documentada de soluciones comparables, si se considera necesaria para decisiones comerciales o institucionales.
9. Definición de gobernanza y responsabilidad por recomendaciones de manejo.

## 12. Conclusiones provisionales
La PFI presenta **factibilidad conceptual favorable para una etapa de desarrollo incremental**, dado que parte de un sistema MATLAB funcional y de una migración web parcial. No es posible concluir aún su factibilidad económica, demanda real ni conveniencia de una arquitectura agentica. La prioridad es preservar y validar el núcleo científico, completar la migración por etapas y evaluar separadamente el aporte de IA. El acceso actual a NotebookLM constituye un antecedente de consulta conversacional externa (nivel 1), mientras que la integración con herramientas de cálculo (nivel 2) y la coordinación agéntica (nivel 3) permanecen como desarrollos propuestos. La recomendación no es desplegar una plataforma integral inmediatamente, sino construir evidencia suficiente para decidir su alcance y sostenibilidad.

## Fuentes consultadas
- Sitio y descripción general de calcuLEMUs: https://intacalculemus.github.io/web/index.html (consultado el 6/11/2026).
- Procesamiento de inventarios de plantaciones: https://intacalculemus.github.io/web/Page3.html (consultado el 6/11/2026).
- Procesamiento de inventarios de bosque nativo: https://intacalculemus.github.io/web/Page11.html (consultado el 6/11/2026).
- Simulador Piltriquitrón: https://intacalculemus.github.io/web/Page17.html (consultado el 6/11/2026).
- Calculadora web y manual técnico: https://intacalculemus.github.io/web/calculadora.html (consultado el 6/11/2026).
- Referencia indicada por la calculadora web: Letourneau, F. J. (2026), *calcuLEMUs*, versión 1.0.0, Zenodo, https://doi.org/10.5281/zenodo.22661942 (referencia publicada en el sitio; no se realizó comprobación independiente del registro).
- Información de antecedentes, estado funcional y cronología aportada por el desarrollador durante la elaboración de este diagnóstico.
