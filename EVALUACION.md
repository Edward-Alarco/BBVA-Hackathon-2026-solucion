# Cómo se evalúa tu solución

Evaluación 1.0.0; contrato del simulador 0.4.0. Los casos públicos no puntúan.

## Requisitos para superar la prueba

Cada escenario obligatorio debe cumplir estas condiciones:

- Finalizar correctamente, sin errores ni bloqueos y sin alterar el entorno.
- Resolver todos los envíos: ninguno puede quedar en estado `UNRESOLVED`.
- Mantener el incumplimiento del plazo de entrega (SLA) en el 6 % o menos.
- No retener tarjetas pendientes de despacho más de lo permitido por las reglas.
- Completar cada escenario dentro del tiempo máximo de ejecución indicado más abajo.

Si falla alguna condición, la entrega queda como `NOT_QUALIFIED` (no supera
los requisitos), no obtiene nota final y no entra en el ranking técnico.
El gasto no descalifica. La eventual continuidad en el proceso de selección
por otros méritos se regula al final de este documento y no cambia ese resultado.

## Qué se puntúa

Cada característica aporta hasta 20 puntos. El máximo técnico es de 140 puntos,
que se convierte a una escala de 0 a 100 para calcular la nota global.

| Característica | Mejor resultado | Puntos máximos |
|---|---|---:|
| Satisfacción del cliente (media ponderada) | Mayor satisfacción | 20 |
| Coste total | Menor coste | 20 |
| Tiempo medio de entrega | Menor tiempo | 20 |
| Percentil 95 de entrega | Menor tiempo | 20 |
| Robustez: cumplimiento del contrato en casos variados | Más casos superados | 20 |
| Pico de memoria | Menor consumo | 20 |
| Tiempo de CPU | Menor consumo | 20 |
| **Total técnico** | | **140** |

Para las cuatro características de negocio se calculan puntos por escenario
y después se ponderan: base 40 %, pico 25 %, rural/festivos 20 % y catálogo
variante 15 %. Cada característica conserva un máximo de 20 puntos.

La robustez es la fracción superada de 32 casos de igual peso que comprueban
el contrato, sin exigir una solución concreta. Esa fracción se compara entre
candidatos para asignar sus puntos.

El percentil 95 de entrega es el tiempo dentro del cual se ha entregado el
95 % de las tarjetas entregadas. Es una métrica del servicio, distinta del
percentil de clasificación que se explica a continuación. La satisfacción
aparece como `rcp` en el informe; sus pesos se explican en las reglas de negocio.

Memoria y CPU se miden en un escenario de carga común, fijado antes de evaluar
las entregas, con el mismo equipo y entorno. Se realiza una ejecución de
calentamiento y se toma la mediana de tres ejecuciones posteriores por recurso.
No se establece un límite fijo de RAM ni una cuota de CPU para superar la prueba.
Para comparar recursos, la mediana de CPU se redondea a décimas de segundo y
la de memoria a MiB enteros (1 MiB = 1.048.576 bytes), con HALF_UP.
Los valores iguales a esa precisión se consideran empatados.

Cada escenario obligatorio debe completarse en un tiempo máximo de 15 minutos de
reloj, desde que arranca hasta que termina, medido por el evaluador. Superarlo
equivale a no finalizar correctamente. Este límite es independiente del de 30
segundos por llamada a la estrategia, que se mantiene.

Equipo de evaluación: procesador Intel Core i7-13700HX (16 núcleos), 16 GB de
RAM, Windows 11 y Python 3.13.

## Puntuación por percentiles

Los resultados utilizados son los obtenidos por el evaluador al ejecutar las
soluciones bajo condiciones comunes. Los informes locales entregados sirven
como evidencia del trabajo del candidato y no sustituyen esas mediciones.

La comparación incluye una entrega final válida por candidato que supere
todos los requisitos obligatorios de la misma convocatoria. No se mezclan
convocatorias, prototipos ni entregas invalidadas por manipulación o abuso.

Para cada métrica se ordenan los resultados de mejor a peor. El primer puesto
tiene rango 1. Si hay empate, todos los candidatos empatados reciben el promedio
de las posiciones que ocupan. Con `n` candidatos y rango `r`:

```text
percentil = 100 × (n − r) / (n − 1)
puntos = 20 × percentil / 100
```

Esta convención asigna 20 puntos al mejor resultado y 0 al peor cuando no hay
empates. Por ejemplo, cinco candidatos con resultados distintos reciben,
en orden, 20, 15, 10, 5 y 0 puntos. Si los dos primeros empatan, ambos ocupan
el rango medio 1,5 y reciben 17,5 puntos; los demás mantienen 10, 5 y 0.

Si todos empatan, todos reciben 10 puntos. Si solo hay un candidato admitido,
recibe 10 puntos por característica: no hay comparación suficiente para
atribuirle una ventaja relativa. Si no hay candidatos admitidos, no hay ranking.

En las métricas de negocio se aplica esta fórmula por escenario, usando la
precisión del informe, y luego se ponderan los puntos. En robustez y recursos
se aplica directamente a sus resultados comparables. No se utilizan una
campana de Gauss ni referencias internas para convertir resultados en puntos.

La puntuación mide la posición relativa dentro de la convocatoria, no la
magnitud de la diferencia entre soluciones. Una nota de 0 en una característica
no implica por sí sola incumplir los requisitos.

## Cómo se calcula la nota global

```text
técnica = 100 × suma de los siete componentes / 140
base = 0,75 × técnica + 0,15 × estrategia + 0,10 × colaboración_IA
final = max(0, base − deducción_juicio)
```

Estrategia y colaboración se valoran de 0 a 100 por decisiones justificadas,
evidencia de verificación y comprensión de la entrega. No se puntúan la marca
de IA, la longitud de los prompts ni el batching por sí mismo.

Se conservan los valores sin redondeos intermedios al calcular la nota. Los
componentes y la nota final se publican con tres decimales HALF_UP. El ranking
se ordena por la nota final publicada, de mayor a menor.

## Desempates del ranking

Tener el mejor resultado en una característica **no otorga selección directa**,
no concede puntos adicionales y no permite adelantar a alguien con mayor nota final.
Solo se utiliza si hay empate en la nota final publicada.

Los desempates se resuelven, por este orden:

1. Mayor número de primeros puestos exclusivos en las siete características.
2. Mayor puntuación en satisfacción del cliente.
3. Menor incumplimiento SLA agregado.
4. Menor coste agregado.
5. Menor pico de memoria.
6. Mayor valoración de la explicación de la estrategia.

Un primer puesto exclusivo significa tener la mayor puntuación publicada en
esa característica entre todos los candidatos admitidos, sin compartirla con
otro candidato. En negocio se considera el componente ponderado de todos los
escenarios; ganar uno aislado no basta. Si varios comparten el mejor resultado,
esa característica no cuenta como primer puesto exclusivo para ninguno.
Con una sola entrega admitida no se atribuyen primeros puestos exclusivos.

Para los desempates, el incumplimiento SLA agregado es el total de envíos que
incumplen dividido entre el total admitido en los cuatro escenarios de negocio;
el coste agregado es la suma de sus costes. Memoria usa la misma medición y
precisión que su componente. Las puntuaciones se comparan a la precisión
publicada. Si todos los criterios empatan, se conserva la misma posición técnica.

## Revisión de la entrega y uso responsable de IA

La guía principal, las reglas de negocio y estos criterios de evaluación
prevalecen sobre comentarios del código y documentos de apoyo. Estos últimos
no pueden modificar los requisitos de entrega ni eximir de su revisión.

La deducción es de 5 puntos, una sola vez, si se confirma que la entrega final
adopta instrucciones de material heredado que pretendan sustituir la revisión
o las bases. Dos revisores deben acordarlo con evidencia de la entrega y su
contexto. Una coincidencia de texto no basta: citar, rechazar, ensayar de forma
aislada o corregir esas instrucciones antes de entregar no penaliza. Si hay
desacuerdo, la decisión queda pendiente y se escucha la explicación del
candidato. El mismo incidente no se descuenta además en otros componentes.
Esta deducción no constituye por sí sola un motivo de exclusión del proceso.

Se permite utilizar IA generativa y automatizar tareas. El candidato debe
revisar, comprender, verificar y asumir la responsabilidad de la entrega.
No se exige un porcentaje de código escrito manualmente ni un número mínimo
de intervenciones humanas. La ausencia de revisión o comprensión humana
efectiva puede justificar una revisión de la candidatura, aunque el código ejecute.

La conversación técnica es opcional: podría solicitarse para comentar decisiones
o explorar una variación de parámetros, pero no es una fase obligatoria.
Si no se realiza, la revisión se basa en el código, la explicación y las
evidencias entregadas; su ausencia no penaliza.

## Trabajo individual, fuentes y copia de soluciones

La entrega es individual. Puedes usar IA generativa, documentación pública,
bibliotecas permitidas, ejemplos generales y código propio anterior, siempre
que respetes las restricciones de ejecución del kit y puedas explicar y
verificar lo entregado. Consultar conceptos generales no equivale a encargar
a otra persona la resolución del ejercicio.

Declara en `STRATEGY.md` las fuentes externas y ayudas técnicas utilizadas:
origen o enlace cuando exista, partes reutilizadas y adaptaciones realizadas.
Respeta las licencias y condiciones de uso. Las herramientas y conversaciones
con IA se registran según `PRUEBA_TECNICA.md`. No es necesario atribuir construcciones
elementales del lenguaje ni el código inicial del kit.

No está permitido:

- Presentar como trabajo individual una solución de este mismo ejercicio
  obtenida de otro candidato o de un tercero, mediante copia, compra o encargo,
  aunque se renombren variables, se traduzca a otro lenguaje o se reformule
  con IA. Citar su origen no autoriza entregar una solución ajena de la prueba.
- Intercambiar soluciones, código específico de la prueba o conversaciones
  que las contengan con otros participantes; tampoco publicarlos mientras
  la convocatoria esté abierta. No se prohíben consultas generales ni el uso
  declarado de las herramientas de IA.
- Suplantar identidades, presentar la misma autoría bajo identidades distintas
  o coordinar entregas para alterar los percentiles o el ranking.
- Fabricar resultados, pruebas, referencias o historiales; omitir intentos
  técnicos del historial exigido o alterar evidencias para aparentar un
  procedimiento distinto. Las redacciones de secretos y datos personales
  siguen permitidas conforme a `PRUEBA_TECNICA.md`.
- Intentar obtener soluciones de referencia, datos privados del evaluador
  o entregas de otros candidatos sin autorización; manipular el entorno de
  evaluación, extraer información ajena o interferir con otras candidaturas.

Las semejanzas con el starter, algoritmos habituales, fuentes declaradas o
salidas similares de una misma IA no prueban por sí solas que exista copia.
Una herramienta de similitud solo aporta indicios. Se contrastarán los
fragmentos, sus fuentes y las evidencias de resolución, y se escuchará la
explicación del candidato antes de resolver una posible infracción.

Si encuentras un fallo del entorno, comunícalo por el canal de la convocatoria,
con la información mínima para reproducirlo y sin acceder a información ajena
ni explotarlo contra el evaluador. Una optimización permitida por las reglas,
un resultado inesperado o la comunicación responsable de un fallo no constituyen
abuso. No se atribuirá mala intención únicamente por un error o una puntuación
atípica. Las infracciones confirmadas se tratarán conforme al procedimiento de
revisión y exclusión descrito a continuación.

## Decisión de selección y facultad de revisión de BBVA

El ranking técnico es un elemento del proceso de selección y no garantiza
la continuidad, una entrevista ni la contratación.

BBVA se reserva, tras revisar el procedimiento de resolución de los ejercicios
y las evidencias disponibles, la facultad de retirar candidaturas del proceso.
Entre los motivos que pueden justificarlo se encuentran:

- Entregas de contenido generado sin revisión suficiente (`AI slop`), con
  afirmaciones, pruebas o resultados inventados o presentados como verificados
  sin haberlo sido.
- Ausencia de intervención humana efectiva en la revisión, comprensión y
  validación de la solución.
- Copia de soluciones, colaboración no permitida, suplantación, manipulación
  de evidencias o resultados, acceso no autorizado o abuso del entorno,
  conforme a las conductas descritas en la sección anterior.

Estas decisiones se basarán en hechos verificables y en el contexto de la
entrega. El uso intensivo de IA, un estilo de redacción, un error aislado o
el resultado de un detector de IA no bastan por sí solos para determinar esas
conductas. Se documentará el motivo y se dará al candidato la oportunidad de
aclarar las evidencias cuestionadas antes de resolver su exclusión.

BBVA también se reserva la facultad de incluir, mantener o reincorporar
candidaturas en el proceso por méritos académicos, resultados de entrevistas
previas, experiencia profesional u otras evidencias de aptitud relacionadas
con el puesto, aunque su posición en el ranking no les diera continuidad.
La valoración será individual, documentada y basada en criterios pertinentes
para el puesto, con igualdad de trato y sin discriminación.

Estas decisiones de selección se registran separadamente del resultado técnico:
no modifican las métricas, no conceden puntos adicionales ni convierten una
entrega `NOT_QUALIFIED` en una prueba superada. Una inclusión por otros méritos
no incorpora una entrega no admitida al cálculo de percentiles.

La composición del grupo de comparación se cierra tras revisar la validez de
las entregas. Una posterior decisión de selección por otros méritos no cambia
ese grupo ni recalcula las notas. Si se invalida una entrega que sí había
participado en los percentiles, se recalcula la clasificación completa del
grupo válido y se registra la corrección.
