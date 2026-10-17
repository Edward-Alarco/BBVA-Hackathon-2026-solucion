# Reglas de negocio y referencia del simulador

Reglas de negocio 0.4.0.
Este contrato define el comportamiento observable, sin prescribir una estrategia.
`interfaces.py` define firmas y tipos; los datos y contextos del escenario
contienen los valores efectivos. Un caso privado no puede añadir obligaciones.

## El servicio en pocas palabras

El banco recibe solicitudes de entrega de tarjetas. Cada tarjeta tiene un
producto, un destino, una zona y un plazo. Tu estrategia decide cuándo
despacharla y con qué transportista.

- **Plazos:** cada producto tiene un plazo y calendario. El motor facilita
  la fecha y hora límite de cada tarjeta.
- **Transportistas:** tienen zonas de cobertura, capacidades, tarifas, horarios
  y una flota limitada. Cada vehículo atiende un lote a la vez.
- **Lotes:** las tarjetas deben compartir destino, zona y número de intento,
  sin superar la capacidad del transportista.
- **Espera:** puedes agrupar durante 45 minutos. Después, si hay un transportista
  compatible y disponible, mantener la tarjeta pendiente cuenta como infracción.
- **Reintentos:** un fallo permite otro intento 24 horas después; el tercer
  fallo devuelve la tarjeta a custodia. El plazo original no se amplía.
- **Costes:** se suman despachos, mejoras y penalizaciones. La referencia de
  coste orienta la comparación, pero no es un límite de gasto.
- **Satisfacción del cliente:** depende del tiempo de entrega y de las opiniones
  simuladas de los receptores, combinadas con distintos pesos.
- **Mejoras:** cuando el escenario lo permite, puedes contratar temporalmente
  más vehículos, mayor velocidad o mayor capacidad en los cortes mensuales.

El detalle siguiente fija las reglas exactas del motor. Consúltalo por tema
durante la implementación.

## Vocabulario del código

| Término | Significado |
|---|---|
| SLA / `sla_deadline` | Plazo de servicio / fecha y hora límite para entregar. |
| RCP / `rcp` | Indicador de satisfacción del cliente; conserva este nombre en el código y el informe. |
| Carrier | Transportista. |
| Shipment | Envío de una tarjeta. |
| Batch | Lote de tarjetas enviado en un mismo viaje. |
| Cluster / `delivery_cluster_id` | Identificador de un mismo destino de entrega. |
| Hook / callback | Función que el motor llama cuando ocurre un evento. |
| Tick | Oportunidad para decidir despachos, cada 15 minutos simulados. |
| Snapshot | Vista del estado del servicio en un instante. |
| ETA | Fecha y hora prevista de llegada. |
| Deadline | Fecha y hora límite de entrega. |
| Cutoff | Momento en que termina la simulación aunque queden envíos pendientes. |
| Drenaje | Periodo final sin nuevas tarjetas, para resolver las pendientes. |
| Upgrade | Mejora temporal de un transportista. |
| bps | Puntos básicos: 100 equivalen al 1 %; 10.000, al 100 %. |
| RSS | Memoria del proceso residente en RAM; se registra su valor máximo. |

## Referencia para programar

## 1. Datos y unidades

Los envíos se notifican en orden de `(available_at, shipment_id)`; sus IDs son
únicos. Productos: `VIP_BLACK`, `BUSINESS`, `SME`, `STANDARD`. Zonas:
`URBANA`, `SUBURBANA`, `RURAL`, `REMOTA`. Los IDs de envío, destino y
transportista son etiquetas ASCII sin significado contractual.

Los inputs se validan antes de ejecutar: un escenario inválido no puntúa.
El CSV UTF-8 contiene
`shipment_id,available_at,product,zone,delivery_cluster_id,is_metal`;
los booleanos son `true/false` y las fechas tienen offset y precisión de segundos.
El calendario publica fechas festivas locales únicas.

Tiempo natural en segundos, distancia en km y dinero en céntimos enteros.
`10.000 bps = 100 %`. Zona local: `America/Lima`; ventanas `[apertura,cierre)`.
Para valores no negativos, HALF_UP significa redondear al más próximo con
empates hacia arriba; `ceil` redondea hacia arriba y `floor` hacia abajo.

La demanda, el catálogo (4–6 carriers), sus nombres, orden, precios, capacidades,
velocidades, disponibilidad y tasas, los festivos y los parámetros agregados de
RCP pueden variar. Los rangos declarados figuran en `rules.toml`; los valores
efectivos están en los inputs y vistas públicas. Solo permanecen ocultas las
realizaciones aleatorias y las características individuales de opinión.

## 2. Ejecución e interfaces

Los cinco hooks son `on_shipments_available`, `on_dispatch_tick`,
`on_delivery_succeeded`, `on_delivery_failed` y `on_monthly_planning`.
El mensual devuelve una tupla de decisiones; los demás, `None`.
Excepciones no capturadas o retornos inválidos terminan en `STRATEGY_ERROR`.
Para detectar bloqueos, el supervisor mantiene una espera máxima de 30 segundos
por llamada. Es tiempo real de espera, no una cuota de CPU.

La admisión dura 90 días, excluido el extremo final. Hay ticks cada 15 minutos
anclados al inicio, mientras exista trabajo. Los cortes de planificación son
los días relativos 0, 30 y 60, con índices 0, 1 y 2. Las llegadas simultáneas se
dividen en bloques de hasta 512; todos se notifican antes del tick.

En un mismo instante se procesan, en este orden: retornos de flota, habilitación
de reintentos y expiraciones; resultados de entrega; planificación; llegadas;
tick; auditoría de retención. Los resultados se ordenan por
`(batch_id, shipment_id)` y actualizan el estado antes del callback.

No hay llegadas durante el drenaje. Termina cuando todos los envíos son
terminales y no quedan resultados pendientes, o al alcanzar el mayor deadline
más siete días naturales. Sin envíos, termina al cierre de admisión. En el cutoff
se procesan primero retornos y entregas previstos exactamente allí; después,
los restantes pasan a `UNRESOLVED`, sin nuevos despachos.

Las vistas son inmutables y conservan el instante de emisión.
`carrier_service.snapshot()` obtiene una vista actualizada.
`dispatch_batch(carrier_id, shipment_ids)` es síncrono y puede invocarse desde
cualquier hook: sus eventos no interrumpen el callback. Las llamadas sucesivas
ven los efectos de las anteriores. Solo se permite usar el servicio durante
callbacks. Los despachos dentro del hook mensual preceden a los upgrades
devueltos; las llegadas y el tick posteriores ya ven las mejoras aceptadas.

## 3. Plazos de entrega (SLA)

| Producto | Duración | Reloj |
|---|---:|---|
| VIP_BLACK | 1.440 min | Continuo |
| BUSINESS | 2.880 min | L–V, 08:00–17:00 |
| SME | 2.880 min | L–S, 08:00–20:00 |
| STANDARD | 4.320 min | L–V, 09:00–18:00 |

Los relojes hábiles excluyen festivos y tiempo fuera de ventana; los días ISO
van de lunes=1 a domingo=7. El motor proporciona `sla_deadline`: el primer
instante que completa la duración desde `available_at`. Un deadline que cae
exactamente al cierre no se desplaza.

Cumple solo una entrega con `delivered_at <= sla_deadline`. Devoluciones y
no resueltos incumplen. Lotes, fallos y reintentos no modifican el deadline.

## 4. Estados y resultados

`READY → IN_TRANSIT → DELIVERED`, o, tras fallo,
`WAITING_RETRY → READY`. El alta tiene intento 1, `ready_at=available_at` y
capacidades requeridas vacías. Una aceptación cambia todos los miembros del lote
a `IN_TRANSIT`.

Tras fallar los intentos 1 o 2, el siguiente se habilita 24 horas naturales
después del resultado. El callback incluye el siguiente `attempt_number` y
su `ready_at/retry_eligible_at`; el `attempt_number` del resultado identifica
el intento que terminó. No se emite una nueva llegada al habilitar el retry.
El instante exacto de habilitación admite despacho.

El tercer fallo termina en `RETURNED_TO_VAULT`. El cutoff produce
`UNRESOLVED`. Ambos cobran una penalización de 2.000 céntimos por envío,
una sola vez. Los tres estados terminales son irreversibles.
Los resultados exitosos tienen `terminal=true` y `failure_reason=None`.

`INACCESSIBLE_ROUTE` añade el requisito persistente `HARD_ACCESS`.
Los demás fallos no cambian capacidades. `OPERATIONAL_DELAY` es un intento
fallido en la ETA, sin demora adicional.

## 5. Despacho y retención

Un lote contiene de 1 a la capacidad efectiva del carrier y comparte
`delivery_cluster_id`, zona y número de intento. El cluster representa un
destino único; no hay rutas multiparada. El carrier debe operar, cubrir
exactamente la zona, satisfacer todas las capacidades y tener una unidad libre.

La aceptación es atómica: ocupa una unidad, cobra y fija el viaje para todo el
lote. El receipt incluye IDs ordenados, coste, batch ID y ETA, sin revelar éxito.
Los IDs se ordenan lexicográficamente: el orden de la solicitud no altera el
resultado. Solo una aceptación asigna el siguiente ID `B-000000001`, etc.

Un rechazo no cambia estado, flota, coste, intento ni aleatoriedad. Su receipt
tiene coste cero, batch ID y ETA nulos. Devuelve la primera causa aplicable:

```text
UNKNOWN_CARRIER, EMPTY_BATCH, DUPLICATE_SHIPMENT, UNKNOWN_SHIPMENT,
TERMINAL_SHIPMENT, SHIPMENT_NOT_READY, MIXED_DELIVERY_CLUSTER, MIXED_ZONE,
MIXED_ATTEMPT_NUMBER, ZONE_UNSUPPORTED, CAPABILITY_UNSUPPORTED,
BATCH_CAPACITY_EXCEEDED, OUTSIDE_OPERATING_WINDOW, NO_AVAILABLE_UNIT
```

Un envío en tránsito no está listo y no puede pertenecer a otro lote activo.

Cada entrada en READY permite 45 minutos naturales de retención. Se audita
después del primer tick que alcanza `ready_at + 45 min`. Si queda pendiente
y un carrier operativo, compatible y con unidad libre podía aceptarlo
individualmente, se registra una infracción. Un intento inválido no la evita.
Sin capacidad factible, la auditoría se pospone a ticks posteriores. Se cuenta
una infracción como máximo por periodo READY; no cambia estado ni coste,
pero debe ser cero para superar la evaluación. El precio no afecta factibilidad.

## 6. Flota y transporte

Los carriers operan 24 horas salvo restricciones de domingos y festivos; si
coinciden, deben permitir ambos. Se comprueba al aceptar: un cierre posterior
no detiene el viaje. Cada unidad realiza un lote simultáneo.

`ida_min = ceil(distancia_km*60*10.000 / (speed_kmh*speed_multiplier_bps))`.

La ETA es despacho + pickup + ida; el retorno de unidad es ETA + ida.
Las distancias urbana/suburbana/rural/remota son 12/35/80/150 km.
La unidad vuelve a estar disponible en el instante exacto del retorno.
Precio, velocidad, capacidad e intento quedan fijados al aceptar; el lote
comparte ETA, pero sus miembros pueden tener resultados diferentes.

El snapshot expone capacidad y flota efectivas, velocidad base y multiplicador.
`next_available_at` es ahora si existe unidad libre, o el menor retorno de
una reutilizable. Los upgrades activos se agregan por tipo.

## 7. Costes y mejoras

```text
linehaul = base_fee_cents + recargo_zona
ajustado = HALF_UP(linehaul * factor_intento * factor_noche * factor_calendario
                  / 10.000³)
coste_lote = ajustado + 120*(tarjetas-1) + 450*tarjetas_metálicas
```

Factores de intento: 10.000, 5.000, 10.000 bps. Noche: [20:00,06:00).
El multiplicador de calendario se aplica una vez si es domingo o festivo.
Los factores de noche/calendario son los del carrier. Se redondea una sola vez,
antes de extras; los extras no reciben factores. Se cobra al aceptar, sin
reembolso por fallo. `current_time_multiplier_bps` redondea noche×calendario
a un bps; la fórmula anterior determina el cargo exacto.

Gasto total = despachos + mejoras + penalizaciones.
La referencia de coste y su contingencia del 110 % son informativas:
superarlas no bloquea operaciones ni descalifica. Los indicadores de exceso
usan `max(0,gasto-umbral)`; sus flags solo se activan al superar el umbral,
no al igualarlo. La contingencia monetaria se calcula con `floor`.

Cuando el escenario habilita mejoras, el hook mensual puede solicitar:

| Tipo | Coste | Efecto | Máximo por carrier/periodo |
|---|---:|---|---:|
| EXTRA_UNIT | 40.000 | Una unidad adicional | 3 |
| SPEED_SHIFT | 60.000 | Velocidad ×1,25 | 1 |
| EXPANDED_CAPACITY | 35.000 | Capacidad floor(base×1,5) | 1 |

Se admiten solo cantidades enteras positivas; las dos últimas, únicamente 1.
Las decisiones se procesan en orden, atómicamente por cantidad; las aceptadas
consumen el límite y una rechazada no impide las siguientes. Precedencia:
`UNKNOWN_CARRIER, UNKNOWN_UPGRADE, UNSUPPORTED_UPGRADE, INVALID_QUANTITY,
PER_PERIOD_LIMIT_EXCEEDED`.

Las mejoras rigen tras el callback hasta el siguiente corte; las del periodo 2,
hasta el cierre. Las anteriores expiran antes de la planificación. Una unidad
extra ocupada al expirar termina su viaje en estado `RETIRING` y se retira,
sin prórroga; renovarla crea capacidad nueva. Los viajes aceptados no cambian.

## 8. Fallos

Por envío e intento se evalúan ruta inaccesible, ausencia y fallo operativo,
en ese orden; gana la primera causa activada. Si ninguna ocurre, hay entrega.
Las probabilidades en bps son:

- Ruta: cero con HARD_ACCESS; en otro caso, la tasa de la zona.
- Ausencia: tasa del intento + modificador de zona.
- Operación: tasa del carrier + modificadores de domingo y festivo aplicables.

Las tasas se limitan a [0,10.000]; en un domingo festivo se suman ambos
modificadores operativos. Los contextos publican estos parámetros.
Los sorteos por causa usan claves separadas; dependen de envío e intento y,
salvo ausencia, también del carrier. No dependen de la estrategia, hora o lote.
Solo los intentos aceptados se resuelven, en su ETA. Rechazos no cambian el azar.

La tasa de éxito observada del snapshot usa los últimos 200 resultados por
carrier, ordenados por `(occurred_at,batch_id,shipment_id)`, y redondea
`éxitos*10.000/n` con HALF_UP; sin observaciones es nula.

## 9. Satisfacción del cliente (RCP en el código)

Los VIP forman una audiencia propia. Entre no VIP existe una proporción
influencer publicada. Audiencia y expectativa individual permanecen ocultas
y son estables por envío entre estrategias; no se notifican opiniones durante
la simulación.

Sea `q` la fracción del SLA consumida hasta entregar: tiempo natural para VIP,
tiempo hábil para el resto. No se limita a 1. El umbral individual `x` se
sortea uniformemente en puntos básicos, con extremos incluidos, dentro del
rango publicado por producto.

| Condición | Valoración antes de HALF_UP al entero |
|---|---|
| q ≤ x | 10 |
| x < q ≤ 1 | 10 − 4*(q−x)/(1−x) |
| 1 < q ≤ 1,5 | 6 − 4*(q−1)/0,5 |
| q > 1,5, entregado | 2 |
| No entregado | 1, opinión obligatoria |

Una entrega posterior al deadline puede conservar q=1 si el retraso ocurre
fuera del horario hábil: incumple SLA aunque el rating siga esta curva.

Para entregados, la probabilidad de opinar es
`clamp(base + HALF_UP(uplift*(10-rating)/9),0,10.000)`.
Bases, incrementos y pesos por audiencia están en `RcpPolicy` y `rules.toml`.
El sorteo de opinión es común entre estrategias; empeorar la valoración puede
aumentar la respuesta, sin cambiar la identidad del receptor.

Satisfacción del cliente (RCP) = suma(valoración×peso) / suma(pesos), sobre opiniones emitidas.
Se informa también media simple y desgloses por audiencia sin IDs.
Sin opiniones, el score es nulo y el escenario no sirve para puntuar.

## 10. Informe y restricciones

`performance_report.schema.json` describe el informe que escribe el motor.
En ejecuciones completas, entregados + devueltos + no resueltos = admitidos.
Los intentos cuentan tarjetas, no lotes. Tasa de fallo de intento =
fallidos/aceptados; fallo de entrega = (devueltos+no resueltos)/admitidos;
incumplimiento SLA = (tardíos+devueltos+no resueltos)/admitidos.

El tiempo medio incluye solo entregados, desde disponibilidad hasta entrega
en tiempo natural. Se calcula en segundos y se expresa en minutos. Percentiles:
nearest-rank sobre segundos, índice `ceil(p*n)-1`; p95 y máximo se redondean
a minutos enteros. Media y RCP: tres decimales; tasas: seis, siempre HALF_UP.
Denominadores cero producen nulo, salvo diagnósticos definidos como cero.

La eficiencia de lotes es `1-lotes/intentos_aceptados` (cero sin intentos);
el tamaño medio es intentos aceptados/lotes. Son diagnósticos.
El supervisor mide el tiempo real de CPU y el pico de memoria del proceso
candidato. Ambos se evalúan; no se fija un tope de RAM ni una cuota de CPU.
Estas mediciones no son tiempos simulados.

Un fin anormal conserva resultados parciales y cuenta administrativamente los
pendientes como no resueltos, sin callbacks, penalizaciones ni opiniones
artificiales. Esos resultados no puntúan. Mismos inputs, estrategia y
realizaciones producen el mismo informe funcional, salvo recursos y metadata.

Solo se incorpora el archivo candidato. No debe modificar contratos protegidos,
abrir datasets, escribir el informe, acceder al estado privado del motor,
crear procesos/hilos ni usar red. Puede conservar estado entre las llamadas de un mismo escenario. No hay aprendizaje entre escenarios, cancelaciones, inventario,
geocoding, tráfico ni acceso a otros candidatos.
