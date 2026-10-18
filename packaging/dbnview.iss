; Inno Setup script for the Windows installer (per-user install, no admin rights needed).
;     pyinstaller --noconfirm packaging/dbnview.spec
;     iscc /DAppVersion=0.5.0 packaging/dbnview.iss      -> dist/DBNView-0.5.0-Windows-Setup.exe
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6D3B5F0E-2B7C-4E2A-9C1D-DB4E5F6A7B80}
AppName=DBNView
AppVersion={#AppVersion}
AppVerName=DBNView {#AppVersion}
AppPublisher=Haochen Luo
AppPublisherURL=https://github.com/chester1uo/DBNView
DefaultDirName={autopf}\DBNView
DefaultGroupName=DBNView
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=DBNView-{#AppVersion}-Windows-Setup
SetupIconFile=dbnview.ico
UninstallDisplayIcon={app}\DBNView.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\DBNView\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\DBNView"; Filename: "{app}\DBNView.exe"
Name: "{group}\{cm:UninstallProgram,DBNView}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\DBNView"; Filename: "{app}\DBNView.exe"; Tasks: desktopicon

[Registry]
; "Open with" entries for .dbn / .zst files (does not take over the default handler)
Root: HKA; Subkey: "Software\Classes\Applications\DBNView.exe\shell\open\command"; ValueType: string; ValueData: """{app}\DBNView.exe"" ""%1"""; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.dbn\OpenWithProgids"; ValueType: string; ValueName: "DBNView.dbn"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.zst\OpenWithProgids"; ValueType: string; ValueName: "DBNView.dbn"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\DBNView.dbn"; ValueType: string; ValueData: "Databento DBN file"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\DBNView.dbn\DefaultIcon"; ValueType: string; ValueData: "{app}\DBNView.exe,0"
Root: HKA; Subkey: "Software\Classes\DBNView.dbn\shell\open\command"; ValueType: string; ValueData: """{app}\DBNView.exe"" ""%1"""

[Run]
Filename: "{app}\DBNView.exe"; Description: "{cm:LaunchProgram,DBNView}"; Flags: nowait postinstall skipifsilent
