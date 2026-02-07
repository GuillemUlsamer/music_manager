const DISCOGS_TOKEN = "bJGcsTjCeCfrDHmLxCEqbLCipDUAvLliBesoOkHy";
const USER_AGENT = "AlwaysHardcoreSheets/1.0";

function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('Always Hardcore')
    .addItem('Import Discogs Release', 'showImportDialog')
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
      sheet.getRange("D2:E").setNumberFormat("[h]:mm:ss");
      const checkboxRange = sheet.getRange(2, 6, rows.length, 1);
      checkboxRange.insertCheckboxes();
    }
  } catch (e) {
    SpreadsheetApp.getUi().alert("Error importing: " + e.toString());
  }
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
