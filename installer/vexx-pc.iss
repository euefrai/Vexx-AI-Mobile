#ifndef PayloadDir
  #error PayloadDir is required. Use tools/build_pc_installer.py.
#endif
#ifndef AppVersion
  #error AppVersion is required.
#endif
#ifndef OutputDir
  #define OutputDir "..\output\installer"
#endif

[Setup]
AppId=VexxPC.Desktop
AppName=Vexx PC
AppVersion={#AppVersion}
AppPublisher=Vexx AI
AppPublisherURL=https://vexx-ai.onrender.com
DefaultDirName={localappdata}\VexxPC\app
DefaultGroupName=Vexx PC
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
AppMutex=VexxPC.Desktop
UninstallDisplayIcon={app}\VexxPC.ico
SetupIconFile={#PayloadDir}\VexxPC.ico
OutputDir={#OutputDir}
OutputBaseFilename=Vexx-PC-Setup-{#AppVersion}
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=no
RestartApplications=no
ChangesAssociations=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; Flags: checkedonce

[UninstallRun]
Filename: "{sys}\reg.exe"; Parameters: "delete ""HKCU\Software\Microsoft\Windows\CurrentVersion\Run"" /v VexxPC /f"; Flags: runhidden

[Files]
Source: "{#PayloadDir}\runtime\*"; DestDir: "{app}\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#PayloadDir}\source\Vexx-PC\*"; DestDir: "{tmp}\VexxPCSource"; Flags: ignoreversion recursesubdirs createallsubdirs deleteafterinstall
Source: "{#PayloadDir}\wheels\*"; DestDir: "{tmp}\VexxPCWheels"; Flags: ignoreversion deleteafterinstall
Source: "{#PayloadDir}\bootstrap.py"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall
Source: "{#PayloadDir}\VexxPC.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\MicrosoftEdgeWebview2Setup.exe"; Flags: dontcopy

[Icons]
Name: "{group}\Vexx PC"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\launch.py"""; WorkingDir: "{app}"; IconFilename: "{app}\VexxPC.ico"; AppUserModelID: "Vexx.PC"
Name: "{autodesktop}\Vexx PC"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\launch.py"""; WorkingDir: "{app}"; IconFilename: "{app}\VexxPC.ico"; Tasks: desktopicon; AppUserModelID: "Vexx.PC"

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\launch.py"""; WorkingDir: "{app}"; Description: "Abrir Vexx PC"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\releases"
Type: filesandordirs; Name: "{app}\runtime"
Type: files; Name: "{app}\launch.py"
Type: files; Name: "{app}\current.json"
Type: files; Name: "{app}\install.log"

[Code]
var InstallPrepared: Boolean;

function GetCustomSetupExitCode: Integer;
begin
  if InstallPrepared then Result := 0 else Result := 1;
end;

function HasWebView2: Boolean;
var Names: TArrayOfString; I: Integer; Name, Version: String;
begin
  Result := False;
  if RegGetSubkeyNames(HKLM32, 'Software\Microsoft\EdgeUpdate\Clients', Names) then
    for I := 0 to GetArrayLength(Names)-1 do
      if RegQueryStringValue(HKLM32, 'Software\Microsoft\EdgeUpdate\Clients\'+Names[I], 'name', Name) and
         (Pos('WebView2', Name) > 0) and
         RegQueryStringValue(HKLM32, 'Software\Microsoft\EdgeUpdate\Clients\'+Names[I], 'pv', Version) and
         (Version <> '') and (Version <> '0.0.0.0') then Result := True;
  if not Result and RegGetSubkeyNames(HKCU, 'Software\Microsoft\EdgeUpdate\Clients', Names) then
    for I := 0 to GetArrayLength(Names)-1 do
      if RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\'+Names[I], 'name', Name) and
         (Pos('WebView2', Name) > 0) and
         RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\'+Names[I], 'pv', Version) and
         (Version <> '') and (Version <> '0.0.0.0') then Result := True;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var ExitCode: Integer;
begin
  Result := '';
  if not HasWebView2 then begin
    WizardForm.StatusLabel.Caption := 'Preparando o componente de janela do Windows...';
    ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
    if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) or
       not HasWebView2 then
      Result := 'Não foi possível preparar o WebView2. Verifique a conexão com a internet e execute o instalador novamente.';
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var ExitCode: Integer; Args: String;
begin
  if CurStep = ssPostInstall then begin
    WizardForm.StatusLabel.Caption := 'Preparando o aplicativo e suas dependências...';
    WizardForm.Update;
    Args := '"' + ExpandConstant('{tmp}\bootstrap.py') + '" --root "' + ExpandConstant('{app}') +
      '" --source "' + ExpandConstant('{tmp}\VexxPCSource') + '" --wheels "' + ExpandConstant('{tmp}\VexxPCWheels') + '"';
    if not Exec(ExpandConstant('{app}\runtime\python.exe'), Args, '', SW_HIDE, ewWaitUntilTerminated, ExitCode) or (ExitCode <> 0) or
       not FileExists(ExpandConstant('{app}\current.json')) then
      RaiseException('Não foi possível preparar o Vexx PC. Seus dados foram preservados. Consulte o arquivo install.log na pasta do aplicativo.');
    InstallPrepared := True;
  end;
end;
