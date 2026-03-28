const DISCOGS_TOKEN = "bJGcsTjCeCfrDHmLxCEqbLCipDUAvLliBesoOkHy";
const USER_AGENT = "MusicManagerApp/1.0";
const RELEASES_SHEET_NAME = "Releases";

function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('music_manager')
    .addItem('Import Discogs Release', 'showImportDialog')
    .addItem('Set up', 'showSetupDialog')
    .addToUi();
}

function showImportDialog() {
  const ui = SpreadsheetApp.getUi();
  const result = ui.prompt(
    'Import Release',
    'Enter Release ID (e.g. 1669268):',
    ui.ButtonSet.OK_CANCEL
  );

  if (result.getSelectedButton() == ui.Button.OK) {
    const releaseId = result.getResponseText();
    const sheetName = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet().getName();
    importDiscogsRelease(sheetName, releaseId);
  }
}

function showSetupDialog() {
  const ui = SpreadsheetApp.getUi();
  const result = ui.prompt(
    'Set up sheets',
    'Enter the number of volumes:',
    ui.ButtonSet.OK_CANCEL
  );

  if (result.getSelectedButton() == ui.Button.OK) {
    const volNum = result.getResponseText();
    const sheetFileName = SpreadsheetApp.getActiveSpreadsheet();
    setupSheet(sheetFileName, volNum);
  }
}

function setupSheet(sheetFileName, volNum) {
  const releasesSheet = getOrCreateReleasesSheet(sheetFileName);
  initializeReleasesSheetHeaders(releasesSheet);

  for (var i = 1; i <= volNum; ++i){
    let newName = "V " + i;
    let sheet = sheetFileName.getSheetByName(newName);

    if(sheet == null) 
      sheet = sheetFileName.insertSheet(newName);

    // Clear A:G (por si acaso)
    sheet.getRange("A:G").clearContent();
    sheet.getRange("A:G").removeCheckboxes();
    sheet.getRange("A:K").clearFormat();

    const headerColA = "Track #";
    sheet.setColumnWidth(1, 60);
    const headerColB = "Artist";
    sheet.setColumnWidth(2, 300);
    const headerColC = "Title";
    sheet.setColumnWidth(3, 400);
    const headerColD = "Duration";
    sheet.setColumnWidth(4, 80);
    const headerColE = "Cumulative";
    sheet.setColumnWidth(5, 80);
    const headerColF = "Add to Playlist";
    sheet.setColumnWidth(6, 100);
    const headerColG = "Notes";
    sheet.setColumnWidth(5, 150);

    let headers = [];
    headers.push([
      headerColA, headerColB, headerColC, headerColD, 
      headerColE, headerColF, headerColG
    ])
    
    sheet.getRange(1,1,1,7).setValues(headers);
    // Store per-sheet metadata in hidden columns I:K.
    sheet.getRange("I1").setValue("Album");
    sheet.getRange("J1").setValue("Year");
    sheet.getRange("K1").setValue("CoverURL");
    sheet.hideColumns(8, 4);
  } 
}

function importDiscogsRelease(sheetName, releaseId) {
  const sheet = SpreadsheetApp.getActive().getSheetByName(sheetName);
  // Clear content A2:G (keep headers in row 1)
  sheet.getRange("A2:G").clearContent();

  const url = `https://api.discogs.com/releases/${releaseId}`;
  try {
    const response = UrlFetchApp.fetch(url, {
      headers: {
        "Authorization": "Discogs token=" + DISCOGS_TOKEN,
        "User-Agent": USER_AGENT
      }
    });

    const data = JSON.parse(response.getContentText());
    const tracks = data.tracklist;
    const albumName = data.title || "";
    const releaseYear = data.year || "";
    const coverUrl = (data.images && data.images.length > 0 && data.images[0].uri) ? data.images[0].uri : "";

    // Persist metadata on the track sheet for the Python downloader.
    sheet.getRange("I1").setValue(albumName);
    sheet.getRange("J1").setValue(releaseYear);
    sheet.getRange("K1").setValue(coverUrl);

    let rows = [];
    let cumulativeSeconds = 0;
    let trackCounter = 1; 

    tracks.forEach(track => {
      if (track.type_ !== "track") return;
      if (!track.duration) track.duration = "0:00"; 

      const seconds = durationToSeconds(track.duration);
      if (isNaN(seconds)) return;

      cumulativeSeconds += seconds;

      let position = track.position || String(trackCounter++).padStart(2, "0");

      rows.push([
        position,
        track.artists && track.artists.length
          ? track.artists.map(a => a.name).join(" & ")
          : (data.artists ? data.artists.map(a => a.name).join(" & ") : ""),
        track.title,
        seconds / 86400,
        cumulativeSeconds / 86400,
        false, // Checkbox
        ""     // Status
      ]);
    });

    if (rows.length > 0) {
      sheet.getRange(2, 1, rows.length, 7).setValues(rows);
      sheet.getRange(2, 1, rows.length, 7).activate();
      SpreadsheetApp.getActive().getActiveRangeList().setHorizontalAlignment('left');
      sheet.getRange("D2:E").setNumberFormat("[h]:mm:ss");
      const checkboxRange = sheet.getRange(2, 6, rows.length, 1);
      checkboxRange.insertCheckboxes();
    }

    appendReleaseToCatalog(albumName, releaseYear, coverUrl);
  } catch (e) {
    SpreadsheetApp.getUi().alert("Error importing: " + e.toString());
  }
}

function getOrCreateReleasesSheet(spreadsheet) {
  let releasesSheet = spreadsheet.getSheetByName(RELEASES_SHEET_NAME);
  if (!releasesSheet) {
    releasesSheet = spreadsheet.insertSheet(RELEASES_SHEET_NAME, 0);
  }
  spreadsheet.setActiveSheet(releasesSheet);
  spreadsheet.moveActiveSheet(1);
  return releasesSheet;
}

function initializeReleasesSheetHeaders(releasesSheet) {
  releasesSheet.getRange("A1").setValue("NAME OF THE ALBUM");
  releasesSheet.getRange("B1").setValue("YEAR");
  releasesSheet.getRange("C1").setValue("COVER");
  releasesSheet.setColumnWidth(1, 320);
  releasesSheet.setColumnWidth(2, 100);
  releasesSheet.setColumnWidth(3, 220);
}

function appendReleaseToCatalog(albumName, releaseYear, coverUrl) {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const releasesSheet = getOrCreateReleasesSheet(spreadsheet);
  initializeReleasesSheetHeaders(releasesSheet);

  const targetRow = Math.max(releasesSheet.getLastRow() + 1, 2);
  const imageFormula = coverUrl
    ? '=IMAGE("' + coverUrl.replace(/"/g, '""') + '")'
    : "";

  releasesSheet.getRange(targetRow, 1, 1, 3).setValues([[albumName, releaseYear, imageFormula]]);
  releasesSheet.setRowHeight(targetRow, 180);
}

function durationToSeconds(duration) {
  if (!duration) return 0;
  const parts = duration.split(":").map(Number);
  return parts.length === 3
    ? parts[0] * 3600 + parts[1] * 60 + parts[2]
    : parts[0] * 60 + parts[1];
}

function secondsToSheetsDuration(seconds) {
  return seconds / 86400;
}
