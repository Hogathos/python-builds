# python-builds

A monorepo of small Python builds. One folder = one project. No project
imports from another project yet — if shared code actually emerges later,
it goes in a shared folder, not copied across projects.

## Builds

- [movie-ticket-calculator](movie-ticket-calculator/) — movie night budget calculator (booleans, conditionals, f-strings)
- [grade-calculator](grade-calculator/) — letter grades from numeric scores (elif chains, f-strings)
- [division_calculator](division_calculator/) — HOI4 division stats calculator (infantry + support or line artillery, verified against the in-game designer)
- [agent-observability-proxy](agent-observability-proxy/) — Essential Complexity Manager: a local proxy in the middle of agent traffic, so the log is real traffic. Trace ID across agents, retry waste and cost per successful task as the headline, local / cheap / terminal-agent-first, metadata only. M1 is local HTTP logging, visualizer v1 outputs `trace-diagram.md` with a GitHub-rendered Mermaid flowchart. See that folder's README for milestones M1–M4 and Layer 2 evals.

## Monorepo guideline

- Folder per project, with its own README, tests, and run command.
- Workflows in `.github/workflows/` are scoped per project, with a `paths:` filter, so CI only runs for the project that changed.
- Commit messages start with a project prefix, e.g. `proxy: add visualizer v1`, `divcalc: fix ...`. Then `git log -- agent-observability-proxy` gives perfect history for just that project.
- No heavy monorepo tooling (Nx, Bazel, Pants, etc.) until slow CI or shared builds actually force it. Monorepo + monolith first, extract only when failure characteristics truly require it.
- Never commit real traffic logs, secrets, API keys, or prompt bodies. `attempts.db` is local only and ignored. Demo traces only in the public repo.

## How to test one project

```sh
cd agent-observability-proxy
PYTHONPATH=. python -m unittest discover -s tests -v
```

Replace the folder name for other projects; each project documents its own test command in its README.
