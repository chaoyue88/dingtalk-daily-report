# 钉钉日报自动生成工具

> Author: Sam <772662699@qq.com>

从 Teambition 自动拉取工时数据，格式化为日报内容，通过钉钉日志 API 一键发送。

## 功能

- 自动获取**当天实际工时**和**下一工作日计划工时**
- 按项目分组，自动编号，公共项目排最后
- 支持预览模式（不发送）
- 无实际工时时自动跳过，不发送空日报
- 明天无计划工时时自动回退使用今天的计划

## 安装依赖

```bash
pip install requests PyJWT
```

## 快速开始

### 1. 初始化配置

```bash
python scripts/dd_config.py init
```

在 `~/.dingtalk-daily/config.json` 生成配置模板，填写以下字段：

```json
{
  "dingtalk": {
    "appkey": "钉钉应用 AppKey",
    "appsecret": "钉钉应用 AppSecret",
    "userid": "你的钉钉 user_id",
    "template_id": "日报模板 ID",
    "field_keys": {
      "yesterday_actual": "今日完成工作",
      "tomorrow_plan": "明日工作计划"
    },
    "extra_fields": [
      {"key": "其他事项", "value": "无"}
    ]
  },
  "teambition": {
    "app_id": "Teambition 应用 ID",
    "app_secret": "Teambition 应用密钥",
    "organization_id": "组织 ID",
    "user_id": "你的 Teambition 用户 ID"
  },
  "report": {
    "project_aliases": {
      "原始项目名": "显示名称"
    }
  }
}
```

### 2. 获取钉钉模板 ID

```bash
# 列出可用模板
python scripts/dd_config.py templates

# 查看模板字段名（确认 field_keys 配置）
python scripts/dd_config.py template-detail TEMPLATE_ID
```

### 3. 验证配置

```bash
python scripts/dd_config.py verify
```

### 4. 预览并发送

```bash
# 预览今天的日报
python scripts/dd_report.py --preview

# 发送今天的日报
python scripts/dd_report.py --send

# 为指定日期预览/发送
python scripts/dd_report.py --date 2026-03-20 --preview
python scripts/dd_report.py --date 2026-03-20 --send
```

## 日报格式示例

```
【今日完成工作】
3月20日
1.智慧城市项目A
1.1.需求开发，功能跟进和问题处理
2.企业服务项目B
2.1.功能开发跟进和问题处理
3.公共项目
3.1.日常管理和沟通
3.2.系统运维

【明日工作计划】
企业服务项目B
智慧城市项目A
公共项目

【其他事项】
无
```

## 命令速查

| 命令 | 说明 |
|------|------|
| `dd_config.py init` | 生成本地配置模板 |
| `dd_config.py verify` | 验证配置和 API 连通性 |
| `dd_config.py templates` | 列出钉钉日报模板 |
| `dd_config.py template-detail ID` | 查看模板字段名 |
| `dd_report.py --preview` | 预览今日日报 |
| `dd_report.py --send` | 发送今日日报 |
| `dd_report.py --date YYYY-MM-DD --preview` | 预览指定日期日报 |
| `dd_report.py --date YYYY-MM-DD --send` | 发送指定日期日报 |
| `dd_report.py --user USER_ID --send` | 为指定用户发送 |

## 前置条件

- 钉钉企业内部应用，需申请 `qyapi_report` 权限
- Teambition 组织应用（Open API）
- 在钉钉工作台已创建日报模板

详细配置步骤参考 [setup-guide.md](references/setup-guide.md)。

## 错误排查

| 错误 | 原因 | 解决 |
|------|------|------|
| `errcode=80003` | 字段 key 不匹配 | 运行 `dd_config.py template-detail` 确认字段名 |
| `errcode=60011` | 应用缺少 `qyapi_report` 权限 | 到钉钉开放平台申请权限 |
| 无工时记录 | 当天未填工时 | 在 Teambition 补填实际工时后重试 |
| JWT 错误 | Teambition 凭据有误 | 检查 `app_id` / `app_secret` |

## 定时发送

每天 17:30 自动发送（crontab）：

```bash
30 17 * * 1-5 cd /path/to/dingtalk-daily-report && python scripts/dd_report.py --send >> ~/.dingtalk-daily/cron.log 2>&1
```
