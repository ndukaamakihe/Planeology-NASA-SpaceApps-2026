# Planalogy: a small web server for the app folder, then the browser opens.
# Started by "Start Planalogy.bat". Needs nothing but Windows PowerShell. Close this window to stop.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\web\app')).Path
$types = @{ '.html'='text/html; charset=utf-8'; '.js'='text/javascript; charset=utf-8'; '.css'='text/css; charset=utf-8';
            '.json'='application/json'; '.gz'='application/octet-stream'; '.jpg'='image/jpeg'; '.jpeg'='image/jpeg';
            '.png'='image/png'; '.svg'='image/svg+xml'; '.woff2'='font/woff2'; '.ico'='image/x-icon'; '.mp4'='video/mp4' }

$listener = $null
foreach ($port in 8642..8660) {
  try {
    $l = New-Object System.Net.HttpListener
    $l.Prefixes.Add("http://localhost:$port/")
    $l.Start(); $listener = $l; break
  } catch { }
}
if (-not $listener) { Write-Host 'No free port between 8642 and 8660. Close other programs and try again.'; Read-Host 'Press Enter to close'; exit 1 }

$url = $listener.Prefixes | Select-Object -First 1
Write-Host ''
Write-Host '  PLANALOGY is running at' $url
Write-Host '  Your browser opens by itself. Close this window to stop.'
Write-Host ''
Start-Process $url

while ($listener.IsListening) {
  $ctx = $listener.GetContext()
  $res = $ctx.Response
  try {
    $path = [Uri]::UnescapeDataString($ctx.Request.Url.AbsolutePath).TrimStart('/')
    if ($path -eq '') { $path = 'index.html' }
    $file = [IO.Path]::GetFullPath((Join-Path $root $path))
    if (-not $file.StartsWith($root) -or -not (Test-Path $file -PathType Leaf)) {
      $res.StatusCode = 404; $bytes = [Text.Encoding]::UTF8.GetBytes('Not found')
    } else {
      $ext = [IO.Path]::GetExtension($file).ToLower()
      $res.ContentType = if ($types.ContainsKey($ext)) { $types[$ext] } else { 'application/octet-stream' }
      $bytes = [IO.File]::ReadAllBytes($file)
    }
    $res.Headers.Add('Cache-Control', 'no-cache')
    $res.ContentLength64 = $bytes.Length
    $res.OutputStream.Write($bytes, 0, $bytes.Length)
  } catch { } finally { $res.Close() }
}
