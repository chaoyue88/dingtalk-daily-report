# 钉钉日报 Skill 配置指南

## 前置条件

1. **Teambition 工时 skill** 已配置好（`~/.teambition/config.json` 存在）
2. **钉钉企业内部应用** 已创建，且有日志权限
3. **钉钉日志模板** 已创建（在钉钉 App → 工作 → 日志 → 模板管理中创建）
4. Python 依赖：`pip install requests PyJWT`

---

## 第一步：创建钉钉企业内部应用

如果还没有应用：

1. 打开 [钉钉开放平台](https://open.dingtalk.com/)，进入「应用管理」
2. 创建「企业内部应用 - H5 微应用」
3. 在「权限管理」中申请以下权限：
   - `qyapi_report` — 日志权限
   - 通讯录权限（`qyapi_get_member` 等，用于获取 user_id）
4. 记录 **AppKey** 和 **AppSecret**

---

## 第二步：获取你的钉钉 user_id

方式一（推荐）：在钉钉管理后台
1. 登录 [钉钉管理后台](https://oa.dingtalk.com)
2. 通讯录 → 成员管理 → 点击你的头像 → 查看「userId」字段

方式二：通过 API
```bash
# 先配置 appkey/appsecret，然后运行
curl "https://oapi.dingtalk.com/gettoken?appkey=YOUR_KEY&appsecret=YOUR_SECRET"
# 用获取的 token 查询用户信息
curl -X POST "https://oapi.dingtalk.com/user/getbyunionid?access_token=TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"unionid": "YOUR_UNIONID"}'
```

---

## 第三步：创建日志模板

1. 打开钉钉 App → 工作台 → 日志
2. 点击右上角「管理」→「模板管理」→「新建模板」
3. 添加字段，推荐字段：

| 字段名称 | 类型 | 说明 |
|---------|------|------|
| 今日完成工作 | 多行文本 | 填写当日实际工时（自动填入）|
| 明日工作计划 | 多行文本 | 填写明日计划工时（自动填入）|
| 其他事项 | 多行文本 | 障碍/风险（可设为固定值"无"）|

4. 保存模板，**记录字段的显示名称**（即「field key」，通常就是字段名本身）

---

## 第四步：初始化 skill 配置

```bash
# 在 skill 目录下执行
python scripts/dd_config.py init
```

这会在 `~/.dingtalk-daily/config.json` 生成配置模板（权限 600）。

---

## 第五步：编辑配置文件

```bash
vim ~/.dingtalk-daily/config.json
```

```json
{
  "dingtalk": {
    "appkey": "ding1234567890",          // 钉钉应用的 AppKey
    "appsecret": "your_secret_here",     // 钉钉应用的 AppSecret
    "userid": "your_dingtalk_userid",    // 你的钉钉 user_id
    "template_id": "template_id_here",  // 日志模板 ID（下一步获取）
    "field_keys": {
      "yesterday_actual": "今日完成工作",  // 必须与钉钉模板字段名一致
      "tomorrow_plan":    "明日工作计划"
    },
    "extra_fields": [
      {"key": "其他事项", "value": "无"}  // 固定值字段
    ],
    "to_userids": []  // 可选：发送给上级的 user_id 列表
  },
  "teambition": {
    "user_id": "your_tb_user_id"  // 你的 Teambition 用户 ID
  },
  "report": {
    "project_aliases": {}  // 可选：项目名别名映射，如 {"旧名": "新名"}
  }
}
```

---

## 第六步：获取模板 ID 和字段名

```bash
# 列出所有可用模板
python scripts/dd_config.py templates

# 查看特定模板的字段名（找到 field key）
python scripts/dd_config.py template-detail TEMPLATE_ID_HERE
```

> **提示**：钉钉日志 API 中，字段的 `key` 通常就是创建模板时设置的字段名称（如「今日完成工作」）。
> 如果 API 未能返回字段列表，直接使用模板中显示的字段名称即可。

---

## 第七步：验证配置

```bash
python scripts/dd_config.py verify
```

如果两端都显示 ✅，说明配置正确。

---

## 使用

### 日常使用

```bash
# 预览日报（不发送）
python scripts/dd_report.py --preview

# 发送日报
python scripts/dd_report.py --send

# 为特定日期生成日报（如今天是周一，手动生成上周五的）
python scripts/dd_report.py --date 2026-03-20 --send
```

### 自动定时发送

在 crontab 中配置（每天 17:30 自动发送）：

```bash
crontab -e
# 添加以下行：
30 17 * * 1-5 cd /path/to/skill && python scripts/dd_report.py --send >> ~/.dingtalk-daily/cron.log 2>&1
```

或使用 Claude Code 的 `/schedule` skill 设置定时任务。

---

## 常见问题

### 问：找不到计划工时记录

确认：
1. 你已在 Teambition 中为明天（下一工作日）创建了计划工时记录
2. 脚本会自动回退：若明天无计划工时，则改用今天的计划工时
3. 检查 teambition.user_id 是否正确

### 问：errcode=40014 (无效 token)

重新运行 `python scripts/dd_config.py verify` 测试 token 获取是否正常。

### 问：errcode=60011 (无权限)

在钉钉开放平台为你的应用添加 `qyapi_report` 权限，并重新提交审核。

### 问：template_id 怎么找

运行 `python scripts/dd_config.py templates`，或在钉钉管理后台 → 日志管理中查看。

### 问：字段 key 填什么

运行 `python scripts/dd_config.py template-detail <template_id>` 获取，
通常就是在钉钉创建模板时写的字段名称（如「今日完成工作」）。
