# PyInstaller spec for Map Poster Studio.  Build with build.bat (Windows).
# Produces dist\MapPosterStudio\MapPosterStudio.exe (one folder, fast startup).

from PyInstaller.utils.hooks import (collect_data_files, collect_dynamic_libs,
                                     collect_submodules, copy_metadata)

datas = [("mapposter/resources", "mapposter/resources"), ("assets", "assets")]
datas += collect_data_files("pyproj")      # PROJ database (proj.db)
datas += collect_data_files("pyogrio")     # GDAL data
datas += collect_data_files("osmnx")
datas += collect_data_files("certifi")
datas += collect_data_files("tkintermapview")
datas += collect_data_files("sv_ttk")
# Some libraries read their own version at import time (importlib.metadata).
for pkg in ("osmnx", "geopandas", "shapely", "pyproj", "pyogrio", "networkx", "pandas",
            "numpy", "matplotlib", "requests", "geopy", "osmium", "pillow", "qrcode"):
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass

binaries = collect_dynamic_libs("osmium") + collect_dynamic_libs("pyogrio") \
    + collect_dynamic_libs("pyproj") + collect_dynamic_libs("shapely")

hiddenimports = (
    collect_submodules("osmium")
    + collect_submodules("pyogrio")
    + collect_submodules("lat_lon_parser")
    + collect_submodules("tkintermapview")
    + collect_submodules("qrcode")
    + collect_submodules("sv_ttk")
    + ["geopy.geocoders", "PIL.ImageTk", "matplotlib.backends.backend_agg",
       "matplotlib.backends.backend_pdf", "matplotlib.backends.backend_svg"]
)

excludes = [
    "PyQt5", "PyQt6", "PySide2", "PySide6", "IPython", "jupyter", "notebook",
    "pytest", "sphinx", "matplotlib.backends.backend_qtagg", "sklearn",
    "folium", "plotly", "fiona",
]

a = Analysis(
    ["MapPosterStudio.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MapPosterStudio",
    icon="assets/icon.ico",
    console=True,          # console for CLI use; the window hides it when double-clicked
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name="MapPosterStudio", upx=False)
