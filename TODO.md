# TODO

## Rendimiento
- [ ] Usuarios ocupados: con 3 hilos, dos canciones eligen al mismo usuario (flowersofintelligence)
  mientras el tercero ya le esta descargando, se quedan en cola 45 s y encima le apuntan un `bad`
  en la memoria. Conjunto `BUSY_USERS` (con lock) en `slskd_client`: se anade al empezar una
  descarga y se quita al acabar; en `downloader`, al recorrer candidatos, saltar los ocupados
  (o dejarlos para el final).

## Scoring
- [ ] Remix no pedido: si el titulo no lleva remix/mix/edit y el fichero si, penalizar 30 puntos
  (no descartar) para que gane el original si existe (Gusset Typist, Life & Death).

## Tags
- [ ] El año no sale en el movil: `tag_file` guarda el primer `audio.save()` en ID3v2.4 (`TDRC`)
  y solo la rama de la caratula en 2.3 (`TYER`). Poner `audio.save(v2_version=3)` tambien en el
  primero. Los mp3 ya bajados se arreglan con un script de una vez: `ID3(f).update_to_v23()` +
  `save(v2_version=3)` sobre la carpeta de musica (apuntar en NOTES.md).

## Mas adelante
- [ ] OAuth `drive.file` + Google Picker para que otros usuarios puedan usarlo sin service account.
- [ ] Importacion de Discogs desde la app (sustituye al Apps Script).
