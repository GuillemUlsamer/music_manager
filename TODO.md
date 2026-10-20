# TODO

## Rendimiento
- [ ] Descargas en paralelo: en `process_sheet`, repartir las filas entre N hilos
  (`ThreadPoolExecutor`, `WORKERS = 3` configurable); cada hilo hace el ciclo completo de su
  cancion. `download_track` no comparte estado. Log: acumular por cancion y volcar al acabar (o
  prefijo por cancion). Cuidado con slskd (3 busquedas simultaneas max) y con los usuarios con
  pocos slots (cola). Hacer despues de los dos puntos de scoring pendientes.


## Mas adelante
- [ ] OAuth `drive.file` + Google Picker para que otros usuarios puedan usarlo sin service account.
- [ ] Importacion de Discogs desde la app (sustituye al Apps Script).
