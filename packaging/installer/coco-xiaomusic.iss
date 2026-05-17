#define MyAppName "coco-xiaomusic"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Flames1217"
#define MyAppExeName "coco-xiaomusic.exe"

[Setup]
AppId={{6E7406D1-BE4D-4A46-8F8E-4F94E96E0F2C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
SetupIconFile=..\..\assets\logo.ico
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\release
OutputBaseFilename=coco-xiaomusic-setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标："; Flags: unchecked

[Files]
Source: "..\..\dist\coco-xiaomusic\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\coco-xiaomusic"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\coco-xiaomusic"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 coco-xiaomusic"; Flags: nowait postinstall skipifsilent
