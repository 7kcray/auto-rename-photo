# Windows 内置 OCR：一批 PNG → 每张图的文本行，写成 JSON。
#
# 由 autorename/ocr.py 调用，不单独使用。参数：
#   -Out  <路径>   结果 JSON 写到这里
#   <路径...>      待识别的图片，按顺序回填
#
# 单张图识别失败就给它空串，不让一张坏图毁掉整批。
# 引擎起不来时写空数组：Python 那边会当作「全部未定」，人照样能手点。

param(
    [Parameter(Mandatory = $true)][string]$Out,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Paths
)

$ErrorActionPreference = 'Stop'

function Write-Texts([string[]]$Texts) {
    $payload = [pscustomobject]@{ texts = @($Texts) }
    $json = ConvertTo-Json -InputObject $payload -Compress -Depth 3
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Out, $json, $encoding)
}

try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime

    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and
        $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    })[0]

    function Await($Operation, $ResultType) {
        $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
        $netTask = $asTask.Invoke($null, @($Operation))
        $netTask.Wait(-1) | Out-Null
        $netTask.Result
    }

    [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
    [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
    [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime] | Out-Null
    [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics, ContentType = WindowsRuntime] | Out-Null
    [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null

    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if (-not $engine) {
        Write-Texts @()
        exit 0
    }
}
catch {
    Write-Texts @()
    exit 0
}

$texts = @()
foreach ($path in $Paths) {
    $text = ''
    try {
        $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
        $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

        $lines = @()
        foreach ($line in $result.Lines) { $lines += $line.Text }
        $text = $lines -join "`n"

        $bitmap.Dispose()
        $stream.Dispose()
    }
    catch {
        $text = ''
    }
    $texts += $text
}

Write-Texts $texts
