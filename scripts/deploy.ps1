# scripts/deploy.ps1
# Деплой сайта на GitHub Pages в один клик.
#
# Что делает:
#   1. Проверяет что Git установлен
#   2. Инициализирует репозиторий (если ещё не)
#   3. Настраивает remote на GitHub (если ещё не)
#   4. Делает add/commit/push
#   5. Открывает настройки Pages в браузере
#
# Использование:
#   powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1

$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')  # переходим в корень проекта

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "✓ $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "⚠ $msg" -ForegroundColor Yellow }
function Err($msg)  { Write-Host "✗ $msg" -ForegroundColor Red }

# === 1. Проверка Git ===
Step "1/5 Проверка Git"
# Если git не в PATH (типично сразу после установки), пробуем стандартные пути
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    $candidates = @(
        "C:\Program Files\Git\bin\git.exe"
        "C:\Program Files (x86)\Git\bin\git.exe"
        "$env:LOCALAPPDATA\Programs\Git\bin\git.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) {
            $env:PATH = (Split-Path $p) + ";" + $env:PATH
            break
        }
    }
}
try {
    $v = (& git --version) 2>&1
    if ($LASTEXITCODE -ne 0) { throw "git not found" }
    Ok $v
} catch {
    Err "Git не установлен. Скачай: https://git-scm.com/download/win"
    Write-Host "После установки Git запусти этот скрипт снова."
    pause
    exit 1
}

# === 2. Инициализация репозитория ===
Step "2/5 Инициализация репозитория"
if (-not (Test-Path .git)) {
    & git init | Out-Null
    & git branch -M main
    Ok "git init выполнен"

    # Настройка user.name / user.email (если глобально не заданы)
    if (-not (& git config user.name 2>$null)) {
        $name = Read-Host "Введи имя для коммитов (например: Boris I)"
        & git config user.name $name
    }
    if (-not (& git config user.email 2>$null)) {
        $email = Read-Host "Введи email (тот же что на GitHub)"
        & git config user.email $email
    }
} else {
    Ok "репозиторий уже инициализирован"
}

# === 3. Настройка remote ===
Step "3/5 Подключение к GitHub"
$remote = & git remote get-url origin 2>$null
if (-not $remote) {
    Warn "Сначала создай пустой репозиторий:"
    Write-Host "  • Открой https://github.com/new" -ForegroundColor White
    Write-Host "  • Name: 3d-landing (или любое)" -ForegroundColor White
    Write-Host "  • Public: ✓" -ForegroundColor White
    Write-Host "  • НЕ ставь 'Add a README file'" -ForegroundColor White
    Write-Host ""

    $open = Read-Host "Открыть страницу создания репо в браузере? (y/n)"
    if ($open -eq 'y') { Start-Process "https://github.com/new" }

    Write-Host ""
    $username = Read-Host "Твой GitHub username"
    $reponame = Read-Host "Имя репо (Enter = 3d-landing)"
    if ([string]::IsNullOrWhiteSpace($reponame)) { $reponame = "3d-landing" }

    $remoteUrl = "https://github.com/$username/$reponame.git"
    & git remote add origin $remoteUrl
    Ok "remote добавлен: $remoteUrl"
} else {
    Ok "remote уже настроен: $remote"
}

# === 4. .gitignore (если нет) ===
if (-not (Test-Path .gitignore)) {
    @'
# OS junk
Thumbs.db
.DS_Store
desktop.ini

# Editor
.vscode/
.idea/
*.swp
*.swo

# Local temp
_inbox/
*.bak
'@ | Out-File -FilePath .gitignore -Encoding utf8
    Ok "создан .gitignore"
}

# === 5. Add / Commit / Push ===
Step "4/5 Коммит и отправка на GitHub"
& git add .

$status = (& git status --porcelain) 2>&1
if ($status) {
    $msg = Read-Host "Комментарий к коммиту (Enter = 'Update site')"
    if ([string]::IsNullOrWhiteSpace($msg)) { $msg = "Update site" }
    & git commit -m $msg | Out-Null
    Ok "коммит создан"
} else {
    Warn "нет изменений для коммита (всё уже синхронизировано)"
}

Write-Host ""
Write-Host "Пушинг в GitHub..." -ForegroundColor Cyan
try {
    & git push -u origin main 2>&1 | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) { throw "push failed" }
    Ok "push успешен"
} catch {
    Err "Push не удался"
    Write-Host ""
    Write-Host "Возможные причины:" -ForegroundColor Yellow
    Write-Host "  1. Репозиторий не создан на GitHub — открой https://github.com/new" -ForegroundColor White
    Write-Host "  2. Нужен Personal Access Token вместо пароля:" -ForegroundColor White
    Write-Host "     https://github.com/settings/tokens → Generate new token (classic)" -ForegroundColor White
    Write-Host "     → выбери 'repo' → Generate → скопируй токен" -ForegroundColor White
    Write-Host "     → используй токен как пароль при push" -ForegroundColor White
    Write-Host "  3. Неверный username — проверь что https://github.com/ТВОЙ_ЮЗЕР/$reponame существует" -ForegroundColor White
    pause
    exit 1
}

# === 6. Открыть настройки Pages ===
Step "5/5 Включение GitHub Pages"
$remoteUrl = (& git remote get-url origin).Trim()
if ($remoteUrl -match 'github\.com[/:]([^/]+)/([^/.]+?)(?:\.git)?$') {
    $username = $Matches[1]
    $reponame = $Matches[2]
    $pagesUrl = "https://github.com/$username/$reponame/settings/pages"
    $siteUrl  = "https://$username.github.io/$reponame"

    Warn "Осталось включить Pages в браузере (открою автоматически)..."
    Start-Sleep -Seconds 2
    Start-Process $pagesUrl

    Write-Host ""
    Write-Host "В браузере:" -ForegroundColor Cyan
    Write-Host "  1. Source: Deploy from a branch" -ForegroundColor White
    Write-Host "  2. Branch: main   |   Folder: / (root)" -ForegroundColor White
    Write-Host "  3. Нажми Save" -ForegroundColor White
    Write-Host ""
    Write-Host "Через 1-2 минуты сайт будет доступен по адресу:" -ForegroundColor Cyan
    Write-Host "  $siteUrl" -ForegroundColor Green -BackgroundColor Black
    Write-Host ""
    Write-Host "Для своего домена (3d.ru и т.п.) — потом в том же разделе Pages" -ForegroundColor White
    Write-Host "  указываешь Custom domain и прописываешь DNS у регистратора." -ForegroundColor White
}

Write-Host ""
Ok "Готово!"
pause
