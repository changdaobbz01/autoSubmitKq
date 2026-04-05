# 重建登录页与测试台

这是当前仓库里的本地 Web 服务与前端页面，目标是围绕“正常打卡”入口做快速联调和功能验证。

## 启动

```powershell
python rebuild_login/server.py
```

默认地址：

```text
http://127.0.0.1:8765
```

## 主要能力

- 登录、验证码刷新、token 复用
- 多账号 `xlsx` 导入
- 账号级 token 刷新
- 账号照片路径检测
- 正常打卡流程调测
- 单账号真实打卡
- 定时轮询
- 企业微信群机器人通知

## 多账号与轮询

当前页面支持：

- 导入 `xlsx` 账号表
- 自动识别账号、密码、姓名、部门、启用状态、照片路径
- 显示多账号 token 状态、照片状态、最近执行结果
- 清空全部账号 token

轮询支持以下配置：

- 周末开关
- 两个打卡时间点
- 轮询执行模式
  - `仅调测`：只跑流程校验，不提交真实打卡
  - `真实提交`：使用账号表中的照片执行真实打卡

轮询会自动跳过：

- 无 token 的账号
- token 已过期的账号
- 照片路径异常的账号

## 正常打卡调试

根目录脚本：

```powershell
python normal_clock_debug.py
```

只做调测，不提交真实打卡。

如果要带图片验证上传链路：

```powershell
python normal_clock_debug.py --image "你的本地图片绝对路径"
```

如果要显式提交真实打卡：

```powershell
python normal_clock_debug.py --image "你的本地图片绝对路径" --submit
```

## 企业微信群通知

页面支持配置企业微信群机器人：

- 保存 `webhook`
- 发送测试消息
- 真实打卡后发送结果
- 轮询完成后发送汇总
- 失败时可选 `@all`

配置会保存到：

```text
.attendance_auth/wecom_bot.json
```

## 打包

仓库根目录可直接执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_portable.ps1
```

生成的便携版目录和压缩包可直接复制到其他 Windows 设备运行。
