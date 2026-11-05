param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'VexxPC\app'),
    [string]$PythonExecutable,
    [string]$WheelDirectory,
    [string]$LogPath,
    [switch]$SkipLaunch,
    [switch]$NoShortcut
)
$ErrorActionPreference = 'Stop'
if ($LogPath) { Start-Transcript -LiteralPath $LogPath -Append | Out-Null }
$sourceRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$targetRoot = [IO.Path]::GetFullPath($InstallRoot)
if ($targetRoot -eq $sourceRoot) { throw 'Escolha outra pasta de instalacao, fora do pacote extraido.' }

function Find-Python {
    # Missing launcher versions are candidates to skip, not fatal install errors.
    $ErrorActionPreference = 'Continue'
    $candidates = @()
    if ($PythonExecutable) { $candidates += $PythonExecutable }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($version in @('-3.13','-3.12','-3')) {
            $candidate = & $launcher.Source $version -c 'import sys; print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $candidate) { $candidates += [string]$candidate }
        }
    }
    foreach ($version in @('313','312')) {
        $candidates += (Join-Path $env:LOCALAPPDATA "Programs\Python\Python$version\python.exe")
    }
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notmatch 'WindowsApps') { $candidates += $command.Source }
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (Test-Path -LiteralPath $candidate) {
            'import sys, sqlite3; assert (3,12) <= sys.version_info[:2] < (3,15); c=sqlite3.connect(":memory:"); c.execute("CREATE VIRTUAL TABLE t USING fts5(name, tokenize=trigram)")' | & $candidate - 2>$null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        }
    }
    return $null
}

Write-Host 'Vexx PC - instalacao para o usuario atual'
Write-Host 'Instala o aplicativo e cria um atalho. Seus dados ficam em %LOCALAPPDATA%\VexxPC.'
$runtimePython = Find-Python
if (-not $runtimePython) {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) { throw 'Instale Python 3.13 em https://www.python.org/downloads/windows/ e execute novamente.' }
    Write-Host 'Instalando Python pela fonte winget. O Windows pode solicitar confirmacao.'
    & $winget.Source install --id Python.Python.3.13 --exact --source winget --scope user --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel instalar Python. Instale pelo site python.org e tente novamente.' }
    $runtimePython = Find-Python
    if (-not $runtimePython) { throw 'Python nao encontrado. Feche e execute o instalador novamente.' }
}

New-Item -ItemType Directory -Path $targetRoot -Force | Out-Null
$versionSource = Get-Content -LiteralPath (Join-Path $PSScriptRoot '__init__.py') -Raw
$releaseVersion = [regex]::Match($versionSource, '__version__\s*=\s*[''"]([0-9.]+)[''"]').Groups[1].Value
if (-not $releaseVersion) { throw 'Versao do pacote invalida.' }
$releaseRoot = Join-Path $targetRoot ('releases\' + $releaseVersion + '-' + [guid]::NewGuid().ToString('N').Substring(0,12))
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
$targetPackage = Join-Path $releaseRoot 'pc_companion'
New-Item -ItemType Directory -Path $targetPackage -Force | Out-Null
# Package code only; never copy the source repository, environment or private data.
foreach ($name in @('__init__.py','__main__.py','app.py','system.py','indexer.py','connection.py','release.py','updater.py','apply_update.py','launcher.py','desktop.py','ai.py','files.py','projects.py','project_host.py','process_group.py','requirements.txt','README.md','Instalar.cmd','instalar.ps1')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $targetPackage $name) -Force
}
$webTarget = Join-Path $targetPackage 'web'
New-Item -ItemType Directory -Path $webTarget -Force | Out-Null
foreach ($name in @('index.html','style.css','app.js','workspace.js')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "web\$name") -Destination (Join-Path $webTarget $name) -Force
}
Copy-Item -LiteralPath (Join-Path $sourceRoot 'remoto.py') -Destination (Join-Path $releaseRoot 'remoto.py') -Force
$venvPath = Join-Path $releaseRoot '.venv'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $runtimePython -m venv $venvPath
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar o ambiente isolado.' }
}
$pipArgs = @('-m','pip','install','--disable-pip-version-check')
if ($WheelDirectory) {
    if (-not (Test-Path -LiteralPath $WheelDirectory -PathType Container)) { throw 'Dependencias do instalador ausentes.' }
    $pipArgs += @('--no-index','--find-links',$WheelDirectory)
}
& $venvPython @pipArgs -r (Join-Path $targetPackage 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Falha nas dependencias. Verifique sua internet e execute novamente.' }
Push-Location -LiteralPath $releaseRoot
try {
    'from pc_companion.app import create_app; import mss, PIL, psutil; print("Dependencias verificadas.")' | & $venvPython -
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao verificar a instalacao.' }
} finally { Pop-Location }

$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText((Join-Path $releaseRoot 'installation.json'), (@{install_root=$targetRoot;version=$releaseVersion} | ConvertTo-Json), $utf8)
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'launcher.py') -Destination (Join-Path $targetRoot 'launch.py') -Force
$pointer = @{release=('releases/' + (Split-Path -Leaf $releaseRoot));version=$releaseVersion} | ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $targetRoot 'current.tmp'), $pointer, $utf8)
Move-Item -LiteralPath (Join-Path $targetRoot 'current.tmp') -Destination (Join-Path $targetRoot 'current.json') -Force
$launchPython = Join-Path (Split-Path -Parent $runtimePython) 'pythonw.exe'
if (-not $NoShortcut) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Vexx PC.lnk'
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $launchPython
    $shortcut.Arguments = '"' + (Join-Path $targetRoot 'launch.py') + '"'
    $shortcut.WorkingDirectory = $targetRoot
    $shortcut.Description = 'Abrir Vexx PC - recursos, arquivos e acesso pela sua conta'
    $shortcut.Save()
}
Write-Host 'Vexx PC instalado. Abra pelo atalho na area de trabalho.'
if (-not $SkipLaunch) {
    Start-Process -FilePath $launchPython -ArgumentList @('"' + (Join-Path $targetRoot 'launch.py') + '"') -WorkingDirectory $targetRoot -WindowStyle Hidden
}
if ($LogPath) { Stop-Transcript | Out-Null }
