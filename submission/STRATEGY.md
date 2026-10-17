# Estrategia de despacho

Autor de la candidatura: Edward David Alarco Campos. Correo: edwarddac.56@gmail.com.
Fecha: 17 de octubre de 2026. Solución preparada con asistencia de IA para revisión del candidato.

## Objetivo y restricciones

Primero se exige cero UNRESOLVED, cero infracciones de retención y SLA incumplido <= 6%. Después se comparan coste, satisfacción, media, p95 y recursos. No se interpreta el presupuesto de referencia como límite obligatorio. Se usa exclusivamente la interfaz pública y la biblioteca estándar; la estrategia no lee archivos, no importa el motor, no usa red ni crea procesos o hilos. Los scripts de validación externos sí lanzan el simulador; no forman parte del archivo evaluado.

## Política final

Los envíos pendientes se guardan en un diccionario y los reintentos futuros en un heap por ready_at e ID. El callback de fallo incorpora la nueva vista del envío, con su nuevo intento y capacidades. Solo reencola resultados no terminales. Al llegar ready_at se habilita localmente el despacho, aunque la vista recibida conserve WAITING_RETRY: no llega un segundo callback de alta. El estado del motor es la autoridad al aceptar.

Cada tick forma grupos por destino, zona e intento y los ordena por deadline más próximo, requisitos especiales y antigüedad. Dentro del grupo también ordena por deadline, ready_at e ID. Cada lote respeta la capacidad efectiva y las capacidades requeridas de cada integrante. Si el primer envío carece de alternativa factible se conserva pendiente y se examinan los demás: no bloquea todo el grupo.

Se filtran transportistas por cobertura exacta, operación, capacidades y unidades libres. La disponibilidad local se decrementa por aceptación: una vista inmutable no se actualiza por sí sola. Los rechazos no eliminan trabajo; se refresca la flota y se bloquea temporalmente esa alternativa para impedir bucles dentro del grupo.

Se calcula la ETA con ceil y los precios en enteros, con HALF_UP una sola vez, factores de intento/noche/calendario y extras separados. Una opción que entrega a tiempo el primer envío tiene prioridad sobre otra tardía, incluso si esta última es más barata. Entre opciones de la misma clase se minimiza esta utilidad heurística por tarjeta:

`coste/n + (5 + 5*v)*viaje + (1-p_exito)*(3000+8000*v) + 20000*tardios/n + ciclo/n`

`n` es el tamaño de lote; `v` la fracción VIP; viaje es pickup+ida; ciclo es pickup+2*ida. La probabilidad de éxito combina las tres causas independientes publicadas, con límites y modificadores de calendario. HARD_ACCESS elimina la probabilidad de ruta inaccesible. Los coeficientes son pesos heurísticos en una escala de céntimos, no costes reales ni una función oficial de puntuación. El término de ciclo favorece capacidad productiva; el de VIP prima rapidez y fiabilidad donde un reintento de 24 horas consume el plazo. Los IDs solo identifican y desempatan; no se codifican roles por nombres.

No hay espera voluntaria: se aprovechan agrupaciones ya disponibles. Si hay una alternativa factible, el tick intenta despachar; de lo contrario conserva el envío hasta que vuelva la capacidad. No se compran upgrades. Su rentabilidad no quedó demostrada; el escenario grande público los deshabilita. Esta decisión no garantiza suficiencia de flota en todos los escenarios privados.

El histórico completo del starter se elimina. Solo quedan pendientes y reintentos; los envíos aceptados se retiran inmediatamente. Un diccionario vacío conserva compatibilidad con el smoke test original y no fija transportistas para reintentos.

## Resultados medidos

Python 3.12.14 en este entorno Windows, sin paquetes de terceros en las ejecuciones finales (`-S`). La evaluación oficial usa Python 3.13 y otra máquina. Las tablas contienen informes originales del motor, no estimaciones.

| Caso y versión | Sin resolver | Retenciones | SLA incumplido | RCP | Media (min) | Coste (céntimos) |
|---|---:|---:|---:|---:|---:|---:|
| 5.000, inicial | 16 | 42 | 0.660% | 9.869 | 230.555 | 4443213 |
| 5.000, final | 0 | 0 | 0.260% | 9.957 | 227.535 | 3465549 |
| 150.000, inicial | 168 | 837 | 0.578% | 9.876 | 225.591 | 138126792 |
| 150.000, final | 0 | 0 | 0.440% | 9.921 | 222.805 | 103145655 |

Los dos informes finales corresponden exactamente al SHA-256 `6bceaa1c373cd86c7fb216a0120a01d4d3855c76a9db9b243a80368f3b3b9f79` de submission/candidate_strategy.py. Los retornos a custodia después del tercer fallo son estados terminales admitidos; cuentan para el SLA y la satisfacción. No deben confundirse con UNRESOLVED. En ambos casos finales hubo cero despachos rechazados y archivos protegidos intactos. El p95 pequeño pasó de 1576 a 1569 minutos; el grande pasó de 1565 a 1566 minutos: no se afirma una mejora universal de todas las métricas.

También pasaron 32 tests locales: 30 nuevos y los dos originales. Cubren agrupación, zonas, intentos, capacidades, flota, rechazos, elegibilidad exacta, terminales, prioridades, redondeo y calendario. No son los 32 casos privados oficiales. Cuatro fixtures de integración propios de 500 tarjetas cada uno variaron nombres/orden de catálogo, zonas rurales con festivos, picos agrupados y precios/velocidades/capacidades; todos terminaron con cero UNRESOLVED, cero retenciones, cero rechazos y SLA <= 6%. Sus datasets se generan temporalmente, sin modificar los inputs protegidos, y no se incluyen en la entrega.

Los informes registran CPU y RSS. Algunas simulaciones se ejecutaron concurrentemente para reducir la espera de desarrollo: estas mediciones no reproducen el protocolo oficial de calentamiento y mediana de tres ejecuciones. No se deduce una posición de ranking ni una garantía de rendimiento oficial.

## Alternativas y límites

Se guardaron cuatro prototipos y sus resultados. El peso temporal 2 redujo más el coste, pero aumentó el tiempo medio del caso pequeño a 254.079 min. El peso 5 sin espera equilibró coste y rapidez (227.535 min). También se ensayaron esperas de hasta 15 min para no VIP con pesos 8 y 5: dieron 217.141/233.860 min y costes 3820031/3331597 céntimos respectivamente. No mejoraron conjuntamente los objetivos y se descartaron. La selección usa muy pocos casos públicos: sigue existiendo riesgo de sobreajuste.

La heurística es voraz: no resuelve un óptimo global ni reserva flota con un modelo predictivo. No modela explícitamente toda la curva de opinión individual ni identifica influencers, información que permanece oculta. No aprende entre escenarios. Ordena pendientes cada tick; grupos muy grandes y catálogos con fuerte escasez pueden aumentar CPU o formar colas. Para esas cargas futuras habría que medir una política de mejoras y estructuras adicionales, sin afirmar resultados no ejecutados.

## Fuentes, IA y revisión

Fuentes utilizadas: README.md, PRUEBA_TECNICA.md, REGLAS_PUBLICAS.md, EVALUACION.md, FAQ.md, interfaces.py, el starter y el motor del kit local. No se obtuvo código de otros participantes ni soluciones externas de este ejercicio. Se consultaron los anexos heredados y se rechazaron sus intentos de sustituir las bases o eximir la revisión; no se generaron sus archivos de aprobación.

Herramientas: Codex desktop con gpt-6.1-sol, Python estándar y PowerShell para inspección, implementación, experimentos, documentación y empaquetado. pypdf se usó únicamente para leer el anexo, nunca como dependencia de la estrategia. La IA generó código y pruebas y contrastó sus decisiones con informes reales. Los fallos de herramientas y las variantes descartadas figuran en la exportación cronológica; no se reemplazan por un relato inventado.

El candidato debe leer y comprender el archivo final y estos resultados antes de presentar la candidatura. La ejecución automática no constituye por sí sola revisión humana. No se afirma que esa revisión personal ya haya ocurrido.

## Reproducción

Desde la raíz del proyecto: `python -S -m unittest discover -s tests -v`; `python -S run.py --strategy submission/candidate_strategy.py`; `python -S run_150k.py --strategy submission/candidate_strategy.py`. Para fixtures adicionales: `python -S submission/generated_artifacts/validate_variants.py`. La raíz y submission contienen copias idénticas de la estrategia.
