# my-skills

Personal collection of [Claude Code](https://claude.com/claude-code) skills,
kept in one place so they can be versioned, reused across machines, and shared.

## What's a skill here

A skill is a self-contained directory under `skills/` with a `SKILL.md`
(frontmatter `name` + `description`, telling an agent *when* to use it) and
any scripts or reference files it needs. This is the same shape Claude Code
expects in `~/.claude/skills/`, so installing one is just copying or linking
its folder there.

## Skills

| Skill | What it's for |
|---|---|
| [`claude-tasks`](skills/claude-tasks/) | A clickable progress panel for a multi-task plan tracked in `TASKS.md`, so the user can see status without asking. |

## Installing a skill

Copy (or symlink) the skill's directory into your skills folder:

```bash
cp -r skills/claude-tasks ~/.claude/skills/claude-tasks
# or, to keep it in sync with this repo:
ln -s "$(pwd)/skills/claude-tasks" ~/.claude/skills/claude-tasks
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the conventions each skill in this
repo follows.

## License

MIT — see [LICENSE](LICENSE).
