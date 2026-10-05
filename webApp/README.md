# 考勤凭证助手

这是一个面向手机的门户短信验证页面，以及供本地考勤程序获取 Token 的 Spring Boot API 服务。

当前版本只保留短信验证码流程，不包含图片验证码：

1. 用户在手机网页输入门户账号和密码。
2. 服务端向门户请求短信验证码。
3. 用户输入短信验证码，服务端完成门户登录和考勤应用换票。
4. 账号、考勤 Token 以及用户选择保存的密码以 AES-256-GCM 加密后写入 PostgreSQL。
5. 桌面接口支持按 revision 分页读取；当前本地考勤程序为确保后来导入的账号不会漏配，每次同步会从 `since=0` 读取完整快照。

## 目录

```text
webApp/
├─ app/                 手机 Web 页面与 Nginx
├─ Api/                 Spring Boot API
├─ docker-compose.yml   Web、API、PostgreSQL 编排
└─ .env.example         部署变量模板
```

## 快速启动

需要已安装 Docker Desktop，并确保部署服务器能访问门户与考勤上游接口。

先生成三组互不相同的随机密钥。在 PowerShell 中执行：

```powershell
function New-RandomBase64([int]$Bytes = 32) {
    $data = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($data) } finally { $rng.Dispose() }
    [Convert]::ToBase64String($data)
}

New-RandomBase64 32 # TOKEN_MASTER_KEY
New-RandomBase64 32 # MOBILE_ACCESS_KEY
New-RandomBase64 32 # DESKTOP_API_KEY
New-RandomBase64 32 # POSTGRES_PASSWORD 也可以使用该随机值
```

复制配置并填写刚生成的值：

```powershell
Copy-Item .env.example .env
notepad .env
docker compose up --build -d
docker compose ps
```

默认访问地址为 `http://服务器地址:8088/`。手机页面第一次打开时需要输入 `MOBILE_ACCESS_KEY`，该口令只存放在浏览器当前会话中。

需要通过二维码分发时，可以把访问口令放在 URL 片段中：

```text
https://服务器地址/attendance-token/#access=<MOBILE_ACCESS_KEY>
```

页面会自动应用该口令并保存到当前浏览器会话，随后立即从地址栏移除 `access` 片段。URL 片段不会发送到服务器，但二维码本身仍包含访问口令，只应分享给参与测试的用户。

查看服务日志：

```powershell
docker compose logs -f api
```

停止服务但保留数据库：

```powershell
docker compose down
```

## 本地程序同步接口

接口：

```http
GET /api/desktop/v1/tokens?since=0&limit=100
X-Desktop-Key: <DESKTOP_API_KEY>
```

PowerShell 测试示例：

```powershell
$headers = @{ "X-Desktop-Key" = "填入 DESKTOP_API_KEY" }
$result = Invoke-RestMethod `
    -Uri "http://127.0.0.1:8088/api/desktop/v1/tokens?since=0&limit=100" `
    -Headers $headers
$result | ConvertTo-Json -Depth 6
```

响应中：

- `items` 是本次变化的账号；只有状态为 `active` 时才返回明文 `token`。
- `nextRevision` 是本地程序下次请求应使用的 `since`。
- `hasMore=true` 时应立即继续请求，直到为 `false`。
- `latestRevision` 是服务端当前最新版本，可用于观察同步进度。
- 密码永远不会通过该接口返回。

调用方可以持久化最后成功处理的 `nextRevision` 做增量同步。当前配套本地程序账号量较小，手动同步和打卡前自动同步都从 `since=0` 分页读取完整快照，再只更新本地已有同名账号的 Token；这样本地后来导入账号时也能匹配到云端较早保存的记录。

## 安全与运维

- 正式对外提供服务时，必须在该服务前配置 HTTPS 反向代理或服务器入口网关。不要在公网直接使用 HTTP 传输账号、密码和短信验证码。
- `TOKEN_MASTER_KEY` 用于解密数据库中的 Token 和密码。部署后必须安全备份；丢失或更换后，已有密文无法恢复。
- `MOBILE_ACCESS_KEY` 供参与测试的手机用户使用，`DESKTOP_API_KEY` 只配置到本地考勤程序，两者不要共用。
- 门户短信临时票据只保存在 API 进程内存中，默认 10 分钟过期，不写入数据库。
- 页面不展示考勤 Token，也不会把门户密码写入浏览器存储。取消“加密保存密码”后，本次登录成功会删除服务端原有的已存密码。
- PostgreSQL 数据保存在 Docker 卷 `tokenhub-db`。升级或迁移前应同时备份数据库和 `TOKEN_MASTER_KEY`。
- `docker-compose.yml` 将 `ad-pro.xyang.xin` 映射到当前考勤 IP，同时保留 HTTPS 主机名与 SNI；如果考勤 IP 变化，需要同步修改 `extra_hosts`。

## 开发验证

后端使用 Java 21 和 Maven Wrapper：

```powershell
Set-Location Api
.\mvnw.cmd test
.\mvnw.cmd package
```

前端是无构建依赖的 HTML/CSS/JavaScript，可执行语法检查：

```powershell
node --check app\app.js
```
