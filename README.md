# autoSubmitKq

基于现有 APK 逆向分析结果重建的“考勤”本地测试台，当前重点覆盖：

- 登录与 token 复用
- `xlsx` 多账号导入与状态管理
- 正常打卡流程调测
- 真实打卡单账号提交
- 定时轮询
- 企业微信群机器人通知
- 便携版打包分发

## 项目结构

- `rebuild_login/`
  本地 Web 界面与 HTTP 服务
- `attendance_auth_client.py`
  登录、验证码、RSA 加密、token 缓存、接口调用
- `account_registry.py`
  多账号注册表、`xlsx` 导入、照片路径与账号状态管理
- `normal_clock_debug.py`
  正常打卡调试与提交流程封装
- `wecom_bot_notifier.py`
  企业微信群机器人通知
- `runtime_paths.py`
  源码运行和打包运行的统一路径适配
- `build_portable.ps1`
  Windows 便携版打包脚本
- `login_api_spec.md`
  登录接口文档
- `login_interface_analysis.md`
  登录分析过程记录
- `normal_clock_api_spec.md`
  正常打卡接口文档

## 本地运行

```powershell
python rebuild_login/server.py
```

默认地址：

```text
http://127.0.0.1:8765
```

## 当前功能

- 优先复用本地 token，减少重复登录
- 支持验证码登录和多账号 token 刷新
- 支持导入 `xlsx` 账号表，自动识别账号、密码、姓名、部门、照片路径
- 支持单账号真实打卡
- 支持轮询模式切换
  - `仅调测`
  - `真实提交`
- 支持修改两个轮询时间点
- 支持周末轮询开关
- 支持企业微信群机器人测试消息、真实打卡消息、轮询汇总消息

## 打包

```powershell
powershell -ExecutionPolicy Bypass -File .\build_portable.ps1
```

打包完成后会生成：

- `dist/AttendanceRebuild/`
- `dist/AttendanceRebuild-portable.zip`

便携版运行方式：

- 双击 `Launch-AttendanceRebuild.bat`
- 或直接运行 `AttendanceRebuild.exe`

运行时数据会写到程序目录下的 `.attendance_auth/`，方便整体复制到其他设备继续使用。

## 说明

- 仓库默认不提交 `.attendance_auth/`、`build/`、`dist/` 等本地运行与打包产物。
- 当前实现以 Windows 本地测试台为主。
- 真实提交会调用生产打卡接口，使用前请先确认轮询模式和账号照片配置。
