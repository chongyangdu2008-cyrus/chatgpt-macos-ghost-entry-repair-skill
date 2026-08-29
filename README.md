# ChatGPT macOS Ghost Entry Repair Skill

A narrowly scoped Codex skill for a macOS ChatGPT Desktop reconciliation defect: a cloud conversation was deleted on another device, disappeared from the authoritative cloud list, but remains as an undeletable ghost entry in **Recents**.

The skill diagnoses the local catalog read-only first. A repair is allowed only when exactly one remote ChatGPT row matches, no local timeline exists, the database is healthy, the user explicitly authorizes the mutation, and a SQLite-consistent backup succeeds. It then removes only that composite-key row, increments the catalog revision, and verifies the result.

## Safety boundaries

- Does not clear cookies, authentication, all app data, or `~/.codex`.
- Does not operate on local Codex tasks or normal cloud conversations.
- Stops on zero or multiple matches, schema drift, local timeline records, locking, or integrity errors.
- Treats the internal database schema as version-dependent diagnostic evidence, not a supported general-purpose API.

## Installation

Copy this repository into the personal Codex skills directory so that `SKILL.md` is located at:

```text
~/.codex/skills/chatgpt-macos-ghost-entry-repair/SKILL.md
```

Codex can then select the skill automatically for the described symptom, or it can be invoked explicitly as `$chatgpt-macos-ghost-entry-repair`.

## Privacy

Do not publish diagnostic output from a real machine. Conversation titles, account and user identifiers, host identifiers, conversation or thread identifiers, tokens, cookies, absolute user paths, database copies, screenshots, and logs must remain local.

---

## 简体中文

这是一个范围严格限定的 Codex Skill，用于处理 macOS ChatGPT Desktop 的本地目录同步异常：某个云端对话已经在手机或其他客户端删除，也不再出现在权威云端对话列表中，但仍作为无法正常删除的幽灵条目残留在桌面端的**最近项目**中。

该 Skill 会先以只读方式检查本地目录。只有在以下条件全部满足时才允许修复：恰好匹配一个远程 ChatGPT 条目、不存在对应的本地时间线记录、数据库完整、用户明确授权修改，并且 SQLite 一致性备份成功。随后，它只删除经过确认的复合主键记录，递增目录修订号，并验证修复结果。

### 安全边界

- 不清除 Cookie、登录状态、全部应用数据或 `~/.codex`。
- 不处理本地 Codex 任务或仍然正常存在的云端对话。
- 如果匹配数量为零或多个、数据库结构发生变化、存在本地时间线、数据库被锁定或完整性检查失败，会立即停止。
- ChatGPT 内部数据库结构可能随版本变化；本工具只用于有备份和严格条件检查的诊断性修复，不是通用官方 API。

### 安装

将本仓库复制到个人 Codex Skills 目录，并确保 `SKILL.md` 位于：

```text
~/.codex/skills/chatgpt-macos-ghost-entry-repair/SKILL.md
```

之后 Codex 可以在出现上述症状时自动选择该 Skill，也可以使用 `$chatgpt-macos-ghost-entry-repair` 显式调用。

### 隐私

请勿公开真实设备上的诊断输出。对话标题、账户及用户标识符、主机标识符、conversation/thread ID、token、Cookie、用户绝对路径、数据库副本、截图和日志都必须保留在本地。
