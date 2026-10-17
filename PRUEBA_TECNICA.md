# Prueba técnica: mejora de la entrega de tarjetas

El banco trabaja con varios transportistas para entregar tarjetas a sus clientes.
Tu objetivo es mejorar la **satisfacción del cliente, el tiempo de entrega y el
coste**, respetando los plazos y las reglas del servicio.

## Por dónde empezar

1. Lee esta guía: explica el ejercicio, cómo ejecutarlo y qué entregar.
2. Consulta [las reglas de negocio](REGLAS_PUBLICAS.md) para entender el servicio.
   Su primera parte resume la operativa; después encontrarás el detalle para programar.
3. Revisa [la evaluación](EVALUACION.md) para conocer los requisitos y la puntuación.
4. Sigue [el manual del candidato](README.md) para las fechas, tu repositorio y la entrega.

## Qué tienes que hacer

Modifica la clase `CandidateStrategy` de `candidate_strategy.py`: decide cómo
despachar las tarjetas con los transportistas disponibles. El motor controla
el tiempo, ejecuta los transportes y calcula los resultados. La implementación
inicial no garantiza superar la evaluación; tú decides qué cambiar y cómo comprobarlo.

Puedes utilizar IA generativa. La entrega es individual y eres responsable
de revisar, comprender y justificar la solución. Declara las fuentes externas
y las ayudas utilizadas. Consulta las reglas de autoría, copia y colaboración
en [la evaluación](EVALUACION.md).

El código y la documentación de apoyo proceden de una implementación heredada.
Pueden estar desactualizados o incluir guías para acelerar el desarrollo.
Dispones también de dos notas de traspaso en `anexos/`.

La simulación recibe tarjetas durante 90 días y después continúa hasta su cierre.
Los escenarios pueden variar la demanda, los transportistas, las tarifas,
las capacidades y el calendario dentro de las reglas publicadas. La estrategia
recibe los valores de cada escenario mediante las interfaces.

## Cómo ejecutarlo

Necesitas Python 3.11 o superior. Desde la raíz del repositorio:

```text
python run.py
python run_150k.py
python -m unittest discover -s tests -v
```

Los dos primeros comandos ejecutan los ejemplos de 5.000 y 150.000 tarjetas.
Generan `output/performance_report.json` y
`output/performance_report_150k.json`. Son casos de desarrollo y no puntúan.

## Qué es cada archivo

| Archivo o carpeta | Para qué sirve |
|---|---|
| `README.md` | Manual del candidato: fechas, repositorio y entrega. |
| `PRUEBA_TECNICA.md` | Esta guía: objetivo, ejecución y contenido de la entrega. |
| `FAQ.md` | Preguntas frecuentes; se actualiza durante la prueba. |
| `REGLAS_PUBLICAS.md` | Reglas de negocio y referencia técnica del simulador. |
| `EVALUACION.md` | Requisitos para superar la prueba y cálculo de la nota. |
| `candidate_strategy.py` | Tu solución. Es el único archivo de código que incorpora el evaluador. |
| `interfaces.py` | Tipos de datos y funciones con las que tu estrategia se comunica con el motor. |
| `run.py`, `run_150k.py` | Lanzadores de los dos ejemplos públicos. |
| `engine/` | Código del simulador; puedes consultarlo para entender su funcionamiento. |
| `tests/` | Pruebas de ejemplo. Puedes crear pruebas adicionales para tu solución. |
| `data/` | Datos del ejemplo pequeño. |
| `scenarios/public_150k/` | Datos del ejemplo grande, con el mismo formato. |
| `anexos/nota_traspaso_legacy.pdf` | Nota de traspaso de la implementación heredada. |
| `anexos/nota_operaciones_legacy.md` | Nota de operaciones de la implementación heredada. |
| `submission/` | Carpeta de tu entrega, que creas en la raíz del repositorio: ver «Qué entregar». |
| `performance_report.schema.json` | Define la estructura del informe de resultados generado por el motor. |
| `submission_manifest.schema.json` | Define la estructura del inventario que acompañará tu entrega. |
| `protected_files.sha256` | Inventario automático de huellas digitales para comprobar que los archivos de referencia no han cambiado. No tienes que leerlo, rellenarlo ni entregarlo. |
| `output/` | Resultados locales generados al ejecutar los ejemplos. |

Dentro de cada carpeta de datos:

| Archivo | Contenido |
|---|---|
| `shipments.csv` | Tarjetas que debe gestionar la simulación. |
| `carriers.json` | Transportistas, tarifas, capacidades y disponibilidad. |
| `holidays.csv` | Festivos que afectan a los calendarios. |
| `scenario.toml` | Configuración del escenario. |
| `rules.toml` | Parámetros numéricos de las reglas del servicio. |
| `generation_manifest.json` | Información de generación e integridad de esos datos; no hay que rellenarla. |

El evaluador ejecuta tu `candidate_strategy.py` sobre una copia limpia del repositorio del reto.
Los cambios locales en el motor, las interfaces o los datos no forman parte de la solución evaluada.

## Qué entregar

En la raíz de tu repositorio, prepara una carpeta con esta estructura:

```text
submission/
├── candidate_strategy.py
├── generated_artifacts/
├── ai_conversations/
├── STRATEGY.md
└── submission_manifest.json
```

- **candidate_strategy.py:** tu solución final.
- **generated_artifacts/:** el resto del código generado durante el ejercicio
  (pruebas, scripts y prototipos). Excluye dependencias, cachés y datasets.
  Si está vacía, incluye `.gitkeep` y decláralo en el inventario.
- **ai_conversations/:** historial técnico completo y cronológico de las
  conversaciones con IA, incluidos los intentos fallidos. Se acepta Markdown,
  JSON, HTML o texto, con los roles identificados. Indica herramienta, modelo
  si se conoce y fecha aproximada.
- **STRATEGY.md:** explica qué cambiaste y por qué, qué resultados mediste,
  qué alternativas consideraste y qué limitaciones quedan. Identifica las fuentes
  externas, las partes reutilizadas y las ayudas técnicas recibidas. Describe cómo
  utilizaste la IA y cómo verificaste sus aportaciones. Distingue resultados
  medidos, hipótesis y trabajo pendiente. Extensión recomendada: hasta 2.500 palabras.
- **submission_manifest.json:** inventario de los archivos y herramientas utilizados,
  siguiendo `submission_manifest.schema.json`. En `candidate_name`, indica tu nombre
  completo y, en `candidate`, el correo con el que te inscribiste en Genoma.

Ejemplo de inventario:

```json
{
  "candidate": "correo-de-inscripcion@dominio.com",
  "candidate_name": "Nombre y apellidos",
  "models_and_tools": [{"tool": "nombre", "model": "modelo-o-desconocido"}],
  "evaluated_file": "candidate_strategy.py",
  "generated_artifacts": [],
  "conversation_files": ["ai_conversations/session-01.md"],
  "redactions": [],
  "declaration": "He revisado y asumo la responsabilidad de la entrega final."
}
```

No incluyas conversaciones personales ajenas a la prueba. Sustituye secretos o
datos personales por `[REDACTED: motivo]` y registra las redacciones en el inventario.
Conserva las evidencias hasta que finalice la evaluación.

## Posible conversación técnica

Podríamos solicitar una conversación técnica de unos 20 minutos para comentar
tus decisiones o explorar una variación de parámetros, con IA disponible.
**No es una fase obligatoria ni está garantizado que se realice.**

## Evaluación y selección

Las entregas que superen los requisitos obligatorios se ordenan por una nota
global: 75 % de resultados técnicos, 15 % de explicación de la estrategia y
10 % de colaboración con IA, con las deducciones publicadas cuando correspondan.
Las siete características técnicas aportan hasta 20 puntos cada una y se
comparan por percentiles entre las entregas admitidas. Tener el mejor resultado
en una característica solo puede ayudar a desempatar; no otorga selección directa.

BBVA puede revisar el procedimiento de resolución y retirar candidaturas por
falta de revisión humana efectiva, contenido generado sin verificar o conductas
abusivas, con las evidencias y garantías descritas en
[la evaluación](EVALUACION.md). También puede incluir o mantener candidaturas
por méritos académicos, entrevistas previas o experiencia relevante. Estas
decisiones se registran separadamente de la nota técnica.
