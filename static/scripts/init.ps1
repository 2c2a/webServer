[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$EncodedToken = $args[0]
if (-not $EncodedToken) {
    Write-Host "Usage: & ([ScriptBlock]::Create(`$script)) <token> [debug]" -ForegroundColor Red
    return
}
$Debug = $args[1] -eq 'debug' -or $args[1] -eq '1'

$padLen = 4 - ($EncodedToken.Length % 4)
if ($padLen -ne 4) { $EncodedToken += '=' * $padLen }
try {
    $jsonBytes = [System.Convert]::FromBase64String($EncodedToken)
    $jsonStr = [System.Text.Encoding]::UTF8.GetString($jsonBytes)
    $tokenObj = $jsonStr | ConvertFrom-Json
    $Token = $tokenObj.t
    $Scheme = $tokenObj.s
    $ServerHost = $tokenObj.h
} catch {
    Write-Host "Token解码失败" -ForegroundColor Red; return
}
if (-not $Token -or -not $Scheme -or -not $ServerHost) {
    Write-Host "Token格式无效" -ForegroundColor Red; return
}
$ServerUrl = "${Scheme}://${ServerHost}"
if ($Debug) { Write-Host "  ServerUrl: $ServerUrl" -ForegroundColor DarkGray }

Write-Host "=== 2c2a WinRM 证书自动配置 ===" -ForegroundColor Cyan

Write-Host "[1/17] 验证Token..." -ForegroundColor Yellow
$validateResp = Invoke-RestMethod -Uri "$ServerUrl/bootstrap/api/cert-provision/validate/?token=$Token" -Method Get
if (-not $validateResp.valid) {
    Write-Host "Token无效或已过期" -ForegroundColor Red; return
}
if ($Debug) { Write-Host "  ServerHost: $ServerHost" -ForegroundColor DarkGray }
Write-Host "  Token验证通过" -ForegroundColor Green

Write-Host "[2/17] 上传主机名..." -ForegroundColor Yellow
$hostname = $env:COMPUTERNAME
$body = @{ token = $Token; hostname = $hostname } | ConvertTo-Json
Invoke-RestMethod -Uri "$ServerUrl/bootstrap/api/cert-provision/upload-hostname/" -Method Post -Body $body -ContentType "application/json"
if ($Debug) { Write-Host "  主机名: $hostname" -ForegroundColor DarkGray }
Write-Host "  主机名已上传: $hostname" -ForegroundColor Green

Write-Host "[3/17] 等待证书签发..." -ForegroundColor Yellow
$certData = $null
$maxWait = 120
$waited = 0
while ($waited -lt $maxWait) {
    Start-Sleep -Seconds 5
    $waited += 5
    try {
        $statusResp = Invoke-RestMethod -Uri "$ServerUrl/bootstrap/api/cert-provision/validate/?token=$Token" -Method Get
        if ($Debug) { Write-Host "  Token状态: $($statusResp.status)" -ForegroundColor DarkGray }
    } catch {
        continue
    }
    try {
        $certResp = Invoke-RestMethod -Uri "$ServerUrl/bootstrap/api/cert-provision/download-certs/?token=$Token" -Method Get
        if ($certResp.ca_cert) {
            $certData = $certResp
            break
        }
    } catch {
    }
    Write-Host "  等待中... ($waited/${maxWait}s)" -ForegroundColor DarkGray
}
if (-not $certData) {
    Write-Host "证书签发超时" -ForegroundColor Red; return
}
if ($Debug) { Write-Host "  证书数据已获取" -ForegroundColor DarkGray }
Write-Host "  证书已就绪" -ForegroundColor Green

Write-Host "[4/17] 下载证书文件..." -ForegroundColor Yellow
$TempDir = "$env:TEMP\2c2a_Certs"
New-Item -ItemType Directory -Force -Path $TempDir | Out-Null
[System.IO.File]::WriteAllBytes("$TempDir\ca.crt", [System.Convert]::FromBase64String($certData.ca_cert))
[System.IO.File]::WriteAllBytes("$TempDir\client.crt", [System.Convert]::FromBase64String($certData.client_cert))
[System.IO.File]::WriteAllBytes("$TempDir\server.pfx", [System.Convert]::FromBase64String($certData.server_pfx))
$PfxPassword = $certData.pfx_password
$NtlmUser = $certData.ntlm_user
$NtlmPassword = $certData.ntlm_password
$UpnValue = $certData.upn_value
if ($Debug) { Write-Host "  保存路径: $TempDir" -ForegroundColor DarkGray }
Write-Host "  证书文件已保存到 $TempDir" -ForegroundColor Green

Write-Host "[5/17] 导入证书..." -ForegroundColor Yellow
$tempCa = Import-Certificate -FilePath "$TempDir\ca.crt" -CertStoreLocation Cert:\LocalMachine\Root
$caIssuerPattern = $tempCa.Subject -replace '.*CN=([^,]+).*','$1'
Get-ChildItem Cert:\LocalMachine\Root | Where-Object Subject -match $caIssuerPattern | Remove-Item -Force
$importedCa = Import-Certificate -FilePath "$TempDir\ca.crt" -CertStoreLocation Cert:\LocalMachine\Root
Get-ChildItem Cert:\LocalMachine\My | Where-Object { $_.Issuer -match $caIssuerPattern } | Remove-Item -Force
Get-ChildItem Cert:\LocalMachine\TrustedPeople | Where-Object Subject -match "winrm-client" | Remove-Item -Force
$secPwd = ConvertTo-SecureString $PfxPassword -AsPlainText -Force
$importedServer = Import-PfxCertificate -FilePath "$TempDir\server.pfx" -CertStoreLocation Cert:\LocalMachine\My -Password $secPwd
Import-Certificate -FilePath "$TempDir\client.crt" -CertStoreLocation Cert:\LocalMachine\TrustedPeople
if ($Debug) { Write-Host "  CA Thumbprint: $($importedCa.Thumbprint)" -ForegroundColor DarkGray }
if ($Debug) { Write-Host "  Server Thumbprint: $($importedServer.Thumbprint)" -ForegroundColor DarkGray }
Write-Host "  证书导入完成" -ForegroundColor Green

Write-Host "[6/17] 创建本地用户..." -ForegroundColor Yellow
$SecurePassword = ConvertTo-SecureString $NtlmPassword -AsPlainText -Force
if (-not (Get-LocalUser -Name $NtlmUser -ErrorAction SilentlyContinue)) {
    New-LocalUser -Name $NtlmUser -Password $SecurePassword -Description "2c2a WinRM Certificate Auth User"
} else {
    Set-LocalUser -Name $NtlmUser -Password $SecurePassword
}
Add-LocalGroupMember -Group "Administrators" -Member $NtlmUser -ErrorAction SilentlyContinue
if ($Debug) { Write-Host "  用户: $NtlmUser" -ForegroundColor DarkGray }
Write-Host "  用户 $NtlmUser 已创建" -ForegroundColor Green

Write-Host "[7/17] 配置HTTPS监听器..." -ForegroundColor Yellow
Get-ChildItem WSMan:\localhost\Listener | Where-Object { $_.Keys -match "Transport=HTTPS" } | Remove-Item -Recurse -Force
New-Item -Path WSMan:\localhost\Listener -Transport HTTPS -Address * -CertificateThumbprint $importedServer.Thumbprint -Force
if ($Debug) { Write-Host "  Thumbprint: $($importedServer.Thumbprint)" -ForegroundColor DarkGray }
Write-Host "  监听器已绑定: $($importedServer.Thumbprint)" -ForegroundColor Green

Write-Host "[8/17] 配置客户端证书映射..." -ForegroundColor Yellow
Get-ChildItem WSMan:\localhost\ClientCertificate | Remove-Item -Recurse -Force
$cred = New-Object System.Management.Automation.PSCredential($NtlmUser, $SecurePassword)
New-Item -Path WSMan:\localhost\ClientCertificate -Subject $UpnValue -Issuer $importedCa.Thumbprint -Credential $cred -Force
if ($Debug) { Write-Host "  Subject=$UpnValue Issuer=$($importedCa.Thumbprint)" -ForegroundColor DarkGray }
Write-Host "  映射已建立: Subject=$UpnValue" -ForegroundColor Green

Write-Host "[9/17] 配置Schannel注册表..." -ForegroundColor Yellow
reg add "HKLM\SYSTEM\CurrentControlSet\Control\SecurityProviders\SCHANNEL" /v ClientAuthTrustMode /t REG_DWORD /d 2 /f
reg add "HKLM\SYSTEM\CurrentControlSet\Control\SecurityProviders\SCHANNEL" /v SendTrustedIssuerList /t REG_DWORD /d 0 /f
if ($Debug) { Write-Host "  ClientAuthTrustMode=2, SendTrustedIssuerList=0" -ForegroundColor DarkGray }
Write-Host "  ClientAuthTrustMode=2, SendTrustedIssuerList=0" -ForegroundColor Green

Write-Host "[10/17] 启用证书认证..." -ForegroundColor Yellow
Set-Item -Path WSMan:\localhost\Service\Auth\Certificate -Value $true
Write-Host "  证书认证已启用" -ForegroundColor Green

Write-Host "[11/17] 配置防火墙..." -ForegroundColor Yellow
$FirewallRuleName = "WinRM HTTPS (5986)"
$existingRule = Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue
if (-not $existingRule) {
    New-NetFirewallRule -DisplayName $FirewallRuleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5986
} else {
    Enable-NetFirewallRule -DisplayName $FirewallRuleName
}
if ($Debug) { Write-Host "  规则: $FirewallRuleName" -ForegroundColor DarkGray }
Write-Host "  防火墙已配置" -ForegroundColor Green

Write-Host "[12/17] 重启WinRM服务..." -ForegroundColor Yellow
Restart-Service WinRM -Force
Write-Host "  WinRM服务已重启" -ForegroundColor Green

Write-Host "[13/17] 通知服务器配置完成..." -ForegroundColor Yellow
$notifyBody = @{ token = $Token } | ConvertTo-Json
$notifyResp = $null
$notifyOk = $false
for ($i = 1; $i -le 3; $i++) {
    try {
        $notifyResp = Invoke-RestMethod -Uri "$ServerUrl/bootstrap/api/cert-provision/notify-complete/" -Method Post -Body $notifyBody -ContentType "application/json"
        $notifyOk = $true
        break
    } catch {
        if ($i -lt 3) { Start-Sleep -Seconds 5 }
    }
}
$testDeferred = $false
if ($notifyOk) {
    if ($notifyResp.test -eq "deferred") {
        Write-Host "  已通知服务器（连接测试将在主机注册后执行）" -ForegroundColor Green
        $testDeferred = $true
    } else {
        Write-Host "  已通知服务器" -ForegroundColor Green
    }
} else {
    Write-Host "  通知服务器失败，但本地配置已完成" -ForegroundColor Yellow
    $testDeferred = $true
}

if ($testDeferred) {
    Write-Host "[14/17] 连接测试已延后，请在后台完成主机注册" -ForegroundColor Yellow
} else {
    Write-Host "[14/17] 等待连接测试..." -ForegroundColor Yellow
    $testResult = $null
    $testWaited = 0
    $maxTestWait = 60
    while ($testWaited -lt $maxTestWait) {
        Start-Sleep -Seconds 5
        $testWaited += 5
        try {
            $testResp = Invoke-RestMethod -Uri "$ServerUrl/bootstrap/api/cert-provision/test-result/?token=$Token" -Method Get
            if ($testResp.status -ne "testing") {
                $testResult = $testResp
                break
            }
        } catch {
            continue
        }
        Write-Host "  测试中... ($testWaited/${maxTestWait}s)" -ForegroundColor DarkGray
    }
    if ($testResult -and $testResult.status -eq "success") {
        Write-Host "  连接测试成功!" -ForegroundColor Green
    } else {
        Write-Host "  连接测试失败或超时" -ForegroundColor Yellow
    }
}

Write-Host "[15/17] 安全性提升选项" -ForegroundColor Yellow
$choice = Read-Host "是否禁用密码认证以提升安全性？(Y/N)"
if ($choice -eq "Y" -or $choice -eq "y") {
    Write-Host "[16/17] 禁用密码认证..." -ForegroundColor Yellow
    Set-Item -Path WSMan:\localhost\Service\Auth\Basic -Value $false
    Set-Item -Path WSMan:\localhost\Service\Auth\Digest -Value $false
    Set-Item -Path WSMan:\localhost\Service\Auth\Kerberos -Value $false
    Set-Item -Path WSMan:\localhost\Service\Auth\CredSSP -Value $false
    Set-Item -Path WSMan:\localhost\Service\AllowUnencrypted -Value $false
    Restart-Service WinRM -Force
    $disableBody = @{ token = $Token } | ConvertTo-Json
    Invoke-RestMethod -Uri "$ServerUrl/bootstrap/api/cert-provision/disable-password-auth/" -Method Post -Body $disableBody -ContentType "application/json"
    Write-Host "  已禁用密码认证，仅允许证书认证" -ForegroundColor Green
} else {
    Write-Host "  保留密码认证" -ForegroundColor Yellow
}

Write-Host "[17/17] 清理临时文件..." -ForegroundColor Yellow
Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "`n=== 配置完成 ===" -ForegroundColor Cyan
