# Building the Windows installer

Install Inno Setup 6, then run:

```bat
installer\build_installer.bat
```

The installer places the application files under:

```text
%ProgramFiles%\IR_Raman_analysis_Toolkit
```

Runtime policy:

```text
IR/Raman Phase Finder uses the shared Sci runtime:
%LOCALAPPDATA%\Sci\env
```

The launcher commands are written to:

```text
%LOCALAPPDATA%\Sci\bin
```

User cache and downloaded reference data are stored under:

```text
%LOCALAPPDATA%\Sci\apps\ir_raman_analysis_toolkit
```

Logs are stored under:

```text
%LOCALAPPDATA%\Sci\logs\ir_raman_analysis_toolkit
```

This installer does not redistribute third-party spectral databases. RRUFF, OpenSpecy and user libraries remain user-managed/downloaded.
