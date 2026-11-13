# python-builds

A monorepo of small Python builds. One folder = one project. No project
imports from another project yet — if shared code actually emerges later,
it goes in a shared folder, not copied across projects.

## Builds

- [movie-ticket-calculator](movie-ticket-calculator/) — movie night budget calculator (booleans, conditionals, f-strings)
- [grade-calculator](grade-calculator/) — letter grades from numeric scores (elif chains, f-strings)
- [division_calculator](division_calculator/) — HOI4 division stats calculator (infantry + support or line artillery, verified against the in-game designer)
- [agent-observability-proxy](agent-observability-proxy/) — local proxy watching agent traffic, metadata only (M1–M4, visualizer v2, Layer 2 evals)

## Monorepo guideline

- Folder per project, with its own README, tests, and run command.
- The workflow in `.github/workflows/` lints and runs the proxy test suite on push and pull requests to `main`.
- Commit messages start with a project prefix, e.g. `proxy: add visualizer v1`, `divcalc: fix ...`. Then `git log -- agent-observability-proxy` gives perfect history for just that project.
- No heavy monorepo tooling (Nx, Bazel, Pants, etc.) until slow CI or shared builds actually force it. Monorepo + monolith first, extract only when failure characteristics truly require it.
- Never commit real traffic logs, secrets, API keys, or prompt bodies. `attempts.db` is local only and ignored. Demo traces only in the public repo.

## How to test one project

```powershell
cd agent-observability-proxy
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Replace the folder name for other projects; each project documents its own test command in its README.
