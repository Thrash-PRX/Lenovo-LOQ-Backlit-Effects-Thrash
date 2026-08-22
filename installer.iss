#define MyAppName "Thrash Lightening Control"
#define MyAppVersion "3.1.1"
#define MyAppPublisher "Thrash"
#define MyAppExeName "ThrashLighteningControl.exe"

[Setup]
AppId={{8AF25A53-845C-4C86-892B-203639D33187}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/Thrash-PRX/Lenovo-LOQ-Backlit-Effects-Thrash
AppSupportURL=https://github.com/Thrash-PRX/Lenovo-LOQ-Backlit-Effects-Thrash/issues
AppUpdatesURL=https://github.com/Thrash-PRX/Lenovo-LOQ-Backlit-Effects-Thrash/releases
DefaultDirName={autopf}\Thrash\Thrash Lightening Control
DefaultGroupName=Thrash Lightening Control
DisableProgramGroupPage=yes
LicenseFile=LICENSE
InfoBeforeFile=installer\INSTALL-NOTES.txt
OutputDir=installer-dist
OutputBaseFilename=ThrashLighteningControl-Setup-v{#MyAppVersion}
SetupIconFile=assets\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/ultra64
SolidCompression=yes
LZMANumBlockThreads=8
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
PrivilegesRequired=admin
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoVersion=3.1.1.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "installer-app\ThrashLighteningControl\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "installer\Thrash-Code-Signing.cer"; DestDir: "{app}\Verification"; Flags: ignoreversion
Source: "installer\SHA256SUMS.txt"; DestDir: "{app}\Verification"; Flags: ignoreversion
Source: "installer\VERIFICATION.txt"; DestDir: "{app}\Verification"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; DestName: "README.md"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autoprograms}\Verification files"; Filename: "{app}\Verification"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#MyAppExeName}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#MyAppExeName}"; ValueType: string; ValueName: "Path"; ValueData: "{app}"; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""Lenovo LOQ Backlit Effects - Thrash"" /F"; Flags: runhidden; RunOnceId: "RemoveStartupTask"
Filename: "{sys}\reg.exe"; Parameters: "delete ""HKCU\Software\Microsoft\Windows\CurrentVersion\Run"" /v ""Lenovo LOQ Backlit Effects - Thrash"" /f"; Flags: runhidden; RunOnceId: "RemoveStartupRunEntry"
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""Thrash Lightening Control"" /F"; Flags: runhidden; RunOnceId: "RemoveNewStartupTask"
Filename: "{sys}\reg.exe"; Parameters: "delete ""HKCU\Software\Microsoft\Windows\CurrentVersion\Run"" /v ""Thrash Lightening Control"" /f"; Flags: runhidden; RunOnceId: "RemoveNewStartupRunEntry"
