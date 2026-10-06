import argparse
from pathlib import Path

from config import cfg
from stop import STOP_EVENT
from slskd_client import ensure_slskd, stop_slskd
from sheets import setup_gspread, process_sheet

def run_manager(spreadsheet_name):
    download_dir = str(Path(cfg()['music_dir']) / (spreadsheet_name.upper() + " PLAYLIST"))

    print("\n\nRunning the playlist builder")
    print(f"Spreadsheet: {spreadsheet_name}")
    print(f"Saving to: {download_dir}")

    STOP_EVENT.clear()
    slskd_proc = None
    try:
        slskd_proc = ensure_slskd()
        client = setup_gspread()
        if not client:
            return
        print("\nChecking what you want...")
        process_sheet(client, spreadsheet_name, download_dir)
        print("\nFinished :)")
    except SystemExit as e:
        print(f"\n{e}")
    except Exception as e:
        print(f"Global Error: {e}")
    finally:
        stop_slskd(slskd_proc)

def stop_manager():
    print("Stopping...")
    STOP_EVENT.set()

def main():
    parser = argparse.ArgumentParser(description="Music Manager v2")
    parser.add_argument("name", help="Name of the spreadsheet (and output folder)")
    args = parser.parse_args()
    run_manager(args.name)


if __name__ == "__main__":
    main()
