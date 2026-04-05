# 正常打卡分析文档

## 1. 结论

`正常打卡` 对应 H5 路由 `/clock`，模块入口是 `6a46`。  
这条链路当前已经可以按下面的结构重建：

1. 页面创建后并行拉取
   - 今日打卡记录
   - 当前定位
   - 人脸模型状态
2. 根据经纬度调用考勤范围接口，得到 `rangeAddress`
3. 用户点击“正常打卡”
4. 若未录入人脸，直接拦截
5. 若不在考勤范围内，直接拦截
6. 打开摄像头，前端做人脸检测
7. 截图上传到 `/attendanceImage/file?uploadType=2`
8. 服务端返回 `imgPath`
9. 调用 `/moSignRecord/createSignRecord`
10. 成功后重新刷新今日打卡记录

很重要的一点：

- `正常打卡` 页面本身 **没有直接使用** `getScheduling`
- 是否显示“上午/下午”主要由当前小时和 `signtype` 决定

## 2. 路由与组件

路由定义：

- `/clock`
- 标题：`正常打卡`
- 模块：`6a46`

页面组件结构：

- `UserHeader`
- `MapCard`
- `ClockCard`
- `ClockRecord`

页面核心状态：

- `isAM`
- `hasFaceModel`
- `rangeAddress`
- `signRecord`
- `center`
- `bdCenter`

其中：

- `isAM` 来自当前小时 `< 14`
- `center` 是普通经纬度
- `bdCenter` 是百度坐标

## 3. 页面初始化逻辑

`Clock` 页面 `created()` 时会执行：

1. `getTodaySignRecord()`
2. `getCenter()`
3. `getModelStatus()`

也就是说：

- 一进页面就会查今天的打卡记录
- 一进页面就会开始轮询定位
- 一进页面就会检查当前账号是否已经录入人脸模型

## 4. 原生定位桥接

### 4.1 Android

Android 侧使用 `WebViewJavascriptBridge`：

- 先调一次：
  - `callHandler("testcontent", { requestType: 301 })`
- 再调一次：
  - `callHandler("testcontent", { requestType: 1 }, callback)`

回调中要求原生返回：

```json
{
  "requestType": "1",
  "requestData": {
    "longitudeBd": "...",
    "latitudeBd": "...",
    "longitude": "...",
    "latitude": "..."
  }
}
```

页面收到后会写入：

- `bdCenter.lng = longitudeBd`
- `bdCenter.lat = latitudeBd`
- `center.lng = longitude`
- `center.lat = latitude`

然后立刻调用：

- `getSignAddress()`

Android 定位轮询周期：

- `5s`

### 4.2 iOS / React Native WebView

iOS 侧不是 `callHandler`，而是：

```js
window.ReactNativeWebView.postMessage(JSON.stringify({ code: 1 }))
```

之后页面会在约 `800ms` 后读取：

- `window.ReactNativeWebView.ownData.location`

期望字段同样是：

- `longitudeBd`
- `latitudeBd`
- `longitude`
- `latitude`

然后同样调用：

- `getSignAddress()`

## 5. 人脸模型状态

### 5.1 接口

- 方法：`POST`
- 路径：`/attendanceImage/searchModel`

### 5.2 页面用途

页面初始化时调用，用于决定：

- `hasFaceModel = true / false`

如果没有人脸模型：

- 正常打卡时会直接提示“请录入人脸”

### 5.3 实测返回

我已用当前账号实际验证：

```json
{
  "isSuccess": true,
  "retCode": "200",
  "retMsg": "",
  "retContent": {
    "userId": "80",
    "imagePath": "/home/nwom/face/face_img/model/4087d2843850428cae825c2229ce20eb.jpeg",
    "imgBase": ""
  }
}
```

可见：

- `imagePath` 存在即可认为已录入人脸

## 6. 今日打卡记录

### 6.1 接口

- 方法：`GET`
- 路径：`/moSignRecord/getSignCord`

### 6.2 请求参数

| 字段 | 位置 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `nowtime` | query | string | 是 | 日期，格式 `YYYY-MM-DD` |

页面真实调用：

```js
getSignCord({ nowtime: encodeURI(moment().format("YYYY-MM-DD")) })
```

### 6.3 页面消费方式

返回数组后，前端会只取两类记录：

- `signtype = 0` 作为上午记录
- `signtype = 1` 作为下午记录

展示字段：

- `signtime`
- `signstatus`
- `signaddress`

### 6.4 实测返回结构

我已用真实 token 拉取当天记录，字段结构已确认：

```json
{
  "id": 1072913,
  "userid": "80",
  "username": "曾理",
  "signaddress": "...",
  "signtime": "2026-04-05 12:39:31",
  "signtype": 1,
  "available": 1,
  "imgPath": "/home/nwom/face/face_img/model/4087d2843850428cae825c2229ce20eb.jpeg",
  "signWay": 0
}
```

目前确认到的字段：

- `id`
- `userid`
- `username`
- `signaddress`
- `signtime`
- `signtype`
- `available`
- `imgPath`
- `signWay`

注意：

- 当前我抓到的返回里没有 `signstatus`
- 但前端模板确实读取了 `signstatus`
- 所以这字段可能只在某些记录场景下返回

## 7. 考勤范围判断

### 7.1 接口

- 方法：`POST`
- 路径：`/adPhoneSignrecordDic/getSignAddress`

### 7.2 请求体

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `longitude` | number/string | 是 | 当前普通经度 |
| `latitude` | number/string | 是 | 当前普通纬度 |

页面真实调用：

```js
getSignAddress({
  longitude: this.center.lng,
  latitude: this.center.lat
})
```

### 7.3 页面行为

如果接口成功且 `retContent` 非空：

- `rangeAddress = retContent`
- 页面视为“进入考勤范围”

否则：

- `rangeAddress` 为空
- 页面视为“不在考勤范围”

### 7.4 实测补充

我已验证：

- 空请求会返回参数不完整
- 说明经纬度是必填

```json
{
  "isSuccess": false,
  "retCode": "500",
  "retMsg": "差数不完整",
  "retContent": ""
}
```

### 7.5 你提供的坐标实测结果

我已经用你提供的这组坐标直接调用过真实接口：

- 纬度：`30.608913948312445`
- 经度：`114.24549825716642`

无论经纬度是数字还是字符串，接口都能正常识别，返回完全一致：

```json
{
  "isSuccess": true,
  "retCode": "200",
  "retMsg": "成功查询",
  "retContent": "武汉-航天花园302栋2单元801室"
}
```

这说明当前这组坐标会被服务端判定为：

- 在考勤范围内
- 标准考勤地址为：`武汉-航天花园302栋2单元801室`

## 8. 手机详细地址字符串是否重要

你补充的这段信息：

- `航天花园内，笑云阁附近9米`
- `湖北省武汉市江汉区云飞路航天花园内，笑云阁附近9米`

对第一版生产接入 **不是必需字段**。

原因是：

1. H5 页面桥接里只读取坐标
   - `longitude`
   - `latitude`
   - `longitudeBd`
   - `latitudeBd`
2. 页面不会直接拿原生 POI 文案去打卡
3. 页面会把坐标发给 `/adPhoneSignrecordDic/getSignAddress`
4. 最终使用服务端返回的标准地址 `rangeAddress`

所以可以明确认为：

- 设备原始详细地址文案：可选
- 四个坐标字段：核心必需
- 服务端返回的 `rangeAddress`：打卡提交时建议使用

## 9. 可选考勤地址列表

### 8.1 接口

- 方法：`POST`
- 路径：`/adPhoneSignrecordDic/getAllSignAddress`

### 8.2 当前判断

`正常打卡` 页面本体没有直接调用这条接口，但它很可能属于：

- 地址配置
- 地址管理
- 调试或后台维护辅助

### 8.3 实测结果

这条接口能返回大量地址字符串列表，例如：

- `武汉-湖北省移动科技园`
- `武汉-省公司`
- `武汉-菱角湖万达A2写字楼`

所以它可以作为：

- 考勤点数据源候选

## 10. 正常打卡按钮逻辑

用户点击“正常打卡”时，前端逻辑是：

1. 先调用桥接：
   - `requestType: 302`
2. 然后判断：
   - 是否已录入人脸
   - 是否在考勤范围
3. 两者都满足才打开摄像头

拦截规则：

- `!hasFaceModel` -> 提示 `请录入人脸`
- `!inRange` -> 提示 `不在考勤范围`

这里 `inRange` 的来源是：

- `rangeAddress` 是否为非空字符串

## 11. 人脸检测与图片上传

### 10.1 前端行为

打开摄像头后，前端会：

1. 加载 `tinyFaceDetector`
2. 周期性检测画面中是否有人脸
3. 检测到后将当前帧画到 canvas
4. 转成 `jpeg`
5. 封装成 `Blob`
6. 上传

### 10.2 上传接口

- 方法：`POST`
- 路径：`/attendanceImage/file?uploadType=2`
- `Content-Type`：`multipart/form-data`

表单字段：

- `fileData`

文件名：

- `face.png`

### 10.3 上传成功判定

前端要求：

- `retCode == "200"`
- `retContent` 为图片路径字符串

这个 `retContent` 会继续作为后续打卡提交里的：

- `imgPath`

## 12. 真正的正常打卡接口

### 11.1 接口

- 方法：`POST`
- 路径：`/moSignRecord/createSignRecord`

### 11.2 前端默认提交体

前端真实调用：

```js
createSignRecord({
  imgPath: uploadedPath,
  address: this.rangeAddress
})
```

所以页面设计上的标准请求体是：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `imgPath` | string | 是 | 人脸截图上传成功后返回的服务端路径 |
| `address` | string | 建议传 | 当前考勤范围地址文本 |

### 11.3 实测结果

我已做最小 live 校验，结果如下：

1. 只传 `imgPath`
   - 成功
   - 返回 `打卡成功`
2. 传 `imgPath + address`
   - 成功
   - 返回 `打卡成功`
3. 只传 `address`
   - 失败
   - 提示图片转存失败
4. 空对象
   - 失败
   - 提示图片转存失败

也就是说，当前可以确认：

- `imgPath` 是真正硬性必填
- `address` 在接口层面很可能不是硬性必填
- 但从业务语义看，生产接入仍建议传 `address`

### 11.3.1 进一步实测结论

这点很关键，我已经从当天记录里验证到了：

- 如果 `createSignRecord` 不传 `address`
  - 接口仍可能成功
  - 但打卡记录里的 `signaddress` 会是空字符串
- 如果 `address` 传错编码
  - 打卡记录里的 `signaddress` 可能变成乱码或问号

因此生产接入时建议：

- 一定传 `address`
- 并且确保请求体按 UTF-8 JSON 正常发送
- 最稳妥的值就是 `/adPhoneSignrecordDic/getSignAddress` 返回的 `retContent`

### 11.4 实测成功响应

```json
{
  "isSuccess": true,
  "retCode": "200",
  "retMsg": "打卡成功",
  "retContent": ""
}
```

## 13. 关键页面判断逻辑

### 12.1 上午 / 下午判断

页面不是通过排班接口判断上午下午，而是：

```js
hour >= 0 && hour < 14
```

即：

- `< 14:00` 视为上午打卡态
- `>= 14:00` 视为下午打卡态

### 12.2 是否在考勤范围

逻辑不是布尔接口，而是：

- `rangeAddress` 有值 -> 在范围内
- `rangeAddress` 为空 -> 不在范围内

### 12.3 正常打卡是否依赖排班

目前从 `/clock` 页面的真实代码看：

- 不依赖 `getScheduling`
- 页面本体没有调用 `/moSignRecord/getScheduling`

所以如果是为了快速接生产，`正常打卡` 最小闭环可以不先接排班接口。

## 14. 可直接用于重建的最小实现

如果你现在只想尽快把“正常打卡”接进生产，建议最小实现按这个顺序：

1. `POST /attendanceImage/searchModel`
   - 判断是否录入人脸
2. 获取原生定位
   - 普通经纬度 + 百度经纬度
3. `POST /adPhoneSignrecordDic/getSignAddress`
   - 判断是否在考勤范围
4. `GET /moSignRecord/getSignCord?nowtime=YYYY-MM-DD`
   - 拉今天记录
5. 打开摄像头做人脸检测
6. `POST /attendanceImage/file?uploadType=2`
   - 获取 `imgPath`
7. `POST /moSignRecord/createSignRecord`
   - 请求体至少带 `imgPath`
   - 建议同时带 `address`
8. 再次调用 `getSignCord`
   - 刷新页面

## 15. 生产接入建议

### 14.1 第一版最值得先接的字段

建议你先把这几个字段固定下来：

- 定位桥接返回：
  - `longitude`
  - `latitude`
  - `longitudeBd`
  - `latitudeBd`
- 可选保留：
  - 原生详细地址字符串
  - 原生 POI 名称
- 今日记录：
  - `signtime`
  - `signtype`
  - `signaddress`
  - `imgPath`
- 打卡提交：
  - `imgPath`
  - `address`

### 14.2 风险点

- `createSignRecord` 是真实写接口，不要频繁联调
- 当前没有看到明显幂等保护
- `imgPath` 明显是硬依赖，不能省略
- `rangeAddress` 为空时前端会直接拦截，不会放行打卡

### 14.3 当前最重要的实现结论

如果只做“正常打卡”：

- 先不接 `getScheduling`
- 先把“定位 + 人脸模型 + 上传图片 + createSignRecord + 今日记录刷新”这 5 段打通
- 其中 `address` 应优先使用服务端标准返回值：
  - `武汉-航天花园302栋2单元801室`

## 16. 人像图调试结论

你提供的这张正脸照片，从调试角度看是合适的：

- 正脸
- 背景干净
- 面部无遮挡
- 分辨率足够

它适合用于验证两件事：

1. `/attendanceImage/file?uploadType=2` 是否能稳定上传
2. `createSignRecord` 在带 `imgPath` 时是否会继续被服务端拒绝

但当前还不能把它直接视为“可绕过真实人脸认证”的证据。原因是：

- H5 前端明确有 `hasFaceModel` 和本地 `tinyFaceDetector` 两层门禁
- 我已经确认 `imgPath` 是提交打卡的硬依赖
- 但还没有安全、可重复、低风险的证据证明服务端完全不做人脸一致性校验

所以这一步最稳妥的策略是：

- 先把图片上传链路跑通
- 默认只做 dry-run
- 只有明确需要时才真的调 `createSignRecord`

## 17. 推荐调试顺序

### 17.1 默认只读 / 不落库

先执行：

```bash
python normal_clock_debug.py --image "你的本地图片路径"
```

这一步会做：

1. 复用本地缓存 token
2. 查当前账号是否已录入人脸模型
3. 用当前坐标调用 `/adPhoneSignrecordDic/getSignAddress`
4. 查当天打卡记录
5. 上传图片到 `/attendanceImage/file?uploadType=2`
6. 输出一份 `wouldSubmit` 请求体

但不会真正写入生产打卡记录。

### 17.2 明确需要时再执行写入

只有在你确认要做真实联调时，再执行：

```bash
python normal_clock_debug.py --image "你的本地图片路径" --submit
```

如果你只想验证最小请求体，也可以额外带：

```bash
python normal_clock_debug.py --image "你的本地图片路径" --submit --no-address
```

但这只适合调试，不适合生产接入。

## 18. 当前最稳妥的生产结论

截至目前，可以确定：

- 正常打卡前端侧不能直接跳过“已录入人脸”和“在考勤范围内”这两个判断
- 服务端提交层至少要求 `imgPath`
- `address` 虽然不是接口硬必填，但生产里应当始终传
- `address` 应使用 `/adPhoneSignrecordDic/getSignAddress` 返回的标准地址
- 当前这组坐标对应的标准地址仍然是：
  - `武汉-航天花园302栋2单元801室`

因此第一版生产实现，仍建议走这条主链路：

1. `searchModel`
2. 原生定位
3. `getSignAddress`
4. 图片上传
5. `createSignRecord`

如果后面你要继续压缩路径，可以再专门验证“上传一张静态人像图后，服务端是否接受直接打卡”，但那一步会产生真实生产记录，必须按受控联调来做。

## 19. 空地点记录修复结论

当前客户端里看到的“打卡地点为空”，不是前端展示层丢了数据，而是那条记录在写入时就没有带上有效 `address`。

这一点现在已经可以确定，因为：

- `ClockRecord` 组件只是直接展示 `signRecord[x].signaddress`
- 不会再用当前定位或 `rangeAddress` 去补写
- 我们之前的 live 验证也已经证明：
  - 不传 `address` 也能打卡成功
  - 但生成的记录里 `signaddress` 会是空字符串

### 19.1 现有坏数据能否直接修

截至当前 bundle 和接口分析结果，正常打卡相关只看到这几条接口：

- `/moSignRecord/createSignRecord`
- `/moSignRecord/getSignCord`
- `/moSignRecord/getScheduling`
- `/moSignRecord/createOutOffice`

没有在当前 H5 中发现：

- 修改正常打卡记录地址的接口
- 删除正常打卡记录的接口
- 重新补写 `signaddress` 的接口

所以当前更稳妥的结论是：

- 现有那条空地点记录，前端侧无法直接修复
- 如果后端没有单独管理接口，就只能保留现状
- 若业务上必须修正，只能走后台人工修数或数据库侧修复

### 19.2 后续如何避免再出现

后面所有正常打卡提交都应固定遵守这条规则：

1. 先用坐标调用 `/adPhoneSignrecordDic/getSignAddress`
2. 取服务端返回的标准地址
3. 再调用 `/moSignRecord/createSignRecord`
4. 始终带上：
   - `imgPath`
   - `address`

其中 `address` 应使用当前已经实测通过的标准值：

- `武汉-航天花园302栋2单元801室`

只要后续都按这条链路提交，就不会再出现“打卡成功但地点为空”的问题。
