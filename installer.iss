; Inno Setup Script for ThermalEngine
; This script is used by GitHub Actions (and scripts/build-local.ps1) to create
; the Windows installer. Build first with Nuitka so that dist\ThermalEngine
; exists, then compile this script with ISCC.exe.

#ifndef MyAppName
  #define MyAppName "ThermalEngine"
#endif
#ifndef MyAppPublisher
  #define MyAppPublisher "Thermal Engine"
#endif
#ifndef MyAppExeName
  #define MyAppExeName "ThermalEngine.exe"
#endif
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#ifndef MyAppVersionNum
  #define MyAppVersionNum "0.0.0"
#endif

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/sito1982/Thermal-Engine-Linux
AppSupportURL=https://github.com/sito1982/Thermal-Engine-Linux/issues
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
DisableDirPage=auto
DisableProgramGroupPage=auto
OutputDir=.
OutputBaseFilename=ThermalEngine-{#MyAppVersion}-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; Instalación por usuario (sin administrador). Las tareas que requieren
; elevación (firewall) la piden de forma puntual con el flag runas.
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64
; Windows 10 o superior (PySide6 6.5+ / Qt 6.5).
MinVersion=10.0
SetupIconFile=assets\icon.ico
UsePreviousAppDir=yes
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
VersionInfoVersion={#MyAppVersionNum}
VersionInfoCompany={#MyAppPublisher}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersionNum}
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "openwith"; Description: "Añadir 'Abrir con Thermal Engine Studio' al menú contextual de los archivos .json"; GroupDescription: "Integración:"; Flags: unchecked
Name: "firewall"; Description: "Permitir el servidor web local (TCP 4241) en el Firewall de Windows (requiere administrador)"; GroupDescription: "Integración:"; Flags: unchecked

[Files]
; Archivos de la aplicación. Los datos que el usuario puede personalizar
; (presets, elements, icons, settings.json) se excluyen aquí y se tratan aparte
; para no sobrescribirlos en las actualizaciones.
Source: "dist\ThermalEngine\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "presets\*, elements\*, icons\*, settings.json"
; Datos por defecto: solo se copian si no existen ya (preserva personalizaciones).
Source: "dist\ThermalEngine\presets\*"; DestDir: "{app}\presets"; Flags: onlyifdoesntexist recursesubdirs createallsubdirs
Source: "dist\ThermalEngine\elements\*"; DestDir: "{app}\elements"; Flags: onlyifdoesntexist recursesubdirs createallsubdirs
Source: "dist\ThermalEngine\icons\*"; DestDir: "{app}\icons"; Flags: onlyifdoesntexist recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; "Abrir con" en el menú contextual de los .json, sin secuestrar la asociación
; por defecto del sistema.
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.json\shell\ThermalEngineStudio"; ValueType: string; ValueName: ""; ValueData: "Abrir con Thermal Engine Studio"; Flags: uninsdeletekey; Tasks: openwith
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.json\shell\ThermalEngineStudio"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#MyAppExeName},0"; Tasks: openwith
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.json\shell\ThermalEngineStudio\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: openwith

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent runascurrentuser
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Thermal Engine Studio (web)"" dir=in action=allow protocol=TCP localport=4241"; StatusMsg: "Configurando el Firewall de Windows..."; Flags: runas; Tasks: firewall

[UninstallDelete]
; Cachés generadas en tiempo de ejecución (no incluye datos del usuario).
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
function VCRuntimeInstalled(): Boolean;
begin
  { El runtime VC++ 2015-2022 suele venir ya en Windows 10/11 o incluido por
    Nuitka/PySide6. La comprobación es informativa, no bloqueante. }
  Result :=
    RegValueExists(HKLM64, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed') or
    RegValueExists(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed');
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if not IsWin64 then
  begin
    MsgBox('Thermal Engine Studio requiere una versión de Windows de 64 bits.', mbCriticalError, MB_OK);
    Result := False;
    Exit;
  end;
  if GetWindowsVersion < $0A000000 then
    MsgBox('Se recomienda Windows 10 o superior. En versiones anteriores la ' +
           'aplicación podría no funcionar correctamente.', mbInformation, MB_OK);
  if not VCRuntimeInstalled() then
    MsgBox('No se detectó el Microsoft Visual C++ Redistributable (2015-2022). ' +
           'Normalmente viene incluido en Windows 10/11 o empaquetado con la ' +
           'aplicación; si la app no arranca, instálalo desde https://aka.ms/vs/17/release/vc_redist.x64.exe',
           mbInformation, MB_OK);
end;
