# Preguntas frecuentes

Este archivo se actualiza con las consultas que llegan a `bbva-hackaton-2026.group@bbva.com`. La versión vigente es la
del repositorio del reto.

## Repositorio y entrega

**¿Puedo hacer un fork del repositorio del reto?**
No. Crea un repositorio privado propio y sube allí el contenido, como indica el [manual](README.md).

**¿Qué rama se evalúa?**
La rama `main` de tu repositorio, tal como esté subida (`git push`) a las 07:00 (hora de Lima) del martes 20 de
octubre. El cierre es el lunes 19 de octubre a las 22:00 (hora de Lima).

**¿Cómo doy acceso a mi repositorio?**
En tu repositorio, en Settings → Collaborators, añade la cuenta `bbvaHackaton2026`. La invitación caduca a los 7 días si
no se acepta; si caduca, vuelve a enviarla.

**¿Dónde va la carpeta `submission/`?**
En la raíz de tu repositorio, en la rama `main`. Su contenido se describe en [`PRUEBA_TECNICA.md`](PRUEBA_TECNICA.md).

**¿Qué `candidate_strategy.py` se evalúa: el de la raíz o el de `submission/`?**
El de `submission/`. `run.py` y las pruebas usan el de la raíz: antes del cierre, copia la versión final a
`submission/candidate_strategy.py`. Para probar esa copia: `python run.py --strategy submission/candidate_strategy.py`.

**¿Qué pongo en `candidate_name` y `candidate` de `submission_manifest.json`?**
En `candidate_name`, tu nombre completo; en `candidate`, el correo con el que te inscribiste en Genoma.

**Si no tengo scripts adicionales, ¿qué pongo en `generated_artifacts/`?**
Un archivo `.gitkeep`, declarado en `submission_manifest.json`.

**¿Tengo que entregar las conversaciones con IA?**
Sí: completas, incluidos los intentos fallidos, en `submission/ai_conversations/`.

## Ejecución

**¿Qué versión de Python necesito?**
Python 3.11 o superior. El equipo de evaluación se describe en [`EVALUACION.md`](EVALUACION.md).

**¿Puedo usar bibliotecas externas, como numpy o pandas?**
No. El evaluador incorpora solo `candidate_strategy.py` y no instala dependencias: usa la biblioteca estándar de Python.
Para comprobarlo en tu equipo, ejecuta `python -S run.py`: así Python no carga las bibliotecas instaladas.

**¿Puedo crear procesos o hilos, o usar la red?**
No. Lo prohíben las reglas de ejecución de [`REGLAS_PUBLICAS.md`](REGLAS_PUBLICAS.md).

**`python run.py` termina con `INTEGRITY_ERROR`. ¿Qué reviso?**
Algún archivo protegido cambió. Puedes modificar `candidate_strategy.py` y añadir archivos nuevos, por ejemplo pruebas
en `tests/`, pero no modificar los archivos existentes. Restáuralos a su versión original o vuelve a clonar el
repositorio del reto.

**La prueba `tests/test_candidate_strategy_smoke.py` falla con mi estrategia. ¿Afecta a la evaluación?**
No. Es una prueba de ejemplo: comprueba el comportamiento de la estrategia inicial y no se ejecuta en la evaluación. Al
empezar debe pasar, porque así compruebas que tu entorno funciona. Si después tu estrategia cambia ese comportamiento
dentro de las reglas, es normal que falle. Para tus propias pruebas, crea archivos nuevos en `tests/` (por ejemplo,
`tests/test_mi_estrategia.py`; puedes partir de una copia de la prueba de ejemplo) sin modificar los existentes, e
inclúyelos en `submission/generated_artifacts/` al entregar.

**¿La simulación termina cuando ya no quedan tarjetas pendientes?**
No. El motor llama a `on_dispatch_tick` cada 15 minutos hasta el corte (el mayor deadline más siete días naturales),
aunque no queden tarjetas pendientes. En este punto, `REGLAS_PUBLICAS.md` describe un fin anticipado que el motor
publicado no aplica. La evaluación usa este mismo motor, sin cambios, para todas las entregas.

**¿Los ejemplos públicos puntúan?**
No. `run.py` (5.000 tarjetas) y `run_150k.py` (150.000 tarjetas) son casos de desarrollo.

## Consultas

**¿Dónde envío una pregunta?**
A `bbva-hackaton-2026.group@bbva.com`. Las respuestas útiles para todos se añaden a este archivo.

**¿Dónde reporto un fallo del entorno?**
En `bbva-hackaton-2026.group@bbva.com`, con los pasos para reproducirlo y el error que obtienes.
