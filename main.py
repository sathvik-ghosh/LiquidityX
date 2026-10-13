"""LIQUIDITYX launcher.   python main.py [--db PATH] [--demo] [--no-intro] [--reduced-motion]"""
import argparse
import os
import sys
import tkinter as tk


def main():
    ap = argparse.ArgumentParser(description="LiquidityX - Financial Network Intelligence & Crisis Recovery")
    ap.add_argument("--db", default=os.path.expanduser("~/.liquidityx/workspace.db"), help="SQLite workspace file")
    ap.add_argument("--demo", action="store_true", help="load the synthetic demo network if the workspace is empty")
    ap.add_argument("--no-intro", action="store_true", help="skip the intro animation")
    ap.add_argument("--reduced-motion", action="store_true", help="disable animations")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(a.db)), exist_ok=True)
    from liquidityx.service import Workspace
    from liquidityx.db import set_setting
    ws = Workspace(a.db)
    if a.demo:
        ws.load_demo()
    if a.reduced_motion:
        set_setting(ws.conn, "reduced_motion", True)
    try:
        from liquidityx.ui.app import App
        App(ws, intro=not a.no_intro).mainloop()
    except tk.TclError as e:
        sys.exit(f"Could not open a window ({e}). On Linux install python3-tk and run inside a desktop session.")


if __name__ == "__main__":
    main()
