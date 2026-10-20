import argparse
from pathlib import Path

from config import cfg
import log
from stop import STOP_EVENT
import bootstrap
from slskd_client import ensure_slskd, stop_slskd
from sheets import setup_gspread, process_sheet

def run_manager(spreadsheet_name):
    download_dir = str(Path(cfg()['music_dir']) / (spreadsheet_name.upper() + " PLAYLIST"))

    log.line("\nRunning the playlist builder")
    log.line(f"Spreadsheet: {spreadsheet_name}")
    log.line(f"Saving to: {download_dir}")

    STOP_EVENT.clear()
    slskd_proc = None
    try:
        bootstrap.ensure_slskd_yml()
        slskd_proc = ensure_slskd()
        client = setup_gspread()
        if not client:
            return
        log.line("Checking what you want...")
        process_sheet(client, spreadsheet_name, download_dir)
        log.line("Finished :)", "done")
    except SystemExit as e:
        log.line(str(e), "error")
    except Exception as e:
        log.line(f"Global Error: {e}", "error")
    finally:
        stop_slskd(slskd_proc)

def stop_manager():
    log.line("Stopping...")
    STOP_EVENT.set()

def main():
    parser = argparse.ArgumentParser(description="Music Manager v2")
    parser.add_argument("name", help="Name of the spreadsheet (and output folder)")
    args = parser.parse_args()
    run_manager(args.name)


if __name__ == "__main__":
    main()
