; StockWidget - Inno Setup 6 betiği
; Derleme: ISCC.exe installer.iss  (veya /DMyAppVersion=1.2.3)
; Çıktı:   Output\StockWidget-<sürüm>-setup.exe
;
; Kurulum kullanıcı bazlıdır (yönetici gerekmez):
;   program : %LOCALAPPDATA%\Programs\StockWidget
;   veri    : %APPDATA%\StockWidget            (kaldırmada korunur)
;   kayıt   : HKCU\Software\Microsoft\Windows\CurrentVersion\Run

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
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
OutputDir=Output
OutputBaseFilename={#MyAppName}-{#MyAppVersion}-setup
SetupIconFile=stock.ico
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
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Windows açılışında StockWidget'i başlat"; GroupDescription: "Başlangıç:"

[Files]
Source: "dist\{#MyAppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} kaldır"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--quit"; Flags: runhidden; RunOnceId: "StockWidgetQuit"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExePath: String;
  ResultCode: Integer;
begin
  Result := '';
  ExePath := ExpandConstant('{app}\{#MyAppExeName}');
  if FileExists(ExePath) then
  begin
    { Yükseltmede çalışan kopya dosyaları kilitlemesin: temiz çıkış iste. }
    Exec(ExePath, '--quit', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(1500);
  end;
end;
