---
name: dingtalk-daily-report
author: Sam <772662699@qq.com>
description: >
  钉钉日报自动生成与发送工具。从 Teambition 获取「上一工作日」的实际工时和「下一工作日」的计划工时，自动填入钉钉日志模板并发送。
  当用户提到「发钉钉日报」、「生成日报」、「钉钉日志」、「daily report」、「发日报」、「汇报工作」、「写日报」、「自动日报」、「日报内容从 Teambition 里取」时，务必使用此 skill。
  即使用户只是说「帮我发今天的日报」、「把工时报告发到钉钉」、「日报用 Teambition 数据自动填」，也应该触发此 skill。
---

# 钉钉日报自动生成 Skill

自动从 Teambition 拉取工时数据 → 格式化为日报内容 → 通过钉钉日志 API 发送。

## 前置条件

1. 用户在钉钉中已建立日报模板（知道模板 ID 和字段名）
2. 钉钉凭据（appkey/appsecret/userid/template_id）和 Teambition 凭据（app_id/app_secret/organization_id/user_id）已填写在内嵌配置或本地覆盖文件中

首次使用时，引导用户阅读 `references/setup-guide.md` 完成配置。

## 核心工作流程

### 判断状态

配置加载优先级（低 → 高）：
1. `references/config.default.json`（skill 内嵌，始终加载，**不需要本地文件存在**）
2. `~/.dingtalk-daily/config.json`（本地覆盖，仅需填写与内嵌默认不同的字段，存在则合并）

**状态判断基于合并后的配置**，而非本地文件是否存在：
- 合并后 `dingtalk.appkey`/`appsecret`/`userid`/`template_id` 任一为空 → 进入「首次配置流程」
- 合并后 `teambition.app_id`/`app_secret`/`organization_id` 任一为空 → 进入「首次配置流程」
- 合并后 `teambition.user_id` 为空 → 提示配置（可用 `--user` 参数临时覆盖）
- 凭据完整 → 直接执行日报生成/发送

### 首次配置流程

引导用户依次完成（参考 `references/setup-guide.md`）：

1. **创建钉钉企业应用**（如还没有），申请 `qyapi_report` 权限
2. **在钉钉创建日报模板**（工作台 → 日志 → 模板管理），记下字段名称
3. 运行 `python scripts/dd_config.py init` 生成配置模板
4. 编辑 `~/.dingtalk-daily/config.json` 填写凭据
5. 运行 `python scripts/dd_config.py templates` 获取 template_id
6. 运行 `python scripts/dd_config.py template-detail <id>` 确认字段 key
7. 运行 `python scripts/dd_config.py verify` 验证连通性

### 生成并预览日报

```bash
python scripts/dd_report.py --preview
```

脚本会：
1. 计算日期：今天的上一工作日（实际工时）和下一工作日（计划工时）
2. 查询 Teambition `/api/worktime/query` 获取实际工时记录
3. 查询 Teambition `/api/plantime/query` 获取计划工时记录
4. 格式化为钉钉模板字段内容并显示

### 发送日报

```bash
python scripts/dd_report.py --send
```

调用 `POST https://oapi.dingtalk.com/topapi/report/create` 发送。

### 其他常用命令

```bash
# 为指定日期生成日报（如今天是周一，查询上周五→下周一）
python scripts/dd_report.py --date 2026-03-21 --send

# 为指定用户发送（覆盖配置中的 user_id）
python scripts/dd_report.py --user tb_user_id --send

# 更新/查看配置
python scripts/dd_config.py verify
python scripts/dd_config.py templates
python scripts/dd_config.py template-detail TEMPLATE_ID
```

## 配置文件说明

配置由两层合并而成（内嵌 < 本地覆盖）：
- **内嵌**：`references/config.default.json`（随 skill 分发，含凭据时开箱即用）
- **本地覆盖**：`~/.dingtalk-daily/config.json`（不存在不报错，存在则覆盖同名字段）

`~/.dingtalk-daily/config.json` 关键字段（只需填写与内嵌默认不同的部分）：

```json
{
  "dingtalk": {
    "appkey": "钉钉应用 AppKey",
    "appsecret": "钉钉应用 AppSecret",
    "userid": "你的钉钉 user_id",
    "template_id": "日报模板 ID",
    "field_keys": {
      "yesterday_actual": "今日完成工作",  // 必须与模板字段名一致
      "tomorrow_plan": "明日工作计划"
    },
    "extra_fields": [
      {"key": "其他事项", "value": "无"}  // 固定值字段
    ]
  },
  "teambition": {
    "user_id": "你的 Teambition 用户 ID"
  },
  "report": {
    "project_aliases": {}  // 项目别名映射，如 {"旧名": "新名"}
  }
}
```

## 名称解析逻辑

- **实际工时**：通过 `/api/worktime/query`（by userId + date）查询，objectId 通过 `/api/task/info` 和 `/api/project/info` API 解析为「项目名-任务名」
- **计划工时**：通过 `/api/plantime/query`（by userId + date）查询，同样通过 API 解析任务名
- **日期计算**：自动跳过周末（周六/周日），prev_workday / next_workday

## 错误处理

| 场景 | 处理方式 |
|------|---------|
| 合并后凭据仍为空 | 引导填写缺失字段（内嵌或本地覆盖均可） |
| Teambition token 过期 | JWT 自动重新生成（每次请求前生成） |
| 钉钉 token 过期 | 自动刷新（缓存在 `~/.dingtalk-daily/.token_cache.json`）|
| 无计划工时记录 | 显示「无计划工时记录」，不阻止发送 |
| 钉钉 errcode=80003 | 字段 key 不匹配，引导用户检查 field_keys 配置 |
| 钉钉 errcode=60011 | 应用缺少 `qyapi_report` 权限，引导去开放平台申请 |

## 参考文档

- `references/setup-guide.md` — 完整配置步骤（首次使用必读）
- `references/dingtalk-api.md` — 钉钉 API 接口细节和错误码
