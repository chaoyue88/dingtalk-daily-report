# 钉钉日志 API 参考

> 本文档整理了钉钉日报 skill 所用到的 API 端点，基于钉钉 OAPI（旧版但稳定）风格。
> 官方文档：https://open.dingtalk.com/document/development/report-log-overview

## 认证

### 获取 Access Token

```http
GET https://oapi.dingtalk.com/gettoken?appkey=APPKEY&appsecret=APPSECRET
```

响应：
```json
{
  "errcode": 0,
  "errmsg": "ok",
  "access_token": "xxxxxxxxx",
  "expires_in": 7200
}
```

- token 有效期 7200 秒（2小时），在有效期内重复获取返回同一个 token
- `access_token` 用于所有后续 API 请求的 `?access_token=` 参数

---

## 日志模板 API

### 列出用户可见的日志模板

```http
POST https://oapi.dingtalk.com/topapi/report/template/listbyuserid?access_token=TOKEN
```

请求体：
```json
{
  "userid": "employee_user_id",
  "offset": 0,
  "size": 20
}
```

响应关键字段：
- `template_list[].template_id` — 模板 ID（填入 config.json）
- `template_list[].name` — 模板名称
- `template_list[].report_type` — 1=日报, 2=周报, 3=月报

### 查看模板字段详情

```http
POST https://oapi.dingtalk.com/topapi/report/template/detail?access_token=TOKEN
```

请求体：
```json
{
  "userid": "employee_user_id",
  "template_id": "template_id_here"
}
```

响应中 `template.contents[]` 包含各字段的 `key`、`type`、`sort` 等信息。

> **注意**：部分版本的 API 可能不返回 contents，此时字段 key 通常等于创建模板时填写的字段名称。

---

## 创建日志（发送日报）

```http
POST https://oapi.dingtalk.com/topapi/report/create?access_token=TOKEN
```

请求体（注意 `create_report_param` 包裹层）：
```json
{
  "create_report_param": {
    "userid": "employee_user_id",
    "template_id": "template_id",
    "dd_from": "your-app-name",
    "to_chat": false,
    "contents": [
      {
        "key": "今日完成工作",
        "sort": "0",
        "type": "1",
        "content_type": "markdown",
        "content": "实际内容文本",
        "value": "实际内容文本"
      },
      {
        "key": "明日工作计划",
        "sort": "1",
        "type": "1",
        "content_type": "markdown",
        "content": "计划内容",
        "value": "计划内容"
      }
    ],
    "to_userids": ["manager_user_id"]
  }
}
```

字段说明：
- `userid` — 日报提交人的 user_id
- `template_id` — 日志模板 ID（从 `listbyuserid` 返回的 `report_code` 字段）
- `dd_from` — 必填，来源标识字符串（任意字符串）
- `to_chat` — 必填，是否发送到聊天（false 只归档不通知）
- `contents[].key` — 模板字段名称（必须与模板字段完全一致）
- `contents[].sort` — 字段排序，**字符串类型**，从 "0" 开始
- `contents[].type` — 字段类型，**字符串类型**，文本字段用 "1"
- `contents[].content_type` — **必须为 "markdown"**（其他值会报 400001）
- `contents[].content` — 字段内容（创建时必填）
- `contents[].value` — 字段内容（与 content 相同内容，两者都需提供）
- `to_userids` — 可选，接收日报的人员 user_id 列表

响应：
```json
{
  "errcode": 0,
  "errmsg": "ok",
  "report_id": "report_id_here"
}
```

常见错误码：
- `40014` — token 无效
- `60011` — 无权限（需申请 `qyapi_report` 权限）
- `80001` — 模板不存在
- `80003` — 字段不匹配（key 写错）

---

## 查询日志（可选）

### 查询员工发送的日志

```http
POST https://oapi.dingtalk.com/topapi/report/list?access_token=TOKEN
```

请求体：
```json
{
  "start_time": 1700000000000,
  "end_time": 1700086400000,
  "userid": "employee_user_id",
  "cursor": 0,
  "size": 20
}
```

- 时间戳单位为**毫秒**
- 响应中 `data_list[].contents[]` 包含各字段内容

---

## 权限申请

在钉钉开放平台「应用管理」→「权限管理」申请以下权限：

| 权限标识 | 说明 |
|---------|------|
| `qyapi_report` | 日志权限（读写日报必须）|
| `qyapi_get_member` | 获取成员信息 |
| `qyapi_get_department_member` | 获取部门成员列表 |

---

## 已知不可用的 API

- `topapi/report/customsave` — **不存在**，调用返回 errcode=22（不合法ApiName）。正确端点是 `topapi/report/create`
- `topapi/report/template/detail` — **不存在**，调用返回「不合法ApiName」
- `topapi/report/template/listbyuserid` — 存在，但若用户无可见模板则返回空列表

替代方案：通过 `topapi/report/list` 查询已有日报记录，从中提取字段结构。

---

## 新版 API（参考）

钉钉同时提供了新版 API（`api.dingtalk.com`），认证方式不同（使用 OAuth 2.0）。
本 skill 使用旧版 OAPI 风格（`oapi.dingtalk.com`），更稳定且文档完善。

如需切换新版 API，参考：
https://open.dingtalk.com/document/orgapp/create-a-log
