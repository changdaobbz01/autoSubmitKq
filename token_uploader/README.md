# 考勤 Token 采集器

这是一个 Windows 桌面采集端。门户短信登录和考勤单点换票都由当前设备直接完成，获取成功后仅把考勤账号与 Token 上传至云端 Token Hub。

## 数据流

```text
用户电脑（湖北网络）
  -> 门户短信登录
  -> 考勤应用单点换票
  -> HTTPS 上传 Token
上海云端 Token Hub
  -> 加密存储
  -> 本地 AttendanceRebuild 按账号同步
```

桌面端不会上传门户密码，也不会在本地保存密码、短信验证码或 Token。云端连接失败时，已经取得的 Token 只暂存在进程内存，用户可以直接重试上传；关闭程序后自动清除。

## 源码运行

```powershell
E:\anaconda\python.exe -m token_uploader.app
```

## 测试

```powershell
E:\anaconda\python.exe -m unittest discover -s tests -v
node --check token_uploader\web\app.js
```

## 打包

```powershell
powershell -ExecutionPolicy Bypass -File .\build_token_collector.ps1
```

产物：

```text
dist/AttendanceTokenCollector/
releases/AttendanceTokenCollector-portable.zip
```

便携包不包含访问口令、账号、密码、Token 或运行缓存。
