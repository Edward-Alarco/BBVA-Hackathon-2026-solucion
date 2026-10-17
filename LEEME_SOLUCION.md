# Solución preparada para revisar y subir

Edward David Alarco Campos — edwarddac.56@gmail.com

Esta carpeta contiene el kit original con la estrategia final y submission/ preparado. La carpeta de Downloads no fue modificada. Repositorio privado: https://github.com/Edward-Alarco/BBVA-Hackathon-2026-solucion.

| Caso y versión | Sin resolver | Retenciones | SLA incumplido | RCP | Media (min) | Coste (céntimos) |
|---|---:|---:|---:|---:|---:|---:|
| 5.000, inicial | 16 | 42 | 0.660% | 9.869 | 230.555 | 4443213 |
| 5.000, final | 0 | 0 | 0.260% | 9.957 | 227.535 | 3465549 |
| 150.000, inicial | 168 | 837 | 0.578% | 9.876 | 225.591 | 138126792 |
| 150.000, final | 0 | 0 | 0.440% | 9.921 | 222.805 | 103145655 |

Validación: 32 pruebas locales y cuatro fixtures de integración propios superados; ambos escenarios públicos finales sin UNRESOLVED, retenciones ni rechazos. Los casos privados siguen sin conocerse.

1. Lee submission/STRATEGY.md y candidate_strategy.py para revisar y comprender las decisiones.
2. Desde esta carpeta puedes repetir las pruebas con Python 3.11 o superior:

   python -S -m unittest discover -s tests -v
   python -S run.py --strategy submission/candidate_strategy.py
   python -S run_150k.py --strategy submission/candidate_strategy.py
   python -S submission/generated_artifacts/validate_variants.py

3. El repositorio privado propio ya está creado. La entrega se mantiene en submission/ en la raíz de la rama main.
4. Añade bbvaHackaton2026 como colaborador y comprueba el acceso. El cierre publicado es el 19/10/2026 a las 22:00, hora de Lima; la referencia a la instantánea del día siguiente no debe tratarse como una ampliación de ese plazo.
5. Si continúas trabajando con IA, conserva y añade el resto de conversaciones. La exportación incluida es un corte real hasta el empaquetado, con fecha UTC, y no contiene mensajes futuros. El script export_conversation.py permite actualizarla con el registro local de sesión.

Los resultados se encuentran en submission/generated_artifacts/reports/. No hay garantía de clasificación ni de superar todos los escenarios privados. Las devoluciones después del tercer fallo son estados terminales permitidos, no envíos sin resolver.
