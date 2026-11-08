"""Launcher for Map Poster Studio (also the PyInstaller entry point).

  Double-click / no arguments  -> opens the window (console hidden)
  With arguments               -> command line, e.g.  MapPosterStudio.exe -c Phoenix -C USA
"""

import multiprocessing
import sys


def _hide_own_console() -> None:
    """When double-clicked, Windows gives the exe its own console; hide it.
    When run from PowerShell/cmd the console is shared, so leave it alone."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        procs = (ctypes.c_uint * 4)()
        if k32.GetConsoleProcessList(procs, 4) <= 1:
            hwnd = k32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if len(sys.argv) == 1:
        _hide_own_console()
        from mapposter.gui import main as gui_main
        gui_main()
        return 0

    from mapposter.cli import main as cli_main
    return cli_main(sys.argv[1:])


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
