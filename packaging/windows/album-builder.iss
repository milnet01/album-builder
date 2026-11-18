; Album Builder - Windows installer (Spec 24 §4.7, MUSI-0406).
;
; Built by packaging/build-windows.ps1 stage 8 with Inno Setup's ISCC, from the
; one-folder bundle stage 6 made. Not meant to be compiled by hand; the build
; passes these defines:
;   AppVersion  X.Y.Z, read from version.py (INV-24-3)
;   BundleDir   dist\AlbumBuilder (the PyInstaller output)
;   RepoRoot    the checkout
;   OutputDir   dist
;
; Per-user install: no admin prompt, into %LOCALAPPDATA%\Programs. Uninstall
; removes only what this script installed; albums and settings live elsewhere
; (Music\Album Builder, %LOCALAPPDATA%\album-builder) and stay.
;
; Quiet update mode, used by the app's self-update (Spec 28 §4.6 Windows):
;   setup.exe /SILENT /SUPPRESSMSGBOXES /NORESTART /UPDATE /WAITPID=<pid>
; asks nothing, waits for process <pid> (the running app) to exit, installs
; over the existing copy with a progress window, then starts the new version.

#ifndef AppVersion
  #error Define AppVersion, BundleDir, RepoRoot and OutputDir (see the header).
#endif

[Setup]
; Fixed for good: a new AppId would install a second copy beside the first.
AppId={{BB0D823A-7868-439E-A024-4ED224D74686}
AppName=Album Builder
AppVersion={#AppVersion}
AppVerName=Album Builder {#AppVersion}
AppPublisher=milnet01
AppPublisherURL=https://github.com/milnet01/album-builder
AppSupportURL=https://github.com/milnet01/album-builder/issues
AppUpdatesURL=https://github.com/milnet01/album-builder/releases
DefaultDirName={autopf}\Album Builder
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
SetupArchitecture=x64
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=AlbumBuilder-{#AppVersion}-windows-x64-setup
SetupIconFile={#RepoRoot}\packaging\album-builder.ico
UninstallDisplayIcon={app}\AlbumBuilder.exe
UninstallDisplayName=Album Builder
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; An interactive install over a running copy offers to close it.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ar"; MessagesFile: "compiler:Languages\Arabic.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "he"; MessagesFile: "compiler:Languages\Hebrew.isl"
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; The bundle's libraries: replaced whole on every install, so files an older
; version shipped and this one dropped do not linger.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#RepoRoot}\packaging\windows\install-kind.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Album Builder"; Filename: "{app}\AlbumBuilder.exe"
Name: "{autodesktop}\Album Builder"; Filename: "{app}\AlbumBuilder.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\AlbumBuilder.exe"; Description: "{cm:LaunchProgram,Album Builder}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\AlbumBuilder.exe"; Flags: nowait; Check: IsUpdate

[UninstallDelete]
; Anything the app wrote inside its own install folder at run time (such as
; a font cache). User data never lives here (Spec 24 INV-24-4).
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\fontconfig-cache"

[Code]
const
  SYNCHRONIZE = $00100000;
  WAIT_FOR_APP_MS = 120000;

function OpenProcess(DesiredAccess: DWORD; InheritHandle: BOOL; ProcessId: DWORD): THandle;
  external 'OpenProcess@kernel32.dll stdcall';
function WaitForSingleObject(Handle: THandle; Milliseconds: DWORD): DWORD;
  external 'WaitForSingleObject@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): BOOL;
  external 'CloseHandle@kernel32.dll stdcall';

function HasSwitch(const Name: String): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), Name) = 0 then
    begin
      Result := True;
      Exit;
    end;
end;

{ The app's self-update runs Setup with /UPDATE; only then does Setup start
  the new version itself, since nobody is there to tick "Launch". }
function IsUpdate: Boolean;
begin
  Result := HasSwitch('/UPDATE');
end;

{ /WAITPID=<pid>: wait up to WAIT_FOR_APP_MS for the running app to exit
  before touching its files (Spec 24 section 4.7). }
function InitializeSetup: Boolean;
var
  Pid: Integer;
  Process: THandle;
begin
  Result := True;
  Pid := StrToIntDef(ExpandConstant('{param:WAITPID|0}'), 0);
  if Pid > 0 then
  begin
    Process := OpenProcess(SYNCHRONIZE, False, Pid);
    if Process <> 0 then
    begin
      WaitForSingleObject(Process, WAIT_FOR_APP_MS);
      CloseHandle(Process);
    end;
  end;
end;
