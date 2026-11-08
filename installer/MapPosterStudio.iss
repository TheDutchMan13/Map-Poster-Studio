; Inno Setup script for Map Poster Studio. Built by build_installer.bat.
; Installs per user (no admin prompt) so the app can keep its themes, presets,
; posters and cache next to the exe.

#ifndef MyAppVersion
  #define MyAppVersion "1.4.0"
#endif
#define MyAppName "Map Poster Studio"
#define MyAppExe "MapPosterStudio.exe"

[Setup]
AppId={{6F7B2C1E-4E0B-4C55-9A57-3B1D2E7A9C41}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Hans De Kryger
DefaultDirName={localappdata}\Programs\Map Poster Studio
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=MapPosterStudio-Setup-{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\MapPosterStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\batch_example.csv"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\Posters folder"; Filename: "{app}\posters"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Dirs]
Name: "{app}\posters"

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Start {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Downloaded map data and caches go; your posters, themes and presets stay.
Type: filesandordirs; Name: "{app}\cache"
Type: filesandordirs; Name: "{app}\fonts"
