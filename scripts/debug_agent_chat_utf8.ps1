param(
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Convert-ToUnicodeEscape {
    param([AllowNull()][string]$Text)

    if ($null -eq $Text) {
        return ""
    }

    $builder = [System.Text.StringBuilder]::new()
    foreach ($char in $Text.ToCharArray()) {
        $codePoint = [int][char]$char
        if ($codePoint -ge 32 -and $codePoint -le 126 -and $char -ne '\' -and $char -ne '"') {
            [void]$builder.Append($char)
        } else {
            [void]$builder.Append(('\u{0:x4}' -f $codePoint))
        }
    }
    return $builder.ToString()
}

$diagnostics = Invoke-RestMethod `
    -Method GET `
    -Uri "$BaseUrl/agent/chat/diagnostics/encoding"

Write-Host "diagnostics.status=$($diagnostics.status)"
Write-Host "diagnostics.sample_korean=$($diagnostics.sample_korean)"
Write-Host "diagnostics.sample_unicode_escape=$($diagnostics.sample_unicode_escape)"

$json = @'
{
  "conversation_key": null,
  "message": "\uC0BC\uC131\uC804\uC790 \uD604\uC7AC\uAC00 \uC5BC\uB9C8\uC57C?",
  "context": {
    "default_market": "KR",
    "default_provider": "kis",
    "timezone": "Asia/Seoul"
  },
  "auto_create_conversation": true
}
'@

$bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
$response = Invoke-RestMethod `
    -Method POST `
    -Uri "$BaseUrl/agent/chat/send" `
    -ContentType "application/json; charset=utf-8" `
    -Body $bytes

Write-Host "intent.category=$($response.intent.category)"
Write-Host "intent.symbol=$($response.intent.symbol)"
Write-Host "answer.text=$($response.answer.text)"
Write-Host "answer.text.unicode_escape=$(Convert-ToUnicodeEscape $response.answer.text)"
Write-Host "safety.real_order_submitted=$($response.safety.real_order_submitted)"
Write-Host "safety.validation_called=$($response.safety.validation_called)"
Write-Host "safety.setting_changed=$($response.safety.setting_changed)"
Write-Host "safety.scheduler_changed=$($response.safety.scheduler_changed)"
Write-Host "diagnostics.encoding_safe=$($response.diagnostics.encoding_safe)"
