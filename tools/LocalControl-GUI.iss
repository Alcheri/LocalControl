#define AppName "LocalControl GUI"
#define AppVersion "1.0.0-beta.1"
#define AppExeName "LocalControl-GUI.exe"

[Setup]
AppId={{9CFC6A25-1FE6-4554-A469-AD8FA32C1C83}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Barry
DefaultDirName={localappdata}\Programs\LocalControl GUI
DefaultGroupName=LocalControl GUI
DisableProgramGroupPage=yes
LicenseFile=..\LICENCE.md
OutputDir=..\dist
OutputBaseFilename=LocalControl-GUI-Setup
SetupIconFile=localcontrol.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
PrivilegesRequired=lowest

[Files]
Source: "..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\LocalControl GUI"; Filename: "{app}\{#AppExeName}"
Name: "{userdesktop}\LocalControl GUI"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch LocalControl GUI"; Flags: nowait postinstall skipifsilent
