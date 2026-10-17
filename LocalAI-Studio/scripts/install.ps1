# 로컬 AI 스튜디오 설치 스크립트
# 엔진(ComfyUI 포터블 + Ollama)만 설치합니다. 모델은 웹 화면의 "설치와 모델" 탭에서 고릅니다.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Expand-Archive / Invoke-RestMethod 속도 개선
[Console]::OutputEncoding = [Text.Encoding]::UTF8
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}   # PowerShell 5.1 + GitHub

$root = Split-Path -Parent $PSScriptRoot
$dl   = Join-Path $root 'downloads'
$eng  = Join-Path $root 'engine'
New-Item -ItemType Directory -Force -Path $dl, $eng | Out-Null

function Get-File([string]$url, [string]$out) {
    if (Test-Path $out) { Write-Host "  (이미 받음) $(Split-Path -Leaf $out)"; return }
    Write-Host "  다운로드: $url"
    # curl.exe 는 Windows 10 1803 이상에 기본 포함. -C - 로 끊긴 지점부터 이어받습니다.
    & curl.exe -L --fail --retry 5 --retry-delay 3 -C - -o "$out.part" $url
    if ($LASTEXITCODE -ne 0) { throw "다운로드 실패: $url  (인터넷 연결을 확인하고 install.bat 을 다시 실행하면 이어받습니다)" }
    Move-Item -Force "$out.part" $out
}

# GitHub 최신 릴리스에서 파일 이름 패턴으로 주소를 찾고, 실패하면 기본 주소를 씁니다(파일 이름이 바뀌어도 견디도록).
function Get-AssetUrl([string]$repo, [string]$pattern, [string]$fallback) {
    try {
        $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/releases/latest" -Headers @{ 'User-Agent' = 'LocalAI-Studio' }
        $hit = @($rel.assets | Where-Object { $_.name -like $pattern }) | Sort-Object { $_.name.Length } | Select-Object -First 1
        if ($hit) { return $hit.browser_download_url }
    } catch {}
    return $fallback
}

Write-Host ""
Write-Host "=== 로컬 AI 스튜디오 설치 ===" -ForegroundColor Cyan

# 사전 점검
if ($root -match '[^\x00-\x7F]' -or $root -match '\s') {
    Write-Warning "설치 경로에 한글/공백이 있습니다 ($root). 일부 도구가 오작동할 수 있으니 C:\LocalAI 처럼 영문 경로를 권장합니다."
}
if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    Write-Warning "NVIDIA GPU/드라이버를 찾지 못했습니다. 이미지 기능은 매우 느리거나 동작하지 않을 수 있습니다."
}
try {
    $free = (Get-PSDrive -Name $root.Substring(0,1)).Free / 1GB
    Write-Host ("  설치 드라이브 여유 공간: {0:N0} GB (엔진 약 17GB, 모델까지 설치하려면 60GB 이상 권장)" -f $free)
    if ($free -lt 20) { Write-Warning "여유 공간이 부족합니다." }
} catch {}

# 1) ComfyUI 포터블 (파이썬/토치 포함)
Write-Host "`n[1/2] 이미지 엔진: ComfyUI 포터블"
$comfy = Join-Path $eng 'ComfyUI_windows_portable'
if (Test-Path "$comfy\python_embeded\python.exe") {
    Write-Host "  이미 설치되어 있습니다."
} else {
    $url = Get-AssetUrl 'comfyanonymous/ComfyUI' 'ComfyUI_windows_portable_nvidia*.7z' 'https://github.com/comfyanonymous/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z'
    Get-File 'https://www.7-zip.org/a/7zr.exe' "$dl\7zr.exe"
    Get-File $url "$dl\comfyui.7z"
    Write-Host "  압축 해제 중... (몇 분 걸립니다)"
    & "$dl\7zr.exe" x -y "-o$eng" "$dl\comfyui.7z" | Out-Null
    if (-not (Test-Path "$comfy\python_embeded\python.exe")) { throw "ComfyUI 압축 해제에 실패했습니다. (디스크 공간을 확인하세요)" }
    Remove-Item "$dl\comfyui.7z" -ErrorAction SilentlyContinue
}

# 2) Ollama (대화 엔진)
Write-Host "`n[2/2] 대화 엔진: Ollama"
if (Test-Path "$eng\ollama\ollama.exe") {
    Write-Host "  이미 설치되어 있습니다."
} else {
    Get-File 'https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip' "$dl\ollama.zip"
    Expand-Archive -Force -Path "$dl\ollama.zip" -DestinationPath "$eng\ollama"
    if (-not (Test-Path "$eng\ollama\ollama.exe")) { throw "Ollama 압축 해제에 실패했습니다. (디스크 공간을 확인하세요)" }
    Remove-Item "$dl\ollama.zip" -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "엔진 설치 완료!" -ForegroundColor Green
Write-Host "다음 순서로 진행하세요:"
Write-Host "  1. start.bat 실행 -> 브라우저에서 스튜디오가 열립니다."
Write-Host "  2. 왼쪽 메뉴의 [설치와 모델] 탭에서 '내 GPU에 맞춰 고르기' -> '선택한 항목 설치'"
