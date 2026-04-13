# Music Manager & Playlist Downloader

Este proyecto sincroniza una carpeta de música local con una hoja de cálculo de Google Sheets.

Si una canción de tu sheet de google esta marcada, la busca y la descarga de YouTube, la convierte a MP3, añade metadatos (ID3 tags) y actualiza el estado en la hoja de cálculo. También gestiona el borrado de archivos si se desmarcan en la lista.

Incluye un script de Google Apps Script (`playlistHelper.gs`) para importar tracklists directamente desde Discogs a la hoja de cálculo. 

## Requisitos Previos

1.  **Python 3.9+** instalado.
2.  **FFmpeg**: Necesario para que `yt-dlp` pueda extraer y convertir el audio a MP3. Debe estar en tu variable de entorno PATH.
3.  **Cuenta de Servicio de Google**:
    *   Habilita las APIs de Google Sheets y Google Drive en Google Cloud Console.
    *   Crea una cuenta de servicio y descarga la clave JSON.
    *   Guarda el archivo como `credentials.json` en la carpeta raíz del proyecto.
    *   **Importante**: Comparte tu hoja de cálculo con el email de la cuenta de servicio (aparece en el JSON como `client_email`).

## Instalación

1.  Clona el repositorio.
2.  Instala las dependencias de Python:

```bash
pip install -r requirements.txt
```

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
   
function onOpen() {
  General_music_manager.onOpen();
}

function showImportDialog() {
  General_music_manager.showImportDialog();
}

function showSetupDialog() {
  General_music_manager.showSetupDialog();
}

function setupSheet(sheetFileName, volNum) {
  General_music_manager.setupSheet(sheetFileName, volNum);
}

function importDiscogsRelease(sheetName, releaseId) {
  General_music_manager.importDiscogsRelease(sheetName, releaseId);
}

function durationToSeconds(duration) {
  General_music_manager.durationToSeconds(duration);
}

function secondsToSheetsDuration(seconds) {
  General_music_manager.secondsToSheetsDuration(seconds);
}

5.  Recarga la hoja. Aparecerá un menú personalizado para importar releases de Discogs usando su ID.

## Uso

Ejecuta el script desde la terminal indicando el nombre de la hoja de cálculo (que debe coincidir con el nombre de la hoja en Google Drive). El script creará una carpeta con ese mismo nombre en el directorio padre `../MUSIC/`.

```bash
python music_manager.py "Nombre de tu Playlist"
```

### Argumentos

*   `name`: El nombre exacto de la Google Sheet. También será el nombre de la carpeta donde se guarden los MP3.

### Ejemplo

Si tu hoja se llama "Always hardcore":

```bash
python music_manager.py "Always hardcore"
```

Esto buscará o creará la carpeta `../ALWAYS HARDCORE PLAYLIST` y descargará las canciones marcadas.

depende de desde donde ejecutes el programa, yo tengo una carpeta en mi ordenador con todas mis playlists por ejemplo /Desktop/MUSIC/ 

## Estructura del Proyecto

*   `music_manager.py`: Script principal de Python.
*   `playlistHelper.gs`: Script para Google Sheets (Google Apps Script).
*   `requirements.txt`: Lista de librerías de Python necesarias.
*   `credentials.json`: (Ignorado por git) Tu clave privada de Google.

## Notas de Seguridad

El archivo `credentials.json` contiene claves privadas. **Nunca** subas este archivo a un repositorio público (ya está incluido en `.gitignore`).
