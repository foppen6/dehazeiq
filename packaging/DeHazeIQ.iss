; Inno Setup-skript för DeHazeIQ (Windows-installationsprogram).
; Byggs av GitHub Actions:  ISCC.exe /DAppVersion=0.3.0 packaging\DeHazeIQ.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6E0B7C1E-4D7A-4F0B-9C3E-DE4A2E1F0A11}
AppName=DeHazeIQ
AppVersion={#AppVersion}
AppVerName=DeHazeIQ {#AppVersion}
AppPublisher=DeHazeIQ
DefaultDirName={localappdata}\Programs\DeHazeIQ
DefaultGroupName=DeHazeIQ
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\Output
OutputBaseFilename=DeHazeIQ-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\DeHazeIQ.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.DesktopIconText=Skapa genväg på skrivbordet
english.LaunchText=Starta DeHazeIQ

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIconText}"; Flags: checkedonce

[Files]
Source: "..\dist\DeHazeIQ\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\DeHazeIQ"; Filename: "{app}\DeHazeIQ.exe"
Name: "{autodesktop}\DeHazeIQ"; Filename: "{app}\DeHazeIQ.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\DeHazeIQ.exe"; Description: "{cm:LaunchText}"; Flags: nowait postinstall skipifsilent
