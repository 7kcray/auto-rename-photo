# Windows 内置 OCR：一批 PNG → 每张图的文本行，写成 JSON。
#
# 由 autorename/ocr.py 调用，不单独使用。参数：
#   -Out  <路径>   结果 JSON 写到这里
#   <路径...>      待识别的图片，按顺序回填
#
# 单张图识别失败就给它空串，不让一张坏图毁掉整批。
# 引擎起不来时写空数组：Python 那边会当作「全部未定」，人照样能手点。
#
# 截图里的路径文字（`\\TCSB2\eStream\...`、`C:\eStream\...`）只有几个像素高，
# 原生尺寸下引擎读不出来；先按 2 倍 Cubic 放大再识别，ENV 线索才有据可依。
# 放大失败或超出引擎上限就退回原生尺寸。

param(
    [Parameter(Mandatory = $true)][string]$Out,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Paths
)

$ErrorActionPreference = 'Stop'
$OcrScale = 2.0

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
    [Windows.Graphics.Imaging.BitmapTransform, Windows.Graphics, ContentType = WindowsRuntime] | Out-Null
    [Windows.Graphics.Imaging.PixelDataProvider, Windows.Graphics, ContentType = WindowsRuntime] | Out-Null
    [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics, ContentType = WindowsRuntime] | Out-Null
    [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null

    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if (-not $engine) {
        Write-Texts @()
        exit 0
    }

    function Get-ScaledBitmap($Decoder) {
        $limit = [Windows.Media.Ocr.OcrEngine]::MaxImageDimension
        $width = [uint32]([math]::Round($Decoder.PixelWidth * $OcrScale))
        $height = [uint32]([math]::Round($Decoder.PixelHeight * $OcrScale))
        if ($width -gt $limit -or $height -gt $limit) {
            throw 'scaled image is larger than the OCR engine allows'
        }

        $transform = New-Object Windows.Graphics.Imaging.BitmapTransform
        $transform.ScaledWidth = $width
        $transform.ScaledHeight = $height
        $transform.InterpolationMode = [Windows.Graphics.Imaging.BitmapInterpolationMode]::Cubic

        $provider = Await ($Decoder.GetPixelDataAsync(
            [Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8,
            [Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied,
            $transform,
            [Windows.Graphics.Imaging.ExifOrientationMode]::IgnoreExifOrientation,
            [Windows.Graphics.Imaging.ColorManagementMode]::DoNotColorManage
        )) ([Windows.Graphics.Imaging.PixelDataProvider])

        $buffer = [System.Runtime.InteropServices.WindowsRuntime.WindowsRuntimeBufferExtensions]::AsBuffer(
            $provider.DetachPixelData()
        )
        [Windows.Graphics.Imaging.SoftwareBitmap]::CreateCopyFromBuffer(
            $buffer,
            [Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8,
            $width,
            $height,
            [Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied
        )
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

        $bitmap = $null
        try {
            $bitmap = Get-ScaledBitmap $decoder
        }
        catch {
            $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        }

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
