# TODO

## Limpieza
- [ ] Borrar `music_manager_v2.py`, `music_manager.py` (`diag_search.py` ya borrado).
- [ ] Quitar `yt-dlp` de `requirements.txt`.
- [ ] Commit y push.

## Release automatica
- [ ] `.github/workflows/release.yml`: con un tag `v2.x.x`, construir con PyInstaller + Inno Setup en runner Windows y subir `MusicManagerSetup-<ver>.exe` a GitHub Releases.
- [ ] El instalador nunca se commitea; va a Releases.

## README
- [ ] Reescribir para v2 (Soulseek/slskd, setup automatico, credentials.json). Aun habla de YouTube/yt-dlp.

## App
- [ ] Boton de ajustes en la app ya configurada: reutilizar la pantalla de setup
  (usuario/password Soulseek, carpeta de musica, carpeta compartida, credentials.json),
  reescribir `config.json` y `slskd.yml`, reiniciar slskd si estaba abierto.
- [ ] Boton "Copy output" al terminar: copia el log entero al portapapeles para pegarlo en una IA.
  `self.root.clipboard_append(self.log_box.get("1.0", tk.END))`
- [ ] Fase 2: resumen automatico al acabar con las canciones a revisar. No necesita IA: guardar por
  cancion durante la ejecucion si acabo en Failed, si el candidato tenia puntuacion floja o
  bitrate desconocido, si vino de FLAC convertido, si salio de la busqueda por album/artista en
  vez de la exacta.

## Robustez de red
- [ ] `requests.Session()` en `slskd_client.py` (keep-alive) para no agotar sockets (WinError 10055).
- [ ] En `downloader.py`, `except requests.ConnectionError: raise SystemExit(...)` antes del
  `RequestException`, para cortar la ejecucion si slskd cae en vez de marcar todo como Failed.
- [ ] `distributed_network.disabled: true` en la plantilla de `slskd.yml` (`bootstrap.write_slskd_yml`).

## Scoring
- [ ] Timeout de descarga por inactividad, no por tiempo total: en `slskd_download` reiniciar el
  contador cada vez que cambia `bytesTransferred`; solo rendirse tras DOWNLOAD_WAIT_SEC sin
  progreso (en wifi lento se cortaban descargas vivas con "Transfer ended: InProgress").
- [ ] `require_title` en `score_candidates`: en las busquedas sin artista (Title, Artist, Album)
  exigir que `normalize_for_match(loose_title(title))` este contenido en el nombre del fichero
  normalizado. El 60 % de palabras en comun deja pasar basura con titulos de palabras corrientes
  (ej. "No Hardcore No Life" -> "Life In The Air (Hardcore Heaven Mix)"). En Exact/Loose se
  mantiene el filtro laxo porque Soulseek ya filtra por artista.
- [x] Modo diagnostico: imprimir por que se descarta cada fichero (bitrate, duracion, titulo).
- [x] Aceptar 192 kbps como ultimo recurso (penalizado, no descartado).
- [ ] Modo sin puerto (wifi ajeno, sin 50300 abierto): priorizar usuarios con puerto abierto
  (campo de la respuesta de slskd) para no gastar la cola de 45 s en los que nunca conectan.
- [ ] Memoria de usuarios: recordar durante la ejecucion (y entre ejecuciones, en un json en
  APP_DIR) de que usuarios se ha descargado bien y cuales han fallado o rechazado. En el
  scoring, bonus a los buenos y penalizacion a los malos, para que un usuario que ya ha
  servido (ej. TauAs) salga antes que uno que ya ha fallado (ej. profet) aunque el fichero
  puntue igual.

## Mas adelante
- [ ] OAuth `drive.file` + Google Picker para que otros usuarios puedan usarlo sin service account.
- [ ] Importacion de Discogs desde la app (sustituye al Apps Script).
