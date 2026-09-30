# Git and GitHub Notes

My own cheat sheet. Only commands I have actually used on this project. Repo: `jaxsonbugg/masters-project` (private). Working folder: `C:\dev\masters-project`.

## The daily loop

Run these from `C:\dev\masters-project` (or add `git -C C:\dev\masters-project` in front of each).

| Order | Command | What it does |
|---|---|---|
| 1 | `git status` | Shows which files are new, changed, or staged. Changes nothing. Run it often. |
| 2 | `git diff` | Shows exactly which lines changed in files not yet staged. `+` is added, `-` is removed. |
| 3 | `git add <file>` (or `git add .` for everything) | Selects changes for the next checkpoint. |
| 4 | `git commit -m "short message"` | Saves the checkpoint with a message describing what changed. |
| 5 | `git push` | Sends new commits to GitHub. |

Tip: `git status` after each step shows what moved from "changed" to "staged" to "clean".

## One-time setup I did (2026-09-30)

| Command | What it does |
|---|---|
| `winget install Git.Git` and `winget install GitHub.cli` | Installs Git and the GitHub command-line tool. |
| `git config --global user.name "Jaxson Bugg"` | Sets the name attached to each commit. |
| `git config --global user.email "buggjm@miamioh.edu"` | Sets the email attached to each commit. |
| `git config --global init.defaultBranch main` | New repositories start on a branch called `main`. |
| `gh auth login` | Logs this computer into my GitHub account through the browser. |
| `gh auth status` | Checks who I am logged in as. |
| `gh auth setup-git` | Lets plain `git push` use my GitHub login. Needed once, otherwise push asks for a password. |
| `git init` | Turns the folder into a Git repository. |
| `gh repo create masters-project --private --source=. --remote=origin --push` | Creates the private repository on GitHub, links it, and uploads the first commit. |
| `gh repo view --web` | Opens the repository in the browser. |

## Looking around

| Command | What it does |
|---|---|
| `git log --oneline` | Lists commits, newest first, one line each. |
| `gh repo view` | Shows repository details, including whether it is private. |

## Things I learned

- `.gitignore` lists files Git must never track (model files, secrets, temp files). Set it up before the first `git add`.
- Git ignores empty folders, so I put a blank `.gitkeep` file in the ones I want to keep.
- A commit only lives on my computer until I `git push`.
- Never commit API keys or anything from `C:\masters_project_large\`.
- The "LF will be replaced by CRLF" warning on Windows is harmless.
