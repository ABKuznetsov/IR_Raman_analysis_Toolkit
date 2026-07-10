#define MyAppName "IR/Raman Phase Finder"
#define MyAppVersion "0.1.4"
#define MyAppPublisher "ABKuznetsov"
#define MyAppURL ""
#define MyShortcutName "IR Raman Phase Finder"

[Setup]
AppId={{A8C3F5AA-B8B3-49C8-B23C-15AB1B7A8A21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\IR_Raman_analysis_Toolkit
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DefaultGroupName=IR Raman Analysis Toolkit
MinVersion=10.0
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=output
OutputBaseFilename=IR_Raman_analysis_Toolkit_Setup_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\icon.ico
UninstallDisplayName={#MyAppName}
VersionInfoVersion={#MyAppVersion}
CreateUninstallRegKey=yes
Uninstallable=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a Desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce
Name: "setupenv"; Description: "Prepare shared Sci Python environment after install"; GroupDescription: "Environment:"; Flags: checkedonce

[Files]
Source: "..\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "installer\*,.git\*,.agents\*,.codex\*,.venv\*,__pycache__\*,*.pyc,*.pyo,.DS_Store,.ruff_cache\*,.pytest_cache\*,build\*,dist\*,logs\*,.cache\*,*.egg-info\*"

[Icons]
Name: "{group}\{#MyShortcutName}"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy RemoteSigned -WindowStyle Hidden -File ""{app}\toolkit\launch_ir_raman_phase_finder_preview.ps1"" -AppId ir_raman_phase_finder"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"
Name: "{group}\Setup Sci Environment"; Filename: "{app}\toolkit\setup_sci_env.bat"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyShortcutName}"; Filename: "{uninstallexe}"; IconFilename: "{uninstallexe}"
Name: "{autodesktop}\{#MyShortcutName}"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy RemoteSigned -WindowStyle Hidden -File ""{app}\toolkit\launch_ir_raman_phase_finder_preview.ps1"" -AppId ir_raman_phase_finder"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\toolkit\setup_sci_env.bat"; Description: "Prepare Sci environment"; Flags: postinstall runascurrentuser skipifsilent; Tasks: setupenv
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy RemoteSigned -WindowStyle Hidden -File ""{app}\toolkit\launch_ir_raman_phase_finder_preview.ps1"" -AppId ir_raman_phase_finder"; Description: "Launch IR/Raman Phase Finder"; Flags: postinstall nowait skipifsilent unchecked

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
