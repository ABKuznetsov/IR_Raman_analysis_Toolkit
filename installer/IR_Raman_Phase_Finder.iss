#define MyAppVersion "1.1.0"

[Setup]
AppId={{A8C3F5AA-B8B3-49C8-B23C-15AB1B7A8A21}
AppName=IR/Raman Phase Finder
AppVersion={#MyAppVersion}
AppPublisher=ABKuznetsov
AppPublisherURL=https://github.com/ABKuznetsov/IR_Raman_analysis_Toolkit
DefaultDirName={autopf}\IR_Raman_analysis_Toolkit
DefaultGroupName=IR Raman Analysis Toolkit
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
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
UninstallDisplayName=IR/Raman Phase Finder
VersionInfoVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a Desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce
Name: "setupenv"; Description: "Prepare shared Sci Python environment after install"; GroupDescription: "Environment:"; Flags: checkedonce

[Files]
Source: "..\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "installer\*,.git\*,.agents\*,.codex\*,.venv\*,__pycache__\*,*.pyc,*.pyo,.DS_Store,.ruff_cache\*,.pytest_cache\*,build\*,dist\*,logs\*,.cache\*,*.egg-info\*"

[Icons]
Name: "{group}\IR Raman Phase Finder"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy RemoteSigned -WindowStyle Hidden -File ""{app}\toolkit\launch_ir_raman_phase_finder_preview.ps1"" -AppId ir_raman_phase_finder"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"
Name: "{autodesktop}\IR Raman Phase Finder"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy RemoteSigned -WindowStyle Hidden -File ""{app}\toolkit\launch_ir_raman_phase_finder_preview.ps1"" -AppId ir_raman_phase_finder"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon
Name: "{group}\Setup Sci Environment"; Filename: "{app}\toolkit\setup_sci_env.bat"; WorkingDir: "{app}"
Name: "{group}\Uninstall IR Raman Phase Finder"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\toolkit\setup_sci_env.bat"; Description: "Prepare Sci environment"; Flags: postinstall runascurrentuser skipifsilent; Tasks: setupenv
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy RemoteSigned -WindowStyle Hidden -File ""{app}\toolkit\launch_ir_raman_phase_finder_preview.ps1"" -AppId ir_raman_phase_finder"; Description: "Launch IR/Raman Phase Finder"; Flags: postinstall nowait skipifsilent unchecked
