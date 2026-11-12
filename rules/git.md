---
area: GIT
title: Git
skill: git
description: >-
  Use when writing a commit message, naming a branch, opening or describing a pull request, or deciding whether a
  file may be committed.
---

### GIT-1 MUST

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

- a standard type: `feat fix docs refactor test build ci perf style chore revert`;
- an optional scope;
- a lowercase imperative subject, with no period, of at most 72 characters;
- no articles (`a`, `an`, `the`) and no filler: say what changed in as few words as hold it.

Example: `fix(proxy): retry on 429 from upstream`, not `fix(proxy): add a retry for the 429 errors`.

*Why:* the default tooling accepts exactly these types, and the imperative matches git's own convention
([Beams](https://cbea.ms/git-commit/)).

*Check:* the `conventional-pre-commit` and `check-commit-msg` commit-msg hooks, for the type, the lowercase start, the
period, the length and the articles; review for the imperative and for filler.

### GIT-2 MUST

A commit message is one line: no body and no trailers. A reason worth keeping goes where readers look for it: a code
comment for a constraint, the PR description for an alternative that was rejected. Claude Code's own trailer is off in
`.claude/settings.json` (`attribution`).

*Check:* `check-commit-msg`.

### GIT-3 MUST

Branches are short-lived and named `<type>/<slug>` (`feat/`, `fix/`, `docs/`, `refactor/`, plus `exp/` for
experiments). Merges are squash-merges, and the PR title is the conventional commit that lands on `main`. `make github`
sets the repo up once: squash-merge only, the PR title as the commit title with an empty body (GIT-2), merged branches
deleted. GitHub appends ` (#N)` to the title, so PR titles stay within 65 characters.

*Check:* `make github`; review.

### GIT-5 MUST

Secrets, data, run outputs and notebook outputs are never committed.

*Check:* gitleaks, nbstripout, `.gitignore`.

### GIT-6 MUST

A PR description follows `.github/pull_request_template.md`: a summary of why, the changes made with the alternatives
rejected, and the checklist; results, how to reproduce them and notes for the reviewer when they apply.

*Why:* commits are one line, so the PR holds the reasoning, and the squash commit links to it by number.

*Check:* template; review.
