# Music Manager & Playlist Downloader

Este proyecto sincroniza una carpeta de música local con una hoja de cálculo de Google Sheets.

Si una canción de tu sheet de google esta marcada, la busca y la descarga de Soulseek (a través de slskd), la convierte a MP3, añade metadatos (ID3 tags) y actualiza el estado en la hoja de cálculo. También gestiona el borrado de archivos si se desmarcan en la lista.

Incluye un script de Google Apps Script (`playlistHelper.gs`) para importar tracklists directamente desde Discogs a la hoja de cálculo. 

## Features
- Sync music library with Google Sheets
- Download tracks from Soulseek automatically (strives for best bitrate)
- Convert to MP3
- Add metadata: artist, title, album (compilation + volume), year, track number and cover art
- Import playlists from Discogs
- Import Discogs lists (multi-release) and create volumes automatically
- Keep a Releases catalog sheet with album, year and cover
- Run from a desktop GUI (`gui.py`) with playlist cards from your Drive, live colored logs and stop button

## Tech Stack
- Python
- Google Sheets API
- slskd (Soulseek client, REST API)
- FFmpeg
- Google Apps Script

## Requisitos Previos

1.  **Cuenta de Soulseek**: usuario y contraseña. Si el usuario no existe, se crea con esa contraseña la 
    primera vez que conecta.
2.  **Cuenta de Servicio de Google**:
    *   Habilita las APIs de Google Sheets y Google Drive en Google Cloud Console.
    *   Crea una cuenta de servicio y descarga la clave JSON.
    *   Guarda el archivo como `credentials.json` donde quieras, la app al arrancar te pide que indiques su ubicacion.
    *   **Importante**: Comparte tu hoja de cálculo con el email de la cuenta de servicio (aparece en el JSON como `client_email`). Modo editor.

## Instalación

1.  Descarga `MusicManagerSetup-x.x.x.exe` de la página de [Releases](https://github.com/GuillemUlsamer/music_manager/releases) y ejecútalo. Crea un acceso directo en el escritorio.
2.  Abre Music Manager. La primera vez aparece la pantalla de configuración:
    *   Usuario y contraseña de Soulseek.
    *   Carpeta de música: donde se guardarán las playlists (una subcarpeta por cada una).
    *   Carpeta a compartir (opcional): lo que ofreces a la red de Soulseek. Compartir algo hace que más usuarios te sirvan.
    *   `credentials.json` de Google.
    *   Puerto de Soulseek (deja 50300 si no sabes qué es).
3.  Pulsa **Set up**. Descarga slskd (el cliente de Soulseek) y lo configura; tarda un minuto. Todo queda en `%LOCALAPPDATA%\MusicManager`, fuera de la carpeta de música.

# aparte
    Si quieres ejecutarlo o modificarlo desde el código:
    git clone https://github.com/GuillemUlsamer/music_manager.git
    cd music_manager
    pip install -r requirements.txt
    python gui.py

    Para generar el instalador (necesitas [Inno Setup 6](https://jrsoftware.org/isdl.php) instalado):
    python -m pip install pyinstaller
    python -m PyInstaller --noconfirm MusicManager.spec
    & "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe" installer.iss

## Configuración de la Hoja de Cálculo

Puedes configurar la hoja manualmente o usar la herramienta automática incluida.

### Método Automático (Recomendado)

Utiliza el script `playlistHelper.gs` para configurar las hojas rápidamente:
1.  Instala el script siguiendo los pasos de la sección **Helper de Discogs** (más abajo).
2.  Recarga la página de Google Sheets.
3.  En el menú superior `music_manager`, selecciona **Set up**.
4.  Introduce el número de volúmenes (hojas) que deseas crear.
5.  El script generará las hojas con los encabezados y anchos de columna correctos automáticamente.

### Estructura de Columnas (Manual)

Si prefieres hacerlo manualmente, la hoja de cálculo debe tener la siguiente estructura de columnas (comenzando por la columna A):

| Columna | Nombre Sugerido | Descripción |
| :--- | :--- | :--- |
| A | Posición | Número de pista |
| B | Artista | Nombre del artista |
| C | Título | Nombre de la canción |
| D | Duración | Duración del track (Formato mm:ss o h:mm:ss) |
| E | Acumulado | (Opcional) |
| F | Descargar | **Checkbox** (TRUE para descargar, FALSE para borrar) |
| G | Estado | Usado por el script para escribir el estado |
| H | Notas | (Opcional) |

### Helper de Discogs

Para facilitar la importación de música:
1.  Abre tu hoja de cálculo en Google Sheets.
2.  Ve a **Extensiones > Apps Script**.
3.  Copia el contenido del archivo `playlistHelper.gs` en el editor.
pon la biblioteca : 1efgoS3Xk_cBVN14eYvrbJngBN8EuUARaOQsqbWSH-eFU6SWdwZR4Tv9N
   
function onOpen() { General_music_manager.onOpen(); }

function showImportDialog() { General_music_manager.showImportDialog(); }

function showListImportDialog() { General_music_manager.showListImportDialog(); }

function showSetupDialog() { General_music_manager.showSetupDialog(); }

function setupSheet(sheetFileName, volNum) { General_music_manager.setupSheet(sheetFileName, volNum); }

function importDiscogsRelease(sheetName, releaseId) { General_music_manager.importDiscogsRelease(sheetName, releaseId); }

function importDiscogsList (listId) { General_music_manager.importDiscogsList(); }

function getOrCreateReleasesSheet(spreadsheet) { General_music_manager.getOrCreateReleasesSheet(spreadsheet); }

function initializeReleasesSheetHeaders(releasesSheet) { General_music_manager.initializeReleasesSheetHeaders(releasesSheet); }

function appendReleaseToCatalog(albumName, releaseYear, coverUrl) { General_music_manager(albumName, releaseYear, coverUrl); }

function durationToSeconds(duration) { General_music_manager.durationToSeconds(duration); }

function secondsToSheetsDuration(seconds) { General_music_manager.secondsToSheetsDuration(seconds); }

5.  Recarga la hoja. Aparecerá un menú personalizado para importar releases de Discogs usando su ID.

Además del import por Release ID, el menú también incluye:
- **Import Discogs List**: importa una lista completa y crea un volumen por release.
- Hoja **Releases**: guarda catálogo de álbumes importados (nombre, año y portada).

## Uso

Abre Music Manager desde el acceso directo. Aparecen tus hojas de Google Drive como tarjetas con su portada. Pulsa una y empieza a descargar las canciones marcadas en la carpeta de música que configuraste, en una subcarpeta `NOMBRE PLAYLIST`.

El log muestra cada búsqueda, el candidato elegido y el estado de la descarga. **Stop** para y cierra slskd. **Copy output** copia el log al portapapeles. **Settings** vuelve a la pantalla de configuración.

Si desmarcas una canción ya descargada, la próxima ejecución la borra de la carpeta.

### Estado en la hoja

En la columna Estado verás `Downloaded`, `Downloaded (verify)` (vino de una búsqueda sin artista, revísala) o `Failed, Do it manually`.

### Argumentos

*   `name`: El nombre exacto de la Google Sheet. También será el nombre de la carpeta donde se guarden los MP3.

### Ejemplo

Si tu hoja se llama "Always hardcore":

```bash
python music_manager.py "Always hardcore"
```

Esto buscará o creará la carpeta `../ALWAYS HARDCORE PLAYLIST` y descargará las canciones marcadas.

depende de desde donde ejecutes el programa, yo tengo una carpeta en mi ordenador con todas mis playlists por ejemplo /Desktop/MUSIC/ 

### Uso con GUI

También puedes ejecutar el gestor con interfaz gráfica:

```bash
start "" ".\.venv\Scripts\pythonw.exe" gui.py
```

En la GUI, escribe el nombre del spreadsheet, pulsa **Ejecutar** y revisa el log en tiempo real.

## Problemas Comunes

### Se queda en `Starting slskd...` y se rinde

slskd no ha podido conectar. Lánzalo a mano para ver el motivo:

& "$env:LOCALAPPDATA\MusicManager\tools\slskd\slskd.exe" --app-dir "$env:LOCALAPPDATA\MusicManager\tools\slskd_data"


Si dice `Failed to start listening on 0.0.0.0:50300`, Windows tiene el puerto reservado (`netsh interface ipv4 show excludedportrange protocol=tcp`). Cambia el puerto en **Settings** a uno fuera de esos rangos, por ejemplo 2234.

Si dice `username and/or password invalid`, revisa las credenciales de Soulseek en **Settings**.

### Montar el proyecto en otro ordenador

No hay que repetir nada de Google Cloud ni volver a compartir la hoja.
1.  Instala desde el mismo instalador.
2.  Copia el `credentials.json` del otro equipo. Si no lo tienes a mano, crea una clave nueva en la **misma** cuenta de servicio (Credenciales > la cuenta > Claves > Agregar clave > JSON). No invalida la del otro portátil.
3.  Rellena el setup. 

## Estructura del Proyecto

*   `music_manager.py`: Script principal de Python.
*   `gui.py`: Interfaz gráfica para ejecutar y monitorizar el proceso.
*   `playlistHelper.gs`: Script para Google Sheets (Google Apps Script).
*   `requirements.txt`: Lista de librerías de Python necesarias.
*   `MusicManager.spec` e `installer.iss`: Generación del exe y del instalador.