# TODO

## App
- [ ] En la hoja, no escribir el bitrate: `Downloaded (128 kbps)` -> `Downloaded`. Mantener
  `Downloaded (verify)`. El bitrate solo en el log. (`downloader.py`: no anadir la nota de kbps;
  o `sheets.py`: filtrarla antes de escribir.)
- [ ] (parcial: ya se marca `Downloaded (verify)` en la hoja) Fase 2: resumen automatico al acabar con las canciones a revisar. No necesita IA: guardar por
  cancion durante la ejecucion si acabo en Failed, si el candidato tenia puntuacion floja o
  bitrate desconocido, si vino de FLAC convertido, si salio de la busqueda por album/artista en
  vez de la exacta.

## Log
- [ ] Rework del log: una linea por cancion con tres partes: lo que se busca (artista - titulo),
  el estado (se sobreescribe: Searching (Exact)... / Queued / Downloading 45% / Converting...) y el
  resultado final (fichero elegido, duracion, bitrate, o Failed). El detalle actual (busquedas,
  Rejected, candidatos) pasa a un modo "verbose" o a un fichero de log, no a la pantalla.
  Encaja con las descargas en paralelo: cada hilo actualiza su propia linea.
  Implementacion: en Tk, cada cancion es una fila (Label o linea del Text con un tag/mark), y
  print() deja de ser el canal; `download_track` recibe un callback `status(msg)`.

## Rendimiento
- [ ] Descargas en paralelo: en `process_sheet`, repartir las filas entre N hilos
  (`ThreadPoolExecutor`, `WORKERS = 3` configurable); cada hilo hace el ciclo completo de su
  cancion. `download_track` no comparte estado. Log: acumular por cancion y volcar al acabar (o
  prefijo por cancion). Cuidado con slskd (3 busquedas simultaneas max) y con los usuarios con
  pocos slots (cola). Hacer despues de los dos puntos de scoring pendientes.

## Scoring
- [ ] Modo sin puerto (wifi ajeno, sin 50300 abierto): priorizar usuarios con puerto abierto
  (campo de la respuesta de slskd) para no gastar la cola de 45 s en los que nunca conectan.
- [ ] Espera larga para candidatos buenos en cola antes del ultimo recurso: NuagistTurtleize tiene
  FLAC de casi todo pero siempre deja en cola (45 s y fuera) y se acaba bajando un 128. Antes de
  pasar a `Last resort`, reintentar los candidatos de calidad que quedaron en cola con QUEUE_WAIT
  largo (3 min).
- [ ] Memoria de usuarios: recordar durante la ejecucion (y entre ejecuciones, en un json en
  APP_DIR) de que usuarios se ha descargado bien y cuales han fallado o rechazado. En el
  scoring, bonus a los buenos y penalizacion a los malos, para que un usuario que ya ha
  servido (ej. TauAs) salga antes que uno que ya ha fallado (ej. profet) aunque el fichero
  puntue igual.

## Mas adelante
- [ ] OAuth `drive.file` + Google Picker para que otros usuarios puedan usarlo sin service account.
- [ ] Importacion de Discogs desde la app (sustituye al Apps Script).
