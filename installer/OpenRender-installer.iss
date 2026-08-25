; OpenRender - Windows installer (Inno Setup)
; Compile with ISCC.exe (Inno Setup 6 or 7), or just run build_installer.bat
;
; Produces: installer-output/OpenRender-Setup-0.0.1-beta.exe
;   - Per-user install (no admin): %LOCALAPPDATA%\Programs\OpenRender
;   - Start Menu + optional desktop shortcut
;   - config.json survives reinstalls AND uninstalls (user settings)

#define MyAppName "OpenRender"
#define MyAppVersion "0.0.1"
#define MyAppVersionLabel "0.0.1 beta"
#define MyAppPublisher "OpenRender"
#define MyAppExeName "OpenRender.exe"

[Setup]
AppId={{6F3A9C42-1B7D-4E58-9A0F-C2D41B7E9A63}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersionLabel}
AppPublisher={#MyAppPublisher}
; Install into a VISIBLE, easy-to-find folder (Documents\OpenRender) holding
; everything together: OpenRender.exe + openrender-extension\. Users must be
; able to browse to the extension folder themselves when loading it unpacked,
; so hiding the app inside AppData was a support trap.
DefaultDirName={userdocs}\{#MyAppName}
PrivilegesRequired=lowest
DisableDirPage=no
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=installer-output
OutputBaseFilename=OpenRender-Setup-{#MyAppVersion}-beta
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\OpenRender.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\release\OpenRender\config.json"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "..\release\OpenRender\LEEME.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\openrender-extension\*"; DestDir: "{app}\openrender-extension"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "OpenRender - agente de IA para tu carpeta de proyecto"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Iniciar OpenRender ahora"; Flags: nowait postinstall skipifsilent
Filename: "{app}\openrender-extension"; Description: "Abrir la carpeta de la extension (para cargarla en Chrome/Edge)"; Flags: postinstall shellexec skipifsilent

[UninstallDelete]
; logs are disposable, but keep config.json (uninsneveruninstall above)
Type: files; Name: "{app}\logs\*.log"
