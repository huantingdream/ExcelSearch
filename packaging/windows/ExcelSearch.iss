#define AppName "ExcelSearch"
#define AppVersion "0.1.0"
#define AppPublisher "ExcelSearch"
#define ProjectRoot SourcePath + "\..\.."

[Setup]
AppId={{B1ED13E6-1838-42C0-B660-29CEBB42A096}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#ProjectRoot}\release
OutputBaseFilename=ExcelSearch-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupLogging=yes
CloseApplications=yes
UninstallDisplayIcon={app}\ExcelSearch.exe

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Files]
Source: "{#ProjectRoot}\dist\ExcelSearch\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\ExcelSearch"; Filename: "{app}\ExcelSearch.exe"
Name: "{autodesktop}\ExcelSearch"; Filename: "{app}\ExcelSearch.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项："

[Run]
Filename: "{app}\ExcelSearch.exe"; Description: "启动 ExcelSearch"; Flags: nowait postinstall skipifsilent
