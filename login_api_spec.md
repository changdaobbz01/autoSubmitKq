# 登录接口文档

## 1. 结论

截至 2026 年 4 月 5 日，`掌上考勤` 当前线上登录流程已经可以按“远程 H5 + JSON 接口”重建，不应再优先按早期 APK 字符串中的 SOAP 接口重建。

当前实际登录链路：

1. App 打开 `WebView`
2. `WebView` 加载远程页面 `/ad/#/login?redirectTo=%2Fhome`
3. 登录页调用 `/iflow/plugins/attendance` 下的 JSON 接口
4. 登录成功后写入 `localStorage.ACCESS_TOKEN`
5. 再调用用户信息接口，进入首页

## 2. 已验证的基础地址

### 2.1 登录页地址

- 页面地址：
  `https://ad-pro.xyang.xin:20002/ad/#/login?redirectTo=%2Fhome`

- HTML 入口：
  `https://ad-pro.xyang.xin:20002/ad/`

### 2.2 API 基地址

前端首页 HTML 明确写死：

```js
window._CONFIG["baseURL"] = "https://ad-pro.xyang.xin:20002/iflow/plugins/attendance"
```

因此当前登录模块 API 基地址为：

- `https://ad-pro.xyang.xin:20002/iflow/plugins/attendance`

## 3. 前端请求器配置

前端请求器在 `ad_app.90f59332.js` 中已经明确：

```js
const api = axios.create({
  baseURL: window._CONFIG["baseURL"],
  timeout: 120000
})
```

### 3.1 请求头

请求拦截器逻辑：

- 从 `localStorage.ACCESS_TOKEN` 读取 token
- 如果存在，则写入请求头：
  `Access-Token: <token>`

不是 `Authorization: Bearer ...`

### 3.2 路由守卫

前端路由守卫逻辑：

- 如果当前路由不是 `Login`
- 且本地没有 `ACCESS_TOKEN`
- 则强制跳转 `/login`

## 4. 登录页结构

真机 UI 与前端代码已共同确认登录页包含以下字段：

- 用户名：`inputMap.username`
- 密码：`inputMap.password`
- 图片验证码：`inputMap.verificationCode`
- 图片验证码图片：`checkImgUrl`
- 隐私政策确认：`ifPrivacy`

额外特征：

- 使用随机软键盘组件 `SimpleKeyboard`
- 用户名、密码、验证码都可通过该软键盘输入
- 页面初次创建时自动拉取验证码
- 点击验证码图片会刷新验证码

## 5. requestId 生成规则

验证码和登录请求都使用同一个 `requestId`。

前端代码实际生成方式：

```js
let makeRequestId = (len = 21) =>
  crypto.getRandomValues(new Uint8Array(len)).reduce(...)
```

可归纳为：

- 长度：`21`
- 字符集：`0-9 a-z A-Z - _`
- 类型：一次登录会话内的随机字符串

示例：

- `cElrNeLHaIQOpDyvq0Cf4`

说明：

- 我本地实际测试时，服务端对 `requestId` 校验较宽松，`GUID` 也能返回验证码
- 但重建时仍建议按前端真实实现生成 21 位随机串

## 6. 接口一：获取图片验证码

### 6.1 请求

- 方法：`GET`
- 路径：`/adUser/user/getVerificationCode`
- 完整地址：
  `https://ad-pro.xyang.xin:20002/iflow/plugins/attendance/adUser/user/getVerificationCode?requestId={requestId}`

### 6.2 请求参数

| 字段 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `requestId` | query | string | 是 | 21 位随机串，登录页创建时生成 |

### 6.3 成功响应

我在 2026 年 4 月 5 日对真实接口做了无账号验证，返回如下特征：

- HTTP 状态：`200`
- `Content-Type`：`text/plain;charset=UTF-8`
- JSON 结构：

```json
{
  "isSuccess": true,
  "retCode": "200",
  "retMsg": "",
  "retContent": "iVBORw0KGgoAAAANSUhEUgAA..."
}
```

### 6.4 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `isSuccess` | boolean | 是否成功 |
| `retCode` | string | 成功时为 `"200"` |
| `retMsg` | string | 成功时为空字符串 |
| `retContent` | string | 验证码图片的 Base64 数据，不带 `data:` 前缀 |

### 6.5 前端处理方式

前端代码明确：

```js
this.checkImgUrl = "data:image/jpeg;base64," + t.retContent
```

因此重建时应直接按下面方式显示：

```text
img.src = "data:image/jpeg;base64," + retContent
```

## 7. 接口二：登录

### 7.1 请求

- 方法：`POST`
- 路径：`/adUser/user/tologinNewV1`
- 完整地址：
  `https://ad-pro.xyang.xin:20002/iflow/plugins/attendance/adUser/user/tologinNewV1`
- Content-Type：
  `application/json;charset=UTF-8`

### 7.2 请求体

前端代码已明确：

```json
{
  "userAccount": "string",
  "pwd": "string",
  "requestId": "string",
  "verificationCode": "string"
}
```

### 7.3 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `userAccount` | string | 是 | 登录用户名 |
| `pwd` | string | 是 | RSA 公钥加密后的密码 Base64 字符串 |
| `requestId` | string | 是 | 与验证码接口使用同一个 requestId |
| `verificationCode` | string | 是 | 用户输入的图片验证码 |

## 8. 密码加密规则

### 8.1 加密算法

前端代码使用 `JSEncrypt` 公钥加密密码。

因此重建时应按以下规则处理：

- 算法：`RSA`
- 填充方式：`PKCS#1 v1.5`
- 输出：Base64 字符串

### 8.2 内置公钥

```pem
-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDkU/q+WCysfHBkIjzySfr/YoJSV/S
vgGI6kgk+maamO9EQYCWGpeBAuz1b9X0SeDqeOByM7ntPvgg3aOVNnhK5mkZXgSkkof
S14HxZc63owBWSt26YtG96WpCoaSRArCYqr3zWFXKD5s7iAjYWJbjyBx2OU4D4OK6ec
I7yO35F6QIDAQAB
-----END PUBLIC KEY-----
```

### 8.3 加密前后示意

```text
明文密码: badpassword
加密后: Base64(RSA_PKCS1_v1_5(publicKey, UTF8(password)))
```

## 9. 登录成功响应

前端成功判断逻辑：

```js
if (t.retContent && t.retContent.token) {
  localStorage.setItem("ACCESS_TOKEN", t.retContent.token)
  ...
}
```

2026 年 4 月 5 日已用真实账号完成一次成功登录，成功响应至少满足：

```json
{
  "isSuccess": true,
  "retCode": "200",
  "retMsg": "string",
  "retContent": {
    "token": "string"
  }
}
```

已确认特征：

| 字段 | 类型 | 说明 |
|---|---|---|
| `isSuccess` | boolean | 成功时为 `true` |
| `retCode` | string | 成功时为 `"200"` |
| `retMsg` | string | 成功时存在，但当前文案不稳定，不建议依赖 |
| `retContent.token` | string | 登录 token |

### 9.1 token 特征

成功返回的 `token` 已确认是 JWT，解码后至少包含：

| 字段 | 说明 |
|---|---|
| `realName` | 真实姓名 |
| `citycode` | 城市编码 |
| `userAccount` | 账号 |
| `userType` | 用户类型 |
| `userName` | 用户名 |
| `exp` | 过期时间戳 |
| `userId` | 用户 ID |

## 10. 登录失败响应

我在 2026 年 4 月 5 日用无效验证码做了真实请求验证，得到：

```json
{
  "retCode": "1008",
  "isSuccess": false,
  "retMsg": "登录失败:请输入正确的验证码!",
  "retContent": ""
}
```

由此可以确认：

- 服务端失败时仍返回 JSON
- `retMsg` 是前端直接展示给用户的错误消息
- 当前服务端会优先校验验证码，再继续校验账号密码

前端失败处理逻辑：

1. 刷新验证码
2. 弹出 `retMsg`

## 11. 接口三：获取用户信息

登录成功后，前端立即调用：

- 方法：`GET`
- 路径：`/adUser/user/getUserInfo`

完整地址：

- `https://ad-pro.xyang.xin:20002/iflow/plugins/attendance/adUser/user/getUserInfo`

请求头要求：

- `Access-Token: <ACCESS_TOKEN>`

前端取到用户信息后会写入：

```json
{
  "userName": "string",
  "department": "string",
  "userAvatar": "默认头像资源"
}
```

保存位置：

- `localStorage.USER_INFO`

### 11.1 真实成功响应

2026 年 4 月 5 日已用真实 token 验证成功，接口返回字段已确认包含：

```json
{
  "isSuccess": true,
  "retCode": "200",
  "retMsg": "查询成功",
  "retContent": {
    "userId": 0,
    "userAccount": "string",
    "userName": "string",
    "realName": "string",
    "pwd": "***",
    "pwdSalt": "***",
    "userType": "string",
    "mobile": "string",
    "email": "string",
    "provincecode": "string",
    "citycode": "string",
    "orgId": 0,
    "depId": "string",
    "department": "string",
    "remark": "string",
    "status": 0,
    "createTime": "string",
    "lastLoginTime": "string",
    "lastModifyPwdTime": "string"
  }
}
```

说明：

- `getUserInfo` 返回字段比前端最终缓存到 `USER_INFO` 的字段多得多
- H5 当前只取 `userName`、`department`，并补一个本地默认头像
- 重建时建议保留完整 `retContent` 模型

## 12. 登出接口

前端代码已确认：

- 方法：`POST`
- 路径：`/adUser/user/loginOut`

完整地址：

- `https://ad-pro.xyang.xin:20002/iflow/plugins/attendance/adUser/user/loginOut`

## 13. 本地存储

### 13.1 H5 当前实际使用

| Key | 位置 | 说明 |
|---|---|---|
| `ACCESS_TOKEN` | `localStorage` | 登录 token |
| `USER_INFO` | `localStorage` | 用户信息缓存 |

### 13.2 APK 原生层遗留线索

原生 APK 静态资源中仍能看到：

- `SharedPreferences("logininfo")`

这说明旧版本原生登录页曾使用本地偏好存储；但当前线上登录流程已经主要由 H5 接管，应优先按 `localStorage` 重建。

### 13.3 推荐 token 复用策略

为了避免频繁触发登录接口，建议按下面的顺序处理：

1. 启动时先读取本地缓存 token
2. 本地先解析 JWT 的 `exp`
3. 若 `exp - 300秒 > 当前时间`，优先直接复用，不打登录接口
4. 只有 token 过期、接近过期，或业务接口明确返回 token 失效时，才重新走验证码登录
5. 重新登录成功后，覆盖本地缓存

建议缓存内容至少包含：

```json
{
  "token": "string",
  "tokenExp": 0,
  "userAccount": "string",
  "userName": "string",
  "realName": "string",
  "department": "string",
  "savedAt": 0,
  "userInfo": {}
}
```

本工作区已经落了一个参考实现：

- [attendance_auth_client.py](D:/文档/New%20project/attendance_auth_client.py)

默认缓存路径：

- `.attendance_auth/session.json`

该目录已加入 `.gitignore`，可直接用于本地复用 token，不会误提交。

## 14. 推荐重建顺序

### 14.1 最小可用版

1. 打开登录页
2. 生成 `requestId`
3. 调用验证码接口
4. 显示图片验证码
5. 用户输入用户名、密码、验证码
6. 用 RSA 公钥加密密码
7. 调用登录接口
8. 保存 `ACCESS_TOKEN`
9. 调用用户信息接口
10. 保存 `USER_INFO`
11. 跳转首页

### 14.2 需要保留的前端行为

- 未勾选隐私政策时不允许登录
- 登录失败后自动刷新验证码
- 点击验证码图片支持刷新
- 没有 token 时强制跳回 `/login`

## 15. 旧 SOAP 线索的处理建议

APK 静态层里确实还能看到：

- `/ws/outerService/dataQueryXml`
- `ksoap2`
- `SoapObject`

但结合 2026 年 4 月 5 日的真机联调结果，可以明确：

- 当前在线登录页不是走 SOAP
- 当前在线登录页走的是 `/iflow/plugins/attendance` 下的 JSON 接口

因此重建时建议：

- 把 SOAP 视为旧版或旁路能力
- 登录模块以本文档中的 H5/JSON 方案为准

## 16. 当前仍待真实账号确认的项

- 是否还存在二次校验或设备风控字段
- 首页初始化时额外依赖的接口列表

当前登录链路和用户信息链路已经基本坐实，不影响第一版重建。
