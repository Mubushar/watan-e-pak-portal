"""Introspect the portal (MCP + REST + auth + agents) and emit docs/reference/*.md.

Run from backend/:  uv run python .../gen_docs.py
Writes:
  docs/reference/MCP_TOOLS.md
  docs/reference/MCP_RESOURCES.md
  docs/reference/MCP_PROMPTS.md
  docs/reference/REST_ENDPOINTS.md
  docs/reference/SETTINGS.md
  docs/reference/CONTENT_MODEL.md
and prints a compact JSON summary to stdout.
"""
import json
import os
import sys

GEN_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(GEN_DIR, "..", ".."))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)
DOCS = os.path.join(ROOT, "docs", "reference")
os.makedirs(DOCS, exist_ok=True)

import server as core  # noqa: E402
import auth  # noqa: E402
import api  # noqa: E402


# ---------------------------------------------------------------- MCP tools
def tool_group(name: str) -> str:
    """Reuse the server's own grouping so the docs can never diverge from portal_catalog."""
    return core._tool_group(name)


async def mcp_tools():
    tools = await core.mcp.list_tools()
    rows = []
    for t in tools:
        desc = (t.description or "").strip().split("\n")[0]
        schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) or {}
        props = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        params = []
        for pname, meta in props.items():
            ptype = meta.get("type", "any")
            if ptype == "array":
                items = meta.get("items") or {}
                ptype = f"array<{items.get('type','any')}>"
            mark = "" if pname in required else "?"
            default = meta.get("default")
            if default is not None and not isinstance(default, (dict, list)):
                ptype = f"{ptype}={json.dumps(default)}"
            elif "anyOf" in meta:
                ptype = "optional"
            params.append(f"`{pname}`{mark}:{ptype}")
        rows.append({"name": t.name, "group": tool_group(t.name), "desc": desc,
                     "params": params, "required": sorted(required)})
    return rows


# ---------------------------------------------------------------- REST
def rest_rows():
    rows = []
    skip = {"openapi", "docs", "docs_oauth2_redirect", "redoc", "swagger_ui_oauth2_redirect"}
    for route in api.app.routes:
        path = getattr(route, "path", None)
        if not path:
            continue
        name = getattr(route, "name", "")
        if name in skip or path.startswith("/openapi"):
            continue
        methods = sorted(getattr(route, "methods", []) or [])
        if not methods:
            methods = ["WEBSOCKET"]
        tags = list(getattr(route, "tags", []) or [])
        summary = (getattr(route, "summary", None) or getattr(route, "description", "") or "")
        rows.append({"path": path, "methods": methods, "tags": tags,
                     "summary": (summary or "").split("\n")[0]})
    rows.sort(key=lambda r: (r["path"]))
    return rows


# ---------------------------------------------------------------- MCP resources
def mcp_resources():
    static, templates = [], []
    for r in core.mcp._resource_manager.list_resources():
        static.append({"uri": str(r.uri), "name": r.name, "desc": (r.description or "")})
    for t in core.mcp._resource_manager.list_templates():
        uri = getattr(t, "uri_template", None) or getattr(t, "uriTemplate", None)
        templates.append({"uri": str(uri), "name": t.name,
                          "desc": (t.description or "")})
    static.sort(key=lambda x: x["uri"])
    templates.sort(key=lambda x: x["uri"])
    return static, templates


def mcp_prompts():
    rows = []
    for p in core.mcp._prompt_manager.list_prompts():
        args = []
        for a in (p.arguments or []):
            args.append(f"`{a.name}`" + ("" if a.required else "?"))
        rows.append({"name": p.name, "desc": (p.description or "").strip(),
                     "args": args})
    rows.sort(key=lambda x: x["name"])
    return rows


# ---------------------------------------------------------------- writers
def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return len(text)


def main():
    import asyncio
    tools = asyncio.run(mcp_tools())
    static_res, templates = mcp_resources()
    prompts = mcp_prompts()
    rest = rest_rows()

    # ---- MCP_TOOLS.md
    groups = {}
    for t in tools:
        groups.setdefault(t["group"], []).append(t)
    out = ["# MCP tool reference", "",
           f"Auto-generated from `server.py` — **{len(tools)} tools** across "
           f"**{len(groups)} groups**. Regenerate with "
           "`uv run python docs/_gen/gen_docs.py` from the repository root's `backend/`.", "",
           "Legend: `?` = optional parameter. Types are the JSON-Schema types the "
           "server advertises to MCP clients.", "",
           "| Group | Tools |", "| --- | --- |"]
    for g in sorted(groups, key=lambda k: (-len(groups[k]), k)):
        out.append(f"| [{g}](#{g.replace('_', '-')}) | {len(groups[g])} |")
    out.append("")
    for g in sorted(groups):
        out += [f"## {g}", "", f"{len(groups[g])} tools.", "",
                "| Tool | Purpose | Parameters |", "| --- | --- | --- |"]
        for t in sorted(groups[g], key=lambda x: x["name"]):
            params = ", ".join(t["params"]) or "—"
            desc = t["desc"].replace("|", "\\|")
            out.append(f"| `{t['name']}` | {desc} | {params} |")
        out.append("")
    write(os.path.join(DOCS, "MCP_TOOLS.md"), "\n".join(out) + "\n")

    # ---- MCP_RESOURCES.md
    out = ["# MCP resources & templates", "",
           f"**{len(static_res)} resources** and **{len(templates)} resource templates**.", "",
           "## Resources", "", "| URI | Name | Description |", "| --- | --- | --- |"]
    for r in static_res:
        out.append(f"| `{r['uri']}` | {r['name']} | {r['desc'].replace('|', chr(92) + '|')} |")
    out += ["", "## Resource templates", "",
            "Templates take URI parameters, e.g. `messaging://conversation/{conversation_id}`.",
            "", "| URI template | Name | Description |", "| --- | --- | --- |"]
    for t in templates:
        out.append(f"| `{t['uri']}` | {t['name']} | {t['desc'].replace('|', chr(92) + '|')} |")
    out.append("")
    write(os.path.join(DOCS, "MCP_RESOURCES.md"), "\n".join(out) + "\n")

    # ---- MCP_PROMPTS.md
    out = ["# MCP prompts", "", f"**{len(prompts)} prompts**.", "",
           "| Prompt | Arguments | Purpose |", "| --- | --- | --- |"]
    for p in prompts:
        out.append(f"| `{p['name']}` | {', '.join(p['args']) or '—'} | "
                   f"{p['desc'].replace('|', chr(92) + '|')} |")
    out.append("")
    write(os.path.join(DOCS, "MCP_PROMPTS.md"), "\n".join(out) + "\n")

    # ---- REST_ENDPOINTS.md
    tags = {}
    for r in rest:
        tag = r["tags"][0] if r["tags"] else "other"
        tags.setdefault(tag, []).append(r)
    out = ["# REST endpoint reference", "",
           f"Auto-generated from the FastAPI app — **{len(rest)} routes** across "
           f"**{len(tags)} tags**. Every route calls the same function the MCP tool of the "
           "same name calls, so behaviour can never drift.", "",
           "| Tag | Routes |", "| --- | --- |"]
    for t in sorted(tags, key=lambda k: (-len(tags[k]), k)):
        out.append(f"| [{t}](#{t.replace('_', '-')}) | {len(tags[t])} |")
    out.append("")
    for t in sorted(tags):
        out += [f"## {t}", "", f"{len(tags[t])} routes.", "",
                "| Method(s) | Path | Purpose |", "| --- | --- | --- |"]
        for r in sorted(tags[t], key=lambda x: x["path"]):
            out.append(f"| {', '.join(r['methods'])} | `{r['path']}` | "
                       f"{r['summary'].replace('|', chr(92) + '|')} |")
        out.append("")
    write(os.path.join(DOCS, "REST_ENDPOINTS.md"), "\n".join(out) + "\n")

    # ---- SETTINGS.md
    snap = core._settings_snapshot()
    out = ["# Runtime settings", "",
           "Read with the MCP tool `portal_settings(action='get')` or "
           "`GET /portal/settings`; write with `portal_settings(action='update', "
           "updates={...})` or `PUT /portal/settings`.", "",
           "| Group | Keys |", "| --- | --- |"]
    for group in sorted(snap):
        val = snap[group]
        if isinstance(val, dict):
            out.append(f"| `{group}` | {', '.join(f'`{k}`' for k in sorted(val))} |")
    out += ["", "## Current values", "", "```json",
            json.dumps(snap, indent=2, default=str), "```", ""]
    write(os.path.join(DOCS, "SETTINGS.md"), "\n".join(out) + "\n")

    # ---- AGENTS.md
    ag = core.agents
    cfg = ag.AGENTIC_CONFIG
    out = ["# Agentic catalogue", "",
           f"**{len(ag.AGENTS)} agents** grouped into **{len(ag.PRODUCTS)} productised line-ups**. "
           "Autonomy levels: " + ", ".join(f"`{l}`" for l in cfg["autonomy_levels"]) +
           f". Any agent whose autonomy is in {cfg['approval_required_levels']} pauses at a human "
           "approval gate unless the caller overrides it.", "",
           "## Products", "", "| Key | Name | Priority | Category | Agents |",
           "| --- | --- | --- | --- | --- |"]
    for p in ag.PRODUCTS:
        out.append(f"| `{p['key']}` | {p['name']} | {p['priority']} | {p['category']} | "
                   f"{len(p['agents'])} |")
    out += ["", "## Agents", "",
            "| Key | Name | Product | Priority | Autonomy | Approval gate | Summary |",
            "| --- | --- | --- | --- | --- | --- | --- |"]
    for a in ag.AGENTS:
        out.append("| `{}` | {} | `{}` | {} | {} | {} | {} |".format(
            a["key"], a["name"], a.get("product") or "—", a["priority"], a["autonomy"],
            "yes" if a["requires_approval"] else "no", a["summary"].replace("|", "\\|")))
    out += ["", "## Workflows", "",
            "Agents with a scripted workflow list the ordered steps below; a step with "
            "`approval` pauses the run at the human gate.", "",
            "| Agent | Steps |", "| --- | --- |"]
    for a in ag.AGENTS:
        wf = a.get("workflow")
        if not wf:
            continue
        steps = " → ".join(
            f"{s['name']}" + (f" (`{s['tool']}`)" if s.get("tool") else "") +
            (" 🔒" if s.get("requires_approval") else "")
            for s in wf)
        out.append(f"| `{a['key']}` | {steps} |")
    out.append("")
    write(os.path.join(DOCS, "AGENTS.md"), "\n".join(out) + "\n")

    # ---- MESSAGING.md (catalogs only - the narrative lives in MESSAGING_GUIDE.md)
    ms = core.messaging
    c = ms.MESSAGING_CONFIG
    out = ["# Messaging catalogs", "",
           "Generated from `messaging.py`. The end-to-end flows live in "
           "[`../MESSAGING_GUIDE.md`](../MESSAGING_GUIDE.md).", "",
           "## Conversation kinds & states", "",
           f"* **Kinds** — {', '.join('`'+k+'`' for k in ms.CONVERSATION_KINDS)}",
           f"* **Statuses** — {', '.join('`'+k+'`' for k in ms.CONVERSATION_STATUSES)}",
           f"* **Member roles** — {', '.join('`'+k+'`' for k in ms.MEMBER_ROLES)}",
           f"* **Presence** — {', '.join('`'+k+'`' for k in ms.PRESENCE_STATES)}",
           f"* **Message types** — {', '.join('`'+k+'`' for k in ms.MESSAGE_TYPES)}",
           f"* **Action kinds** — {', '.join('`'+k+'`' for k in ms.ACTION_KINDS)}",
           f"* **Action statuses** — {', '.join('`'+k+'`' for k in ms.ACTION_STATUSES)}",
           f"* **Notification states** — {', '.join('`'+k+'`' for k in ms.NOTIFICATION_STATES)}",
           f"* **Outbox channels** — {', '.join('`'+k+'`' for k in ms.OUTBOX_CHANNELS)}",
           f"* **Moderation actions** — {', '.join('`'+k+'`' for k in ms.MODERATION_ACTIONS)}",
           f"* **Report reasons** — {', '.join('`'+k+'`' for k in ms.REPORT_REASONS)}", "",
           "## Default channels", "",
           "| Key | Name | Restricted | Roles allowed | Purpose |",
           "| --- | --- | --- | --- | --- |"]
    for ch in ms.DEFAULT_CHANNELS:
        out.append(f"| `{ch['key']}` | {ch['name']} | {'yes' if ch['restricted'] else 'no'} | "
                   f"{', '.join(ch['roles']) or '—'} | {ch['purpose']} |")
    out += ["", "Staff whose role is in `ADMIN_ROLES` ("
            + ", ".join(f"`{r}`" for r in ms.ADMIN_ROLES)
            + ") may read any non-restricted channel without joining.", "",
            "## Notification categories", "",
            "| Category | Label | Default channels | Urgent |", "| --- | --- | --- | --- |"]
    for key, meta in ms.NOTIFICATION_CATEGORIES.items():
        out.append(f"| `{key}` | {meta['label']} | {', '.join(meta['channels'])} | "
                   f"{'yes' if meta['urgent'] else 'no'} |")
    out += ["", "## Attachment rules", "",
            "Sensitive kinds are gated on the signed expiring link (owner/admin only "
            "for `restricted`, members for the rest). Attachments are always *references* "
            "— bytes never travel in a message.", "",
            "| Kind | Extensions | Sensitive by default |", "| --- | --- | --- |"]
    for key, rule in ms.ATTACHMENT_RULES.items():
        out.append(f"| `{key}` | {', '.join(rule['ext']) or '—'} | "
                   f"{'yes' if rule['sensitive'] else 'no'} |")
    out += ["", "## Runtime limits", "", "| Setting | Value |", "| --- | --- |"]
    for key in ("message_max_length", "edit_window_minutes", "attachment_max_mb",
                "attachment_link_ttl_minutes", "retention_days_default",
                "rate_limit_per_minute", "rate_limit_burst", "search_min_chars"):
        out.append(f"| `{key}` | {c[key]} |")
    out.append(f"| `quiet_hours` | {c['quiet_hours']['start']}–{c['quiet_hours']['end']} |")
    out.append(f"| `telegram.max_text` | {c['telegram']['max_text']} |")
    out.append(f"| `telegram.link_code_ttl_minutes` | {c['telegram']['link_code_ttl_minutes']} |")
    out.append(f"| `email.from` | {c['email']['from']} |")
    out.append("")
    write(os.path.join(DOCS, "MESSAGING.md"), "\n".join(out) + "\n")

    # ---- JSON summary for the author
    summary = {
        "tools_total": len(tools),
        "tools_by_group": {g: len(v) for g, v in sorted(groups.items())},
        "resources": len(static_res), "templates": len(templates), "prompts": len(prompts),
        "rest_total": len(rest),
        "rest_by_tag": {t: len(v) for t, v in sorted(tags.items())},
        "prompt_names": [p["name"] for p in prompts],
        "resource_uris": [r["uri"] for r in static_res],
        "template_uris": [t["uri"] for t in templates],
        "roles": sorted(auth.ROLE_CATALOG.keys()),
        "role_catalog": sorted(auth.ROLE_CATALOG.keys()),
        "permissions": len(auth.PERMISSIONS),
        "permission_keys": sorted(auth.PERMISSIONS.keys()),
        "settings_groups": sorted(snap.keys()),
        "agent_list": [a.get("key") for a in core.agents.AGENTS],
        "agent_count": len(core.agents.AGENTS),
        "products": [p.get("key") for p in core.agents.PRODUCTS],
    }
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
