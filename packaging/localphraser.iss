; Compile the validated onedir build with Inno Setup 6.3 or newer.
#ifndef BuildDir
  #define BuildDir "..\dist\LocalPhraser"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist\packages"
#endif

[Setup]
AppId={{D7CE5E21-B4FD-498E-AE52-FB1566E2944C}
AppName=LocalPhraser
AppVersion=0.1.0a1
AppPublisher=Robert Backe
AppPublisherURL=https://github.com/RobertBacke/LocalPhraser
DefaultDirName={localappdata}\Programs\LocalPhraser
DefaultGroupName=LocalPhraser
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=LocalPhraser-0.1.0a1-windows-x64-setup-preview
UninstallDisplayIcon={app}\LocalPhraser.exe
LicenseFile=..\LICENSE
InfoBeforeFile=START_HERE.txt
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "START_HERE.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\LocalPhraser"; Filename: "{app}\LocalPhraser.exe"
Name: "{userdesktop}\LocalPhraser"; Filename: "{app}\LocalPhraser.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\LocalPhraser.exe"; Description: "Launch LocalPhraser"; Flags: nowait postinstall skipifsilent unchecked

[Code]
// Preserve settings/models and startup entries belonging to other installations.
function ExecutableFromCommand(Command: String): String;
var
  Separator: Integer;
begin
  Result := '';
  if Command = '' then Exit;
  if Command[1] = '"' then
  begin
    Delete(Command, 1, 1);
    Separator := Pos('"', Command);
    if Separator = 0 then Exit;
    Result := Copy(Command, 1, Separator - 1);
  end
  else
  begin
    Separator := Pos(' ', Command);
    if Separator = 0 then Result := Command
    else Result := Copy(Command, 1, Separator - 1);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Names: TArrayOfString;
  Index: Integer;
  Command: String;
  RunKey: String;
begin
  if CurUninstallStep <> usUninstall then Exit;
  RunKey := 'Software\Microsoft\Windows\CurrentVersion\Run';
  if not RegGetValueNames(HKCU, RunKey, Names) then Exit;
  for Index := 0 to GetArrayLength(Names) - 1 do
    if Copy(Names[Index], 1, 13) = 'LocalPhraser-' then
      if RegQueryStringValue(HKCU, RunKey, Names[Index], Command) then
        if CompareText(ExecutableFromCommand(Command),
          ExpandConstant('{app}\LocalPhraser.exe')) = 0 then
          if not RegDeleteValue(HKCU, RunKey, Names[Index]) then
            Log('Unable to remove an owned LocalPhraser startup entry.');
end;
