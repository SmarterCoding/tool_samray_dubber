
#define AppName "SamrayDubberPro"
#define AppVersion "1.0.0"
#define AppPublisher "Chamnan Dev"
#define AppExeName "SamrayDubberPro.exe"

[Setup]
AppId={{D0B54C1D-9C42-4C1D-A9B0-123456789ABC}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}

DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}

OutputDir=..\..\release\windows
OutputBaseFilename=SamrayDubberPro-windows-Setup

SetupIconFile=..\..\assets\icons\icon.ico

Compression=lzma2
SolidCompression=yes
WizardStyle=modern

ArchitecturesInstallIn64BitMode=x64

UninstallDisplayIcon={app}\{#AppExeName}

[Files]
Source: "..\..\dist\windows\SamrayDubberPro\*"; \
    DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; \
    Filename: "{app}\{#AppExeName}"

Name: "{autodesktop}\{#AppName}"; \
    Filename: "{app}\{#AppExeName}"

[Run]
Filename: "{app}\{#AppExeName}"; \
    Description: "Launch {#AppName}"; \
    Flags: postinstall nowait skipifsilent
