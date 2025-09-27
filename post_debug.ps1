$ErrorActionPreference = 'Stop'

function Do-Post($url, $bodyJson, $headers) {
    Write-Host "POST -> $url"
    try {
        $r = Invoke-RestMethod -Uri $url -Method Post -Body $bodyJson -ContentType 'application/json' -Headers $headers -TimeoutSec 30
        Write-Host "Status: 200 (OK)"
        Write-Host "Body:`n" ($r | ConvertTo-Json -Depth 10)
    } catch {
        # Try to extract response body from the exception if present
        $e = $_.Exception
        Write-Host "Exception message: " $e.Message
        if ($e.Response) {
            try {
                $respStream = $e.Response.GetResponseStream()
                $sr = New-Object System.IO.StreamReader($respStream)
                $content = $sr.ReadToEnd()
                Write-Host "Response body:`n$content"
            } catch {
                Write-Host "Could not read response body: $($_.Exception.Message)"
            }
        }
    }
    Write-Host "----------`n"
}

$ngrok = 'https://multiplicative-unapprehendably-marisha.ngrok-free.dev/bridge/link_echo_generate/echo_generate'

$payloads = @(
    @{ prompt = 'debug test minimal' } ,
    @{ prompt = 'debug with model' ; model = 'gpt-4o-mini' },
    @{ prompt = 'with contextIds int list' ; contextIds = @(1,2,3) },
    @{ prompt = 'with contextIds as strings' ; contextIds = @('a','b') }
)

# Try without X-API-Key
foreach ($p in $payloads) {
    $body = $p | ConvertTo-Json -Depth 5
    Do-Post $ngrok $body @{}
}

# Try with X-API-Key header
$hdr = @{ 'X-API-Key' = 'SECRET' }
foreach ($p in $payloads) {
    $body = $p | ConvertTo-Json -Depth 5
    Do-Post $ngrok $body $hdr
}
