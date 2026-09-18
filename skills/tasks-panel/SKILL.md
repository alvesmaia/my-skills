---
name: tasks-panel
description: Use when executing a multi-task implementation plan and the user has no visibility into progress. Also use when the user asks to open the task board, open the progress panel, or see where the plan stands.
---

# Plan progress in TASKS.md

While you execute a multi-task plan, the user has no visibility: what closed,
what is running, what is blocked, and what is waiting on a decision of theirs.
Asking them every so often costs their day; a report at the end arrives too late
for them to redirect anything.

This skill solves that with two artifacts: a file **you** maintain, and a panel
**they** leave open.

## What to do

**When you start executing the plan**, create `TASKS.md` at the repository root
in the format below, then open the panel:

```
uv run <this-skill-dir>/scripts/tasks-panel.py
```

On Windows with Windows Terminal available, open it in a split pane instead so
it doesn't take over the current one:

```
wt -w 0 split-pane -V -s 0.3 uv.exe run <this-skill-dir>/scripts/tasks-panel.py
```

Tell the user in one line that the panel is open and that phases expand on
click. Do not ask permission to open it — opening it is the point of the skill.

**Every time a task closes**, update `TASKS.md` in the **same commit** that
closes it. A board that drifted from the code is worse than no board: the user
starts deciding on wrong information.

**Never edit `TASKS.md` while a subagent is working in the repository.** Its
`git add` will sweep your file into its commit. Update before dispatching or
after it reports back.

## The format

The panel parses this. Keep it, or it stops rendering.

```markdown
# Project name

`✅ done` · `▶️ running` · `⬜ todo` · `⛔ blocked` · `❓ needs your call`

**20 of 25 tasks · 235 tests · 60 commits**

## Phase A — name of the phase

- ✅ 1 · Short task title
- ✅ 2 · Another title
- ▶️ 3 · Task in progress — *under review*
- ⬜ 4 · Task not started

## ❓ Needs your call

- One pending decision per line
- No icon needed: the icon is in the section title

## ⛔ Blocked

- What is stuck, and why

## ⬜ Debts

- What was deliberately deferred
```

Rules the panel depends on:

- A phase is `## `; a task is `- <icon> <number> · <title>`.
- The leading number is what links a task to its detail (see below).
- A section whose **title starts with a status icon** is an action section: it
  never starts collapsed and its items may omit the icon. This is structural,
  not name-based, so it works in any language.
- One line per task. **No descriptive paragraphs on the board** — that mistake
  is what produced this skill: the board became a technical record and stopped
  working as a board, unreadable in a narrow side panel.

## Task detail

The long text — what the task delivered, and why the non-obvious decisions were
made — goes into `docs/task-details.md` (or `docs/historico-implementacao.md`,
both are recognized), in this shape:

```markdown
✅ **Task 13 — Local registry of installed mini-apps**
Local SQLite holding what is installed and at which version. Reinstalling the
same id updates the row instead of duplicating it. 18 tests.
```

The panel joins the two by task number, and the task then expands to show that
text. A task with no detail stays a plain line — the triangle appears only where
there is something to read.

That split is the point: the board answers "where are we" at a glance, the
detail file answers "why was it done this way" when someone needs it.

## How the panel behaves

It reloads itself when the file changes, keeping whatever the reader had
expanded — updating the board never collapses anything in their face. Mouse:
click a title. Keyboard: `↑↓` moves, `→` opens or steps in, `←` closes or steps
out, `Enter` toggles, `a` expands all, `c` collapses all, `q` quits.

Whatever is `▶️` shimmers — a bright band sweeps across the task's text and,
if the phase itself is in progress, across the phase title too. It's the only
part of the board that changes on its own; everything else only updates when
the file does.

At rest it only compares the file's modification time.

## Themes

`uv run <this-skill-dir>/scripts/tasks-panel.py --theme NAME [path]`

- `alvesmaia` (default) — the alvesmaia brand palette (indigo accent, neutro
  text), terminal's own background.
- `dourado` — the same idea in amber/gold instead of indigo.
- `monokai` — the classic Monokai editor palette, its own dark background.
- `vscode-dark` — VS Code's Dark+ defaults, its own dark background.

## Requirements

`uv` (https://docs.astral.sh/uv/). It resolves Python and Textual from the
script's own PEP 723 header into an isolated cache — nothing is installed
system-wide. The first run takes a few seconds building that cache; later runs
are immediate.

The panel finds the board in the current directory or any parent, or takes a
path as its argument.
