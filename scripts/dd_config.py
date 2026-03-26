#!/usr/bin/env python3
# Author: Sam <772662699@qq.com>
"""
钉钉日报 skill 配置管理工具

用法:
  python scripts/dd_config.py init           # 创建配置文件模板
  python scripts/dd_config.py verify         # 验证配置（测试两端连通性）
  python scripts/dd_config.py templates      # 列出钉钉日志模板（帮助找 template_id）
  python scripts/dd_config.py template-detail TEMPLATE_ID  # 查看模板字段（找 field key）
"""

import argparse
import json
import os
import sys
import time

try:
    import requests
except ImportError:
    print("缺少依赖: pip install requests PyJWT")
    sys.exit(1)

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CONFIG_FILE = os.path.join(_SCRIPT_DIR, "..", "references", "config.default.json")
CONFIG_DIR = os.path.expanduser("~/.dingtalk-daily")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


# ─── 配置模板（本地覆盖文件的示例，仅需填写与内嵌默认不同的字段）─────────────────

CONFIG_TEMPLATE = {
    "_comment": "只需填写与 scripts/config.default.json 不同的字段，其余留空即可",
    "dingtalk": {
        "appkey": "",
        "appsecret": "",
        "userid": "",
        "template_id": "",
        "field_keys": {
            "yesterday_actual": "今日完成工作",
            "tomorrow_plan": "明日工作计划"
        },
        "extra_fields": [
            {"key": "其他事项", "value": "无"}
        ],
        "to_userids": []
    },
    "teambition": {
        "app_id": "",
        "app_secret": "",
        "organization_id": "",
        "api_base": "https://open.teambition.com",
        "user_id": ""
    },
    "report": {
        "project_aliases": {}
    }
}

CONFIG_COMMENTS = """
# 配置说明：
#
# dingtalk.appkey / appsecret
#   钉钉企业内部应用的 AppKey 和 AppSecret
#   位置：钉钉开放平台 → 应用管理 → 选择应用 → 基础信息
#
# dingtalk.userid
#   发送日报的用户钉钉 user_id（注意：是钉钉内部 userid，非手机号）
#   获取方式：运行 `python scripts/dd_config.py templates` 会尝试列出应用信息
#   或在钉钉管理后台 → 通讯录 → 人员详情中查看
#
# dingtalk.template_id
#   日志模板 ID。先在钉钉「日志」功能中创建模板（或让管理员创建），
#   再运行 `python scripts/dd_config.py templates` 获取 template_id
#
# dingtalk.field_keys
#   模板字段键名映射。键名必须与钉钉模板中字段名称完全一致。
#   运行 `python scripts/dd_config.py template-detail TEMPLATE_ID` 查看字段名
#
# dingtalk.extra_fields
#   额外静态字段（如"遇到的问题"固定填"无"）
#   格式: [{"key": "字段名称", "value": "固定内容"}]
#
# teambition.user_id
#   你的 Teambition 用户 ID
#
# report.project_aliases
#   项目名别名映射，用于将 Teambition 项目名映射为日报中的显示名
#   格式: {"原始项目名": "显示名称"}
"""


def load_config():
    """加载配置：内嵌默认 + 本地覆盖合并"""
    if not os.path.exists(_DEFAULT_CONFIG_FILE):
        return None
    with open(_DEFAULT_CONFIG_FILE, encoding="utf-8") as f:
        config = json.load(f)
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            overrides = json.load(f)
        config = _deep_merge(config, overrides)
    return config


def get_dingtalk_token(appkey: str, appsecret: str) -> str:
    resp = requests.get(
        "https://oapi.dingtalk.com/gettoken",
        params={"appkey": appkey, "appsecret": appsecret},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errcode") != 0:
        raise RuntimeError(f"获取 token 失败: {data.get('errmsg')}")
    return data["access_token"]


# ─── 命令：init ───────────────────────────────────────────────────────────────

def cmd_init(args):
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)

    if os.path.exists(CONFIG_FILE) and not args.force:
        print(f"配置文件已存在: {CONFIG_FILE}")
        print("使用 --force 覆盖")
        return

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(CONFIG_TEMPLATE, f, indent=2, ensure_ascii=False)
    os.chmod(CONFIG_FILE, 0o600)

    print(f"✅ 配置文件已创建: {CONFIG_FILE}")
    print(f"   权限已设为 600（仅所有者可读写）")
    print()
    print("下一步：")
    print("  1. 编辑配置文件，填写钉钉 appkey/appsecret/userid/template_id")
    print("  2. 填写 teambition.user_id（你的 Teambition 用户 ID）")
    print("  3. 运行 `python scripts/dd_config.py templates` 获取模板 ID 和字段名")
    print("  4. 运行 `python scripts/dd_config.py verify` 验证配置")
    print()
    print(CONFIG_COMMENTS)


# ─── 命令：verify ─────────────────────────────────────────────────────────────

def cmd_verify(args):
    config = load_config()
    if not config:
        print(f"内嵌配置不存在: {_DEFAULT_CONFIG_FILE}")
        sys.exit(1)

    dd = config.get("dingtalk", {})
    tb = config.get("teambition", {})

    errors = []
    warnings = []

    # 检查必填字段
    for field in ["appkey", "appsecret", "userid", "template_id"]:
        if not dd.get(field):
            errors.append(f"dingtalk.{field} 未配置")
    for field in ["app_id", "app_secret", "organization_id"]:
        if not tb.get(field):
            errors.append(f"teambition.{field} 未配置")

    if not tb.get("user_id"):
        warnings.append("teambition.user_id 未配置")

    if errors:
        print("❌ 配置校验失败：")
        for e in errors:
            print(f"   - {e}")
        sys.exit(1)

    # 测试钉钉连通性
    print("测试钉钉 API 连通性...", end=" ", flush=True)
    try:
        token = get_dingtalk_token(dd["appkey"], dd["appsecret"])
        print(f"✅ 获取 token 成功（前 20 字符：{token[:20]}...）")
    except Exception as e:
        print(f"❌ 失败: {e}")
        sys.exit(1)

    # 测试 Teambition 连通性
    print("测试 Teambition API 连通性...", end=" ", flush=True)
    try:
        import jwt as pyjwt
        now = int(time.time())
        payload = {"iat": now, "_appId": tb["app_id"], "exp": now + 3600}
        tb_token = pyjwt.encode(payload, tb["app_secret"], algorithm="HS256",
                                headers={"typ": "jwt", "alg": "HS256"})
        if isinstance(tb_token, bytes):
            tb_token = tb_token.decode("ascii")
        resp = requests.get(
            f"{tb.get('api_base', 'https://open.teambition.com')}/api/org/info",
            headers={
                "Authorization": f"Bearer {tb_token}",
                "X-Tenant-Id": tb["organization_id"],
                "X-Tenant-Type": "organization",
            },
            params={"orgId": tb["organization_id"]},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        org_name = data.get("result", {}).get("name", "unknown") if isinstance(data, dict) else "unknown"
        print(f"✅ 连接成功（组织: {org_name}）")
    except Exception as e:
        print(f"❌ 失败: {e}")
        sys.exit(1)

    if warnings:
        print("\n⚠️  警告：")
        for w in warnings:
            print(f"   - {w}")

    print("\n✅ 配置验证通过！")
    print("   运行 `python scripts/dd_report.py --preview` 预览日报内容")


# ─── 命令：templates ──────────────────────────────────────────────────────────

def cmd_templates(args):
    config = load_config()
    if not config:
        print("请先运行: python scripts/dd_config.py init")
        sys.exit(1)

    dd = config.get("dingtalk", {})
    if not dd.get("appkey") or not dd.get("appsecret"):
        print("请先在配置文件中填写 dingtalk.appkey 和 dingtalk.appsecret")
        sys.exit(1)

    if not dd.get("userid"):
        print("请先在配置文件中填写 dingtalk.userid")
        sys.exit(1)

    token = get_dingtalk_token(dd["appkey"], dd["appsecret"])

    resp = requests.post(
        f"https://oapi.dingtalk.com/topapi/report/template/listbyuserid?access_token={token}",
        json={"userid": dd["userid"], "offset": 0, "size": 20},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("errcode") != 0:
        print(f"查询失败: {data.get('errmsg')}")
        sys.exit(1)

    templates = data.get("template_list", [])
    if not templates:
        print("未找到日志模板。请先在钉钉「日志」功能中创建模板，或联系管理员。")
        return

    print(f"找到 {len(templates)} 个模板：\n")
    for t in templates:
        print(f"  template_id: {t.get('template_id')}")
        print(f"  名称: {t.get('name')}")
        print(f"  创建者: {t.get('creator_name', '')}")
        print(f"  类型: {'日报' if t.get('report_type') == 1 else '其他'}")
        print()

    print("运行 `python scripts/dd_config.py template-detail TEMPLATE_ID` 查看字段名")


# ─── 命令：template-detail ────────────────────────────────────────────────────

def cmd_template_detail(args):
    """
    钉钉未提供 template/detail 公开 API。
    改为查询该模板最近的一条日报记录，从中提取字段名。
    如果还没有日报记录，则给出人工查看的指引。
    """
    config = load_config()
    if not config:
        print("请先运行: python scripts/dd_config.py init")
        sys.exit(1)

    dd = config.get("dingtalk", {})
    token = get_dingtalk_token(dd["appkey"], dd["appsecret"])

    # 查询该模板最近 5 条日报，从中提取字段结构
    import time as _time
    end_ms = int(_time.time() * 1000)
    start_ms = end_ms - 30 * 24 * 3600 * 1000  # 最近 30 天

    resp = requests.post(
        f"https://oapi.dingtalk.com/topapi/report/list?access_token={token}",
        json={
            "template_id": args.template_id,
            "start_time": start_ms,
            "end_time": end_ms,
            "cursor": 0,
            "size": 5,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("errcode") != 0:
        print(f"查询失败: {data.get('errmsg')}")
        sys.exit(1)

    records = (data.get("result") or {}).get("data_list") or []
    if records:
        # 从第一条记录里提取字段名
        contents = records[0].get("contents", []) or []
        if contents:
            print(f"模板 {args.template_id} 的字段列表（从已有日报中提取）：\n")
            for i, c in enumerate(contents):
                key = c.get("key", "?")
                print(f"  [{i+1}] key: \"{key}\"")
            print()
            print("将字段名填入 ~/.dingtalk-daily/config.json 的 field_keys：")
            print('  "field_keys": {')
            if len(contents) >= 1:
                print(f'    "yesterday_actual": "{contents[0].get("key", "昨日完成工作")}",')
            if len(contents) >= 2:
                print(f'    "tomorrow_plan":    "{contents[1].get("key", "今日计划工作")}"')
            print('  }')
            return

    # 没有已有日报记录，给出手动查看指引
    print(f"模板 {args.template_id} 暂无历史日报记录，无法自动提取字段名。\n")
    print("请手动确认字段名：")
    print("  1. 打开钉钉 App → 工作台 → 日志")
    print("  2. 点击对应模板，手动填写一条测试日报并提交")
    print("  3. 再次运行此命令即可自动提取字段名\n")
    print("  或者直接在钉钉管理后台查看模板字段名称，")
    print("  字段 key 通常就是创建模板时填写的字段名，例如：")
    print('    "昨日完成工作" / "今日计划工作"')


# ─── 入口 ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="钉钉日报 skill 配置管理")
    sub = parser.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="创建配置文件")
    p_init.add_argument("--force", action="store_true", help="强制覆盖已有配置")

    sub.add_parser("verify", help="验证配置连通性")
    sub.add_parser("templates", help="列出可用的钉钉日志模板")

    p_detail = sub.add_parser("template-detail", help="查看模板字段（找 field key）")
    p_detail.add_argument("template_id", help="模板 ID")

    args = parser.parse_args()

    if args.cmd == "init":
        cmd_init(args)
    elif args.cmd == "verify":
        cmd_verify(args)
    elif args.cmd == "templates":
        cmd_templates(args)
    elif args.cmd == "template-detail":
        cmd_template_detail(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
