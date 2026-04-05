# 登录接口分析记录

## 1. 本次分析的关键转折

最开始仅从 APK 静态字符串看，登录模块很像旧版原生 SOAP 调用；但在 2026 年 4 月 5 日接入真机并打开 `WebView` 调试后，可以确认当前线上登录流程已经切换为远程 H5。

也就是说：

- APK 原生层仍然存在旧时代的登录痕迹
- 但当前实际在跑的登录页，是远端前端页面
- 真正应重建的是当前 H5 页面对应的 JSON 接口

## 2. 真机联调证据

### 2.1 前台页面

真机上启动后，前台 Activity 为：

- `com.inspur.handnwom/.activity.AndroidInterfaceForJsThree`

该页面中承载：

- `com.github.lzyzsd.jsbridge.BridgeWebView`

### 2.2 UI 树

`uiautomator dump` 已确认登录页实际包含：

- 用户名输入框
- 密码输入框
- 第三个输入框
- 图片区域
- 登录按钮
- 隐私政策勾选项
- 隐私政策弹窗

这与前端代码中：

- `username`
- `password`
- `verificationCode`
- `checkImgUrl`
- `ifPrivacy`

完全对得上。

结论：

- 图片验证码不是猜测，已经被真机运行态证实

## 3. WebView DevTools 证据

### 3.1 实际页面 URL

通过 `webview_devtools_remote` 获取到的真实页面 URL：

- `https://ad-pro.xyang.xin:20002/ad/#/login?redirectTo=%2Fhome`

这一步非常关键，因为它直接否定了“当前登录流程仍走原生 LoginActivity + SOAP”的主假设。

### 3.2 HTML 首页配置

页面 HTML 中有明确配置：

```html
<script>
window._CONFIG = {}
window._CONFIG["baseURL"] =
  "https://ad-pro.xyang.xin:20002/iflow/plugins/attendance"
</script>
```

结论：

- 当前 H5 登录调用的 API 基地址已经被页面配置坐实

## 4. 前端代码证据

## 4.1 axios 请求器

`ad_app.90f59332.js` 中存在独立请求器模块：

```js
const api = axios.create({
  baseURL: window._CONFIG["baseURL"],
  timeout: 120000
})
```

请求拦截器：

```js
const token = localStorage.getItem("ACCESS_TOKEN")
if (token) {
  config.headers["Access-Token"] = token
}
```

说明：

- 当前系统不是 `Bearer` 鉴权
- 当前系统使用的是自定义头：
  `Access-Token`

## 4.2 路由守卫

路由配置中存在：

- `/login`
- `name: "Login"`

并且有路由守卫逻辑：

- 没有 `ACCESS_TOKEN` 时跳转 `/login`

说明：

- 登录状态完全由前端 token 控制
- 这是典型单页应用结构

## 5. 登录页组件证据

登录页组件可直接还原出大部分核心行为。

### 5.1 输入模型

```js
inputMap: {
  username: "",
  password: "",
  verificationCode: ""
}
```

### 5.2 登录页运行逻辑

组件创建时：

```js
created() {
  this.getVerificationCode()
}
```

说明：

- 页面一打开就自动取验证码

### 5.3 验证码展示逻辑

```js
getVerificationCode() {
  apiGetVerificationCode(this.requestId).then(res => {
    if (res.retCode === "200") {
      this.checkImgUrl = "data:image/jpeg;base64," + res.retContent
    }
  })
}
```

说明：

- 验证码接口直接返回 Base64 图片数据
- 返回字段是 `retContent`
- 前端拼接 `data:image/jpeg;base64,`

### 5.4 登录提交逻辑

```js
apiLogin({
  userAccount: this.inputMap.username,
  pwd: encryptedPassword,
  requestId: this.requestId,
  verificationCode: this.inputMap.verificationCode
})
```

说明：

- 登录请求字段名已经被前端代码坐实
- 这几个字段可以直接进入接口文档

## 6. requestId 证据

`ad_chunk-vendors.f3af1892.js` 中的生成函数：

```js
let makeRequestId = (len = 21) =>
  crypto.getRandomValues(new Uint8Array(len)).reduce(...)
```

行为特征：

- 默认长度 21
- 使用浏览器 `crypto.getRandomValues`
- 字符集是 URL 友好型字符：
  `0-9 a-z A-Z - _`

说明：

- `requestId` 不是后端返回的
- 是前端自己生成、自己维护的会话标识

## 7. RSA 密码加密证据

登录组件中明确存在内置 RSA 公钥：

```pem
-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDkU/q+WCysfHBkIjzySfr/YoJSV/S
vgGI6kgk+maamO9EQYCWGpeBAuz1b9X0SeDqeOByM7ntPvgg3aOVNnhK5mkZXgSkkof
S14HxZc63owBWSt26YtG96WpCoaSRArCYqr3zWFXKD5s7iAjYWJbjyBx2OU4D4OK6ec
I7yO35F6QIDAQAB
-----END PUBLIC KEY-----
```

调用方式：

```js
const enc = new JSEncrypt()
enc.setPublicKey(publicKey)
const pwd = enc.encrypt(this.inputMap.password)
```

结论：

- 当前登录密码并非明文提交
- 当前登录密码为 RSA 公钥加密后提交

## 8. 已坐实的接口

## 8.1 获取验证码

- 方法：`GET`
- 路径：`/adUser/user/getVerificationCode`
- 参数：`requestId`

真实探测返回：

```json
{
  "isSuccess": true,
  "retCode": "200",
  "retMsg": "",
  "retContent": "<base64 image data>"
}
```

## 8.2 登录

- 方法：`POST`
- 路径：`/adUser/user/tologinNewV1`
- 请求体：

```json
{
  "userAccount": "string",
  "pwd": "string",
  "requestId": "string",
  "verificationCode": "string"
}
```

### 8.2.1 失败返回验证

2026 年 4 月 5 日，我用无效验证码实际请求后拿到：

```json
{
  "retCode": "1008",
  "isSuccess": false,
  "retMsg": "登录失败:请输入正确的验证码!",
  "retContent": ""
}
```

从这个结果可以推断：

- 服务端先校验验证码
- 验证码不对时，不会继续进入账号密码校验分支

### 8.2.2 成功返回验证

2026 年 4 月 5 日已用真实账号完成一次成功登录。

成功返回特征：

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

补充结论：

- `retContent.token` 足以作为登录成功判定
- `retMsg` 在成功时不稳定，不应作为业务判断依据
- `token` 为 JWT，而不是随机 session id

JWT 载荷已确认至少包含：

- `realName`
- `citycode`
- `userAccount`
- `userType`
- `userName`
- `exp`
- `userId`

## 8.3 获取用户信息

- 方法：`GET`
- 路径：`/adUser/user/getUserInfo`
- 鉴权：`Access-Token`

前端成功处理逻辑：

```js
localStorage.setItem("ACCESS_TOKEN", token)
apiGetUserInfo().then(...)
```

并缓存：

```json
{
  "userName": "...",
  "department": "...",
  "userAvatar": "默认头像"
}
```

### 8.3.1 用户信息接口真实返回

使用真实 token 调用后，`getUserInfo` 返回字段已确认包含：

- `userId`
- `userAccount`
- `userName`
- `realName`
- `pwd`
- `pwdSalt`
- `userType`
- `mobile`
- `email`
- `provincecode`
- `citycode`
- `orgId`
- `depId`
- `department`
- `remark`
- `status`
- `createTime`
- `lastLoginTime`
- `lastModifyPwdTime`

这说明：

- 当前前端只消费了其中一小部分字段
- 接口设计上的用户模型比登录页显露出来的更完整

## 8.4 登出

- 方法：`POST`
- 路径：`/adUser/user/loginOut`

## 9. 当前与早期静态分析的冲突点

### 9.1 为什么早期会推到 SOAP

APK 静态层仍然能看到：

- `ksoap2`
- `SoapObject`
- `/ws/outerService/dataQueryXml`

所以如果只看 APK 字符串，很容易把登录模块推向“原生 SOAP”。

### 9.2 为什么现在要改判为 JSON

因为运行态证据更强：

1. 真机 `WebView` 页面 URL 已抓到
2. HTML 里的 `window._CONFIG["baseURL"]` 已抓到
3. 前端 JS 的验证码、登录、用户信息接口路径已抓到
4. 验证码接口和失败登录接口已真实打通

因此当前应该这样处理：

- SOAP：作为旧版、遗留或旁路能力保留记录
- 登录重建：以当前 H5/JSON 方案为准

## 10. 对重建工作的直接影响

### 10.1 可以立刻编码的部分

- 登录页 UI
- 验证码加载/刷新
- requestId 生成
- RSA 密码加密
- 登录请求
- token 保存
- 用户信息拉取
- 登录态守卫

### 10.2 仍需真实账号联调的部分

- 首页初始化所需接口
- token 过期和续登策略

## 11. 一句话结论

当前可用的登录模块已经不是“原生 SOAP 登录页”，而是“App 壳 + WebView + 远程 Vue 登录页 + JSON 接口 + RSA 密码加密 + 图片验证码”。
