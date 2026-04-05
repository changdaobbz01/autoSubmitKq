# 重建登录页与首页壳

这是一个不依赖 Node 的最小重建版本，当前包含两部分：

- `server.py`：本地静态页 + 同源代理 + 首页聚合接口
- `web/`：重建版 H5 登录页与登录后首页壳

## 启动

```bash
python rebuild_login/server.py
```

默认地址：

```text
http://127.0.0.1:8765
```

## 当前能力

- 检测并优先复用本地 token
- 拉取并刷新图片验证码
- 账号密码登录
- 登录后刷新用户信息
- 聚合首页数据
  - 待审批
  - 我的发起
  - 待补签
  - 人脸模型状态
- 按真实 H5 菜单重建首页入口
- 清理本地会话，并可选调用远端登出

## 正常打卡调试

根目录还提供了一个默认不落库的调试脚本：

```bash
python normal_clock_debug.py
```

如果已经把人像图保存到本地，可以继续执行：

```bash
python normal_clock_debug.py --image "你的本地图片路径"
```

这两条命令都会优先复用 `.attendance_auth/session.json` 中的 token，只做：

- 人脸模型检查
- 考勤范围地址计算
- 当日打卡记录查询
- 可选的图片上传

只有显式带上 `--submit` 时，才会调用真实的 `/moSignRecord/createSignRecord`。

## 多账号测试台

前端已精简为多账号测试台，只保留：

- 当前会话
- `xlsx` 导入
- 多账号状态表
- 工作日轮询状态
- 企业微信群通知
- 返回数据面板

### xlsx 导入

支持首表列名：

- `账号 / 用户名 / userAccount`
- `密码 / password`
- `姓名 / realName`
- `部门 / department`
- `启用 / enabled`
- `备注 / note`

导入后会在本地生成账号注册表，并为每个账号准备独立 session 缓存目录。

本地注册表：

```text
.attendance_auth/accounts_registry.json
```

账号级 session：

```text
.attendance_auth/accounts/<account>/session.json
```

### 轮询说明

轮询默认时点是工作日 `08:00`、`18:30`，当前实现是：

- 对导入表中“启用”的账号逐个执行 `dry-run`
- 只对“已有可复用 token”的账号执行正常打卡检查
- token 已过期或没有 token 的账号，会标记为“待验证码登录”
- 不做无人值守验证码登录
- 不做批量真实打卡提交

页面里可以直接修改两个打卡时点，保存后会同步刷新后端轮询计划和下一次执行时间。

轮询状态会持久化到：

```text
.attendance_auth/clock_polling_state.json
```

后端接口：

- `GET /api/accounts`
- `POST /api/accounts/import`
- `POST /api/accounts/toggle`
- `POST /api/accounts/remove`
- `GET /api/clock-polling/status`
- `POST /api/clock-polling/start`
- `POST /api/clock-polling/stop`

## 企业微信群通知

页面已支持企业微信群“消息推送（原群机器人）”配置：

- 保存群机器人 `webhook` 地址
- 配置真实打卡结果通知
- 配置轮询汇总通知
- 可选失败时 `@all`
- 发送一条测试消息验证联通性

通知配置文件：

```text
.attendance_auth/wecom_bot.json
```

说明：

- 真实打卡成功或失败后，会按配置向企业微信群推送结果
- 轮询 dry-run 完成后，会按配置推送汇总结果
- 页面会显示最近一次测试发送和最近一次实际发送状态
- 留空保存不会覆盖已保存的 `webhook`

## 设计说明

- 远端接口存在跨域限制，所以浏览器页面不直接请求线上服务。
- 本地代理统一代发验证码、登录、用户信息、首页聚合、登出等请求。
- token 默认缓存到项目根目录 `.attendance_auth/session.json`。
- 首页菜单和接口映射来自已经确认的 H5 bundle 分析结果。
