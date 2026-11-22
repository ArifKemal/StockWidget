; StockWidget - Inno Setup 6 betiği
; Derleme (kök dizinden): ISCC.exe packaging\installer.iss  (veya /DMyAppVersion=1.2.3)
; Çıktı:   Output\StockWidget-<sürüm>-setup.exe
;
; Kurulum kullanıcı bazlıdır (yönetici gerekmez):
;   program : %LOCALAPPDATA%\Programs\StockWidget
;   veri    : %APPDATA%\StockWidget            (kaldırmada korunur)
;   kayıt   : HKCU\Software\Microsoft\Windows\CurrentVersion\Run

#ifndef MyAppVersion
  #define MyAppVersion "1.1.0"
#endif

#define MyAppName "StockWidget"
#define MyAppPublisher "Arif Kemal"
#define MyAppURL "https://github.com/ArifKemal/StockWidget"
#define MyAppExeName "StockWidget.exe"

[Setup]
AppId={{9F1B7C24-3E56-4D0A-8B7C-52E1A9D34F60}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
UsePreviousAppDir=yes
MinVersion=10.0
OutputDir=..\Output
OutputBaseFilename={#MyAppName}-{#MyAppVersion}-setup
SetupIconFile=..\assets\stock.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} kurulumu
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "autostart"; Description: "Windows açılışında StockWidget'i başlat"; GroupDescription: "Başlangıç:"

[Files]
Source: "..\dist\{#MyAppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--toggle"; Check: CanCreateShortcuts
Name: "{group}\{#MyAppName} kaldır"; Filename: "{uninstallexe}"; Check: CanCreateShortcuts
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--toggle"; Tasks: desktopicon; Check: CanCreateDesktopIcon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--quit"; Flags: runhidden; RunOnceId: "StockWidgetQuit"

[Code]
var
  ShortcutsAllowed: Boolean;
  DesktopIconAllowed: Boolean;

{ Yazılabilirlik denemesi: klasöre geçici dosya bırakıp siler. }
function CanWriteToDir(const Dir: String): Boolean;
var
  Probe: String;
begin
  Result := False;
  try
    if not ForceDirectories(Dir) then
      Exit;
    Probe := AddBackslash(Dir) + 'sw_probe.tmp';
    if SaveStringToFile(Probe, 'x', False) then
    begin
      DeleteFile(Probe);
      Result := True;
    end;
  except
    Result := False;
  end;
end;

{ HKCU'ya yazabiliyor muyuz? Kurumsal kısıtlamaları önceden yakalar. }
function CanWriteRegistry: Boolean;
var
  ProbeKey: String;
begin
  ProbeKey := 'Software\StockWidget';
  Result := RegWriteStringValue(HKEY_CURRENT_USER, ProbeKey, 'InstallProbe', '1');
  if Result then
  begin
    RegDeleteValue(HKEY_CURRENT_USER, ProbeKey, 'InstallProbe');
    RegDeleteKeyIfEmpty(HKEY_CURRENT_USER, ProbeKey);
  end;
end;

function CanCreateShortcuts: Boolean;
begin
  Result := ShortcutsAllowed;
end;

function CanCreateDesktopIcon: Boolean;
begin
  Result := DesktopIconAllowed;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExePath: String;
  AppDirPath: String;
  AppDirExisted: Boolean;
  ResultCode: Integer;
begin
  Result := '';
  AppDirPath := ExpandConstant('{app}');
  AppDirExisted := DirExists(AppDirPath);

  { Yükseltmede çalışan kopya dosyaları kilitlemesin: temiz çıkış iste. }
  ExePath := ExpandConstant('{app}\{#MyAppExeName}');
  if FileExists(ExePath) then
  begin
    Exec(ExePath, '--quit', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(1500);
  end;

  { Kısıtlı (kurumsal) makinelerde Inno'nun ham "Error 5" hatası yerine
    ne yapılacağını söyleyen net bir mesaj göster. }
  if not CanWriteToDir(AppDirPath) then
  begin
    if not AppDirExisted then
      RemoveDir(AppDirPath);
    Result := 'Kurulum klasörüne yazılamıyor:' + #13#10 +
      ExpandConstant('{app}') + #13#10#13#10 +
      'Bu makinede bu klasöre yazma izni yok (kurumsal kısıtlama olabilir).' + #13#10 +
      'Kurulum yerine portatif ZIP sürümünü kullanabilirsiniz:' + #13#10 +
      '{#MyAppURL}/releases/latest';
    Exit;
  end;

  if not CanWriteRegistry then
  begin
    if not AppDirExisted then
      RemoveDir(AppDirPath);
    Result := 'Windows kayıt defterine (HKCU) yazılamıyor.' + #13#10#13#10 +
      'Bu makinede kurulum izni yok (kurumsal kısıtlama olabilir).' + #13#10 +
      'Kurulum yerine portatif ZIP sürümünü kullanabilirsiniz:' + #13#10 +
      '{#MyAppURL}/releases/latest';
    Exit;
  end;

  { Kısayollar zorunlu değil: yazılamıyorsa kurulumu düşürmeyelim. }
  ShortcutsAllowed := CanWriteToDir(ExpandConstant('{autoprograms}'));
  DesktopIconAllowed := CanWriteToDir(ExpandConstant('{autodesktop}'));
  if not ShortcutsAllowed then
    Log('UYARI: Başlat menüsü yazılamıyor; kısayollar atlanacak.');
  if not DesktopIconAllowed then
    Log('UYARI: Masaüstü yazılamıyor; masaüstü kısayolu atlanacak.');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and (not ShortcutsAllowed) and
     (not WizardSilent) then
    SuppressibleMsgBox('Kısayollar oluşturulamadı: bu makinede Başlat menüsü' +
      ' yazılamıyor.' + #13#10 + 'Programı doğrudan şuradan çalıştırabilirsiniz:' + #13#10 +
      ExpandConstant('{app}\{#MyAppExeName}'), mbInformation, MB_OK, IDOK);
end;
