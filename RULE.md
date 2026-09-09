# Git Rules

## Branch mapping

- `vule556677` → [`vule556677@gmail.com`](mailto:vule556677@gmail.com)
- `nhatle08052004n` → [`nhatle08052004n@gmail.com`](mailto:nhatle08052004n@gmail.com)
- `lhieu20231` → [`lhieu20231@gmail.com`](mailto:lhieu20231@gmail.com)
- `xeniellq1` → [`xeniellq1@gmail.com`](mailto:xeniellq1@gmail.com)
- `thanhson240624` → [`thanhson240624@gmail.com`](mailto:thanhson240624@gmail.com)

## Worktree mapping

| Branch | Worktree path |
|---|---|
| `vule556677` | `D:\DOANNHATLE\Interview_Coach_SRC_CODE\BE-vule556677` |
| `nhatle08052004n` | `D:\DOANNHATLE\Interview_Coach_SRC_CODE\BE` |
| `lhieu20231` | `D:\DOANNHATLE\Interview_Coach_SRC_CODE\BE-lhieu20231` |
| `xeniellq1` | `D:\DOANNHATLE\Interview_Coach_SRC_CODE\BE-xeniellq1` |
| `thanhson240624` | `D:\DOANNHATLE\Interview_Coach_SRC_CODE\BE-thanhson240624` |

## Shared-code model

- All worktrees above belong to ONE git repo (one project). They share the same git objects and refs, but each has an independent working tree.
- Shared code lives on `main`. Nobody commits to `main` directly — code reaches `main` only via reviewed Pull Requests.
- To receive other developers' merged code, update your own branch from `main` (step 10 below). Never touch another developer's branch or worktree.

## Workflow

1. FIRST, verify you are in the correct worktree and branch:

```bash
git rev-parse --show-toplevel
git branch --show-current
```

The toplevel MUST equal the worktree path of your assigned branch. If not, stop and `cd` there first.

2. Work ONLY in your assigned worktree and branch. NEVER switch to another developer's branch/worktree. NEVER modify or commit directly to `main`.

3. Implement and test your assigned task.

4. Before committing, configure the assigned Git identity:

```bash
git config user.name "<branch-name>"
git config user.email "<assigned-email>"
```

5. Verify:

```bash
git branch --show-current
git config user.email
```

6. Commit your changes:

```bash
git add .
git commit -m "<clear commit message>"
```

7. Push ONLY your assigned branch:

```bash
git push -u origin <branch-name>
```

8. Create a Pull Request to main using GitHub CLI:

```bash
gh pr create --base main --head <branch-name> --title "<title>" --body "<description>"
```

9. After creating the PR, check whether it has merge conflicts:

```bash
gh pr view <pr-number> --json number,title,mergeable,mergeStateStatus
gh pr checks <pr-number>
```

Report the result to the user and ask for a decision. If there are
conflicts, resolve them inside YOUR branch/worktree first (never in `main`).
Merge the PR only after the user explicitly approves.

10. After another PR is merged into main, update your branch before starting new work (run inside YOUR worktree, on YOUR branch):

```bash
git pull origin main
```

## Notes

- `user.email` identifies the commit author; GitHub login credentials determine which account can push.
- NEVER push directly to `main`.
- NEVER work outside your assigned worktree.
