#!/usr/bin/env python3
# Author: Sam <772662699@qq.com>
"""
钉钉日报自动生成与发送脚本

功能：
  1. 从 Teambition 获取当天的实际工时
  2. 从 Teambition 获取下一工作日的计划工时
  3. 格式化为钉钉日志模板字段内容
  4. 通过钉钉 API 发送日报（或仅预览不发送）

依赖：pip install requests PyJWT
配置（优先级从低到高）：
  1. references/config.default.json  — skill 内嵌默认配置
  2. ~/.dingtalk-daily/config.json — 本地覆盖（仅需填写与默认不同的字段）
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import date, timedelta

# 匹配项目名中的 "数字-" 和 "客户代码-" 前缀，如 "26-CZJ-" → 去掉后得到真实项目名
_NUM_PREFIX_RE = re.compile(r'^\d+-')
_CLIENT_CODE_RE = re.compile(r'^[A-Z]{2,5}-')


def _normalize_project_name(name: str) -> str:
    """
    去掉项目名中的数字前缀和客户代码前缀，提取真实项目名。
    "26-XX-某智慧城市项目" → "某智慧城市项目"
    "25-XX-某企业服务平台" → "某企业服务平台"
    "公共项目"            → "公共项目"
    """
    name = _NUM_PREFIX_RE.sub("", name)   # 去掉开头的 "数字-"
    name = _CLIENT_CODE_RE.sub("", name)  # 去掉开头的 "大写字母代码-"
    return name

try:
    import jwt
except ImportError:
    print("缺少依赖: pip install PyJWT")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("缺少依赖: pip install requests")
    sys.exit(1)


# ─── 配置 ────────────────────────────────────────────────────────────────────

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CONFIG_FILE = os.path.join(_SCRIPT_DIR, "..", "references", "config.default.json")
_LOCAL_CONFIG_DIR = os.path.expanduser("~/.dingtalk-daily")
_LOCAL_CONFIG_FILE = os.path.join(_LOCAL_CONFIG_DIR, "config.json")


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并两个 dict，override 的值覆盖 base"""
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config(local_path: str = None) -> dict:
    """
    加载配置，优先级：内嵌默认 < 本地覆盖。
    内嵌默认：references/config.default.json（随 skill 分发）
    本地覆盖：~/.dingtalk-daily/config.json（只需填写与默认不同的字段）
    """
    # 1. 读内嵌默认
    if not os.path.exists(_DEFAULT_CONFIG_FILE):
        print(f"内嵌配置不存在: {_DEFAULT_CONFIG_FILE}")
        sys.exit(1)
    with open(_DEFAULT_CONFIG_FILE, encoding="utf-8") as f:
        config = json.load(f)

    # 2. 合并本地覆盖（若存在）
    local = local_path or _LOCAL_CONFIG_FILE
    if os.path.exists(local):
        with open(local, encoding="utf-8") as f:
            overrides = json.load(f)
        config = _deep_merge(config, overrides)

    return config


# ─── 工作日计算 ───────────────────────────────────────────────────────────────

def prev_workday(d: date) -> date:
    """上一个工作日（跳过周末）"""
    d = d - timedelta(days=1)
    while d.weekday() >= 5:  # 5=周六, 6=周日
        d = d - timedelta(days=1)
    return d


def next_workday(d: date) -> date:
    """下一个工作日（跳过周末）"""
    d = d + timedelta(days=1)
    while d.weekday() >= 5:
        d = d + timedelta(days=1)
    return d


# ─── Teambition 认证 ──────────────────────────────────────────────────────────

def tb_jwt_token(app_id: str, app_secret: str) -> str:
    """生成 Teambition JWT App Access Token"""
    now = int(time.time())
    payload = {"iat": now, "_appId": app_id, "exp": now + 3600}
    token = jwt.encode(payload, app_secret, algorithm="HS256", headers={"typ": "jwt", "alg": "HS256"})
    return token if isinstance(token, str) else token.decode("ascii")


def tb_headers(tb_config: dict, user_id: str = None) -> dict:
    """构建 Teambition 请求头"""
    token = tb_jwt_token(tb_config["app_id"], tb_config["app_secret"])
    h = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Tenant-Id": tb_config["organization_id"],
        "X-Tenant-Type": "organization",
    }
    op_id = user_id or tb_config.get("default_user_id", "")
    if op_id:
        h["X-Operator-Id"] = op_id
    return h


def tb_api_base(tb_config: dict) -> str:
    return tb_config.get("api_base", "https://open.teambition.com").rstrip("/")


def ms_to_hours(ms) -> float:
    return round((ms or 0) / 3_600_000, 2)


# ─── 从 Teambition 获取工时数据 ──────────────────────────────────────────────

# 会话级缓存，避免重复调用 API
_task_info_cache: dict = {}
_project_info_cache: dict = {}


def _get_task_full_name(tb_config: dict, user_id: str, task_id: str) -> str:
    """
    通过 API 获取任务的完整名称（"项目名-任务名" 格式）。

    命名规则：
    - 若任务 content 以客户代码前缀开头（如 "GWH-"、"CZJ-"），说明 content 已自带
      "客户代码-项目名-任务名" 结构，直接使用；
    - 否则以 Teambition projectId 对应的项目名作为前缀（如 "公共项目-日常管理"）。

    结果缓存在 _task_info_cache，同一 task_id 只调一次 API。
    """
    if task_id in _task_info_cache:
        return _task_info_cache[task_id]

    base = tb_api_base(tb_config)
    headers = tb_headers(tb_config, user_id)
    full_name = task_id  # 兜底

    try:
        resp = requests.get(
            f"{base}/api/task/info",
            headers=headers,
            params={"taskId": task_id},
            timeout=8,
        )
        resp.raise_for_status()
        task = (resp.json().get("result") or {})
        task_name = task.get("content", "")
        project_id = task.get("projectId", "")

        if task_name:
            raw_proj = _get_project_name(tb_config, user_id, project_id) if project_id else ""
            proj_name = _normalize_project_name(raw_proj) if raw_proj else ""
            full_name = f"{proj_name}-{task_name}" if proj_name else task_name
    except Exception:
        pass

    _task_info_cache[task_id] = full_name
    return full_name


def _get_project_name(tb_config: dict, user_id: str, project_id: str) -> str:
    """通过 API 获取项目名称，缓存结果。"""
    if project_id in _project_info_cache:
        return _project_info_cache[project_id]

    base = tb_api_base(tb_config)
    headers = tb_headers(tb_config, user_id)
    name = ""

    try:
        resp = requests.get(
            f"{base}/api/project/info",
            headers=headers,
            params={"projectId": project_id},
            timeout=8,
        )
        resp.raise_for_status()
        result = resp.json().get("result") or {}
        name = result.get("name", "")
    except Exception:
        pass

    _project_info_cache[project_id] = name
    return name


def fetch_actual_hours(tb_config: dict, user_id: str, date_str: str) -> list:
    """
    查询指定日期的实际工时记录（/api/worktime/query），通过 API 解析任务名。
    不依赖 config 中的 tasks/projects 配置。
    返回: [{"task_id": ..., "task_name": ..., "hours": ..., "description": ...}, ...]
    """
    base = tb_api_base(tb_config)
    headers = tb_headers(tb_config, user_id)

    resp = requests.get(
        f"{base}/api/worktime/query",
        headers=headers,
        params={"userId": user_id, "startDate": date_str, "endDate": date_str, "pageSize": 100},
        timeout=15,
    )
    resp.raise_for_status()
    records = resp.json().get("result", []) or []

    result = []
    for r in records:
        task_id = r.get("objectId", "")
        task_name = _get_task_full_name(tb_config, user_id, task_id)
        result.append({
            "task_id": task_id,
            "task_name": task_name,
            "hours": ms_to_hours(r.get("worktime", 0)),
            "description": r.get("description", ""),
        })
    return result


def fetch_planned_hours(tb_config: dict, user_id: str, date_str: str, **_kwargs) -> list:
    """
    查询指定日期的计划工时记录（/api/plantime/query），通过 API 解析任务名。
    不依赖 config 中的 tasks/projects 配置。
    返回: [{"task_name": ..., "hours": ...}, ...]
    """
    base = tb_api_base(tb_config)
    headers = tb_headers(tb_config, user_id)

    resp = requests.get(
        f"{base}/api/plantime/query",
        headers=headers,
        params={"userId": user_id, "startDate": date_str, "endDate": date_str, "pageSize": 100},
        timeout=15,
    )
    resp.raise_for_status()
    records = resp.json().get("result", []) or []

    result = []
    for r in records:
        task_id = r.get("objectId", "")
        task_name = _get_task_full_name(tb_config, user_id, task_id)
        result.append({
            "task_name": task_name,
            "task_id": task_id,
            "hours": ms_to_hours(r.get("plantime", 0)),
        })
    return result


# ─── 格式化日报内容 ──────────────────────────────────────────────────────────

def _parse_project_task(task_name: str) -> tuple:
    """从 '项目名-任务名' 格式中提取项目和任务，无法拆分则整体归入任务"""
    if "-" in task_name:
        idx = task_name.index("-")
        return task_name[:idx], task_name[idx+1:]
    return "其他", task_name


def _apply_aliases(project: str, aliases: dict) -> str:
    """应用项目别名映射（config 中 report.project_aliases）"""
    return aliases.get(project, project)


def _merge_label(task: str, desc: str) -> str:
    """
    智能合并任务名和工作进展：
    - 无 desc → 直接用任务名
    - desc 与 task 中文字符重叠度 ≥ 50%（含义相近）→ 直接用 desc
    - desc 提供了不同维度的信息 → "task，desc" 自然衔接
    """
    if not desc or not desc.strip():
        return task
    desc = desc.strip()
    cjk = [c for c in task if '\u4e00' <= c <= '\u9fff']
    if cjk and sum(1 for c in cjk if c in desc) / len(cjk) >= 0.5:
        return desc  # 重叠度高，desc 已足够表达
    return f"{task}，{desc}"


def format_actual_content(records: list, date_str: str, project_aliases: dict = None) -> str:
    """
    将实际工时记录格式化为历史风格：

    {M}月{D}日
    1.{项目名}
    1.1.{工作进展 or 任务名}（Xh）
    1.2.{工作进展 or 任务名}（Xh）
    2.{项目名}
    2.1.{工作进展 or 任务名}（Xh）

    工作项优先使用填工时时填写的工作进展（description），无则 fallback 到任务名。
    工时以括号标注。研发部公共项目排最后。
    """
    if not records:
        return f"（{date_str} 无工时记录）"

    aliases = project_aliases or {}
    # 按项目分组，保留原始顺序
    from collections import OrderedDict
    groups = OrderedDict()
    for r in records:
        proj, task = _parse_project_task(r["task_name"])
        proj = _apply_aliases(proj, aliases)
        groups.setdefault(proj, []).append((task, r["hours"], r.get("description", "")))

    # 研发部公共项目排最后
    PUBLIC = "研发部公共项目"
    keys = [k for k in groups if k != PUBLIC]
    if PUBLIC in groups:
        keys.append(PUBLIC)

    # 日期标题（{M}月{D}日，去掉前导零）
    from datetime import date as _date
    d = _date.fromisoformat(date_str)
    header = f"{d.month}月{d.day}日"

    lines = [header]
    for proj_idx, proj in enumerate(keys, 1):
        lines.append(f"{proj_idx}.{proj}")
        for task_idx, (task, hours, desc) in enumerate(groups[proj], 1):
            label = _merge_label(task, desc)
            lines.append(f"{proj_idx}.{task_idx}.{label}")

    return "\n".join(lines)


def format_planned_content(records: list, date_str: str, project_aliases: dict = None) -> str:
    """
    将计划工时记录格式化为历史风格：每行一个项目名，不含工时、不编号。
    研发部公共项目排最后。
    """
    if not records:
        return f"（{date_str} 无计划工时记录）"

    aliases = project_aliases or {}
    # 收集不重复的项目名，保留顺序
    seen = {}
    for r in records:
        proj, _ = _parse_project_task(r["task_name"])
        proj = _apply_aliases(proj, aliases)
        seen[proj] = True

    PUBLIC = "研发部公共项目"
    keys = [k for k in seen if k != PUBLIC]
    if PUBLIC in seen:
        keys.append(PUBLIC)

    return "\n".join(keys)


# ─── 钉钉认证与发送 ───────────────────────────────────────────────────────────

def get_dingtalk_token(appkey: str, appsecret: str) -> str:
    """获取钉钉旧版 OAPI Access Token（用于 oapi.dingtalk.com 接口）"""
    cache_file = os.path.join(_LOCAL_CONFIG_DIR, ".token_cache.json")
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            cache = json.load(f)
        if cache.get("expires_at", 0) > time.time() + 300:
            return cache.get("access_token", "")

    resp = requests.get(
        "https://oapi.dingtalk.com/gettoken",
        params={"appkey": appkey, "appsecret": appsecret},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errcode") != 0:
        raise RuntimeError(f"获取钉钉 token 失败: {data.get('errmsg')}")

    token = data["access_token"]
    expires_in = data.get("expires_in", 7200)
    with open(cache_file, "w") as f:
        json.dump({"access_token": token, "expires_at": time.time() + expires_in}, f)
    return token



def send_dingtalk_log(dd_config: dict, contents_list: list, dry_run: bool = False) -> dict:
    """
    发送钉钉日志（使用 oapi.dingtalk.com/topapi/report/create 端点）。

    contents_list: [{"key": "template_field_key", "value": "内容", "sort": 1}, ...]
    dry_run: True 则只打印不发送
    """
    if dry_run:
        print("\n[预览模式] 将发送以下日志内容：")
        for item in contents_list:
            print(f"\n【{item['key']}】")
            print(item["value"])
        return {"preview": True}

    token = get_dingtalk_token(dd_config["appkey"], dd_config["appsecret"])

    # topapi/report/create 的 contents 格式：
    #   sort/type 为字符串，content_type 必须为 "markdown"，同时提供 content 和 value
    #   markdown 模式下 & 需转义为 &amp; 否则渲染为乱码
    api_contents = [
        {
            "sort": str(c["sort"] - 1),  # API 从 0 开始，sort 为字符串
            "type": "1",
            "content_type": "markdown",
            "key": c["key"],
            "content": c["value"].replace("&", "&amp;"),
            "value": c["value"].replace("&", "&amp;"),
        }
        for c in contents_list
    ]

    param = {
        "userid": dd_config["userid"],
        "template_id": dd_config["template_id"],
        "dd_from": "claude-skill",
        "to_chat": dd_config.get("to_chat", True),  # 默认 True，发给模板配置的接收人
        "contents": api_contents,
    }
    to_users = dd_config.get("to_userids", [])
    if to_users:
        param["to_userids"] = to_users
    body = {"create_report_param": param}

    resp = requests.post(
        f"https://oapi.dingtalk.com/topapi/report/create?access_token={token}",
        json=body,
        timeout=15,
    )
    resp.raise_for_status()
    result = resp.json()
    if result.get("errcode") != 0:
        raise RuntimeError(f"发送失败 (errcode={result.get('errcode')}): {result.get('errmsg')}")
    return result


# ─── 主流程 ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="钉钉日报自动生成与发送")
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--date", default=None, help="报告日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--user", default=None, help="Teambition 用户 ID（覆盖配置）")
    parser.add_argument("--preview", action="store_true", help="仅预览，不发送")
    parser.add_argument("--send", action="store_true", help="确认发送（默认仅预览）")
    args = parser.parse_args()

    config = load_config(args.config)
    tb_config = config.get("teambition", {})
    dd_config = config.get("dingtalk", {})
    report_config = config.get("report", {})

    # 确定报告日期
    today = date.fromisoformat(args.date) if args.date else date.today()
    actual_date = today                  # 今日完成工作 = 当天
    plan_date = next_workday(today)      # 明日工作计划 = 下一工作日

    # 确定目标用户 ID
    user_id = args.user or tb_config.get("user_id", "")
    if not user_id:
        print("错误: 未指定用户 ID，请在 config.json 的 teambition.user_id 中配置，或使用 --user 参数")
        sys.exit(1)

    print(f"报告日期: {today}  |  实际工时: {actual_date}  计划工时: {plan_date}  |  用户: {user_id}")
    print()

    # ── 获取 Teambition 数据 ──
    print(f"正在获取 {actual_date} 的实际工时...")
    actual_records = fetch_actual_hours(tb_config, user_id, str(actual_date))
    print(f"  找到 {len(actual_records)} 条记录")

    # 无工时记录 → 提示并退出，不发送
    if not actual_records:
        print(f"\n⚠️  {actual_date} 没有实际工时记录，无需发送日报。")
        sys.exit(0)

    print(f"正在获取 {plan_date} 的计划工时...")
    planned_records = fetch_planned_hours(tb_config, user_id, str(plan_date))
    print(f"  找到 {len(planned_records)} 条记录")

    # 明天无计划工时 → 用今天的计划兜底
    if not planned_records:
        print(f"  明天（{plan_date}）无计划工时，改用今天（{today}）的计划...")
        planned_records = fetch_planned_hours(tb_config, user_id, str(today))
        print(f"  找到 {len(planned_records)} 条记录")
        plan_date = today  # 更新用于格式化的日期标注

    # ── 格式化内容 ──
    field_keys = dd_config.get("field_keys", {})
    actual_key = field_keys.get("yesterday_actual", "昨日完成工作")
    plan_key = field_keys.get("tomorrow_plan", "今日计划工作")

    project_aliases = report_config.get("project_aliases", {})
    actual_text = format_actual_content(actual_records, str(actual_date), project_aliases)
    planned_text = format_planned_content(planned_records, str(plan_date), project_aliases)

    contents = []
    sort_idx = 1

    contents.append({"key": actual_key, "value": actual_text, "sort": sort_idx})
    sort_idx += 1

    contents.append({"key": plan_key, "value": planned_text, "sort": sort_idx})
    sort_idx += 1

    # 追加额外静态字段（如"遇到的问题"）
    for extra in dd_config.get("extra_fields", []):
        contents.append({"key": extra["key"], "value": extra.get("value", ""), "sort": sort_idx})
        sort_idx += 1

    # ── 预览 ──
    print("\n" + "=" * 60)
    print(f"【{actual_key}】（{actual_date}）")
    print(actual_text)
    print()
    print(f"【{plan_key}】（{plan_date}）")
    print(planned_text)
    for extra in dd_config.get("extra_fields", []):
        print()
        print(f"【{extra['key']}】")
        print(extra.get("value", ""))
    print("=" * 60)

    # ── 发送 ──
    if not args.send and not args.preview:
        print("\n提示：使用 --send 发送日报，或 --preview 仅预览（不发送）")
        return

    if args.send:
        print("\n正在发送到钉钉日志...")
        result = send_dingtalk_log(dd_config, contents, dry_run=False)
        print(f"✅ 发送成功！日志 ID: {result.get('report_id', result)}")
    else:
        send_dingtalk_log(dd_config, contents, dry_run=True)


if __name__ == "__main__":
    main()
