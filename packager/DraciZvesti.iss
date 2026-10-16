#ifndef SourceDir
  #error SourceDir must point to the PyInstaller onedir output.
#endif
#ifndef OutputDir
  #error OutputDir must point to packager/artifacts.
#endif
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

#define AppName "Draci Zvesti"
#define AppExeName "DraciZvesti.exe"

[Setup]
AppId={{A26F3DAA-9689-4A6C-B44B-A1112247EB71}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Draci Zvesti
DefaultDirName={localappdata}\Programs\DraciZvesti
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=DraciZvesti-{#AppVersion}-Windows-x64-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\{#AppExeName}
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; Preserve mutable deck/card databases across upgrades and uninstalls.  The
; wildcard entry excludes them and the dedicated entries install only seeds.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "_internal\utils\cards.db,_internal\utils\decks.db"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceDir}\_internal\utils\cards.db"; DestDir: "{app}\_internal\utils"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "{#SourceDir}\_internal\utils\decks.db"; DestDir: "{app}\_internal\utils"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
