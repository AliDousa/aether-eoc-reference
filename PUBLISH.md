# Publishing this repository

Steps to create the public GitHub repository, configure it, and link it from a
profile. Written so they can be re-run or adapted; nothing here is required to
*use* the project.

## 0. Before the first public push

Run the checks that must pass:

```bash
make lint          # ruff + eslint
make typecheck     # pyright + tsc
make test          # 18 API + 14 web, no API key needed
make reset         # rebuild the scenario from fixtures and verify the audit chain
```

Then the sanitisation sweep. This is the one that matters — it is the same set
of patterns the `synthetic-data-check` job runs in CI:

```bash
git grep -nIE --ignore-case \
  -e 'nabidh|dha[-_ ]?prod|production fhir' \
  -e '\b(10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|192\.168\.[0-9]{1,3}\.[0-9]{1,3}|172\.(1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3})\b' \
  -e 'BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|id_rsa' \
  -e '\b(AKIA[0-9A-Z]{16}|sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{30,})\b' \
  -e '(postgres|mysql|mongodb)://[^ "]*@' \
  -- ':!PUBLISH.md' ':!.github/workflows/ci.yml' ':!.gitignore' \
     ':!**/package-lock.json' ':!**/uv.lock' \
     ':!docs/THREAT_MODEL.md' ':!SECURITY.md' \
     ':!docs/adr/0006-synthetic-data-only-public-release.md'

git ls-files | grep -E '(^|/)\.env$' && echo "STOP: .env is tracked"
```

All of these should produce no output.

## 1. Create the repository

Requires the [GitHub CLI](https://cli.github.com/), authenticated
(`gh auth status`).

```bash
cd aether-eoc-reference

gh repo create AliDousa/aether-eoc-reference \
  --public \
  --source . \
  --remote origin \
  --description "Reference slice of a next-gen public-health EOC: live ICS board, resource requests, human-in-the-loop AI agents, and an immutable audit log. Synthetic data only." \
  --push
```

The description is 158 characters, inside GitHub's 160-character limit.

> **If the push is rejected with `refusing to allow an OAuth App to create or
> update workflow .github/workflows/ci.yml without workflow scope`:**
>
> `gh`'s default token carries `repo` but not `workflow`, and GitHub requires
> the latter to push anything under `.github/workflows/`. The repository will
> have been created; only the push failed. Grant the scope once (this opens a
> browser), then push:
>
> ```bash
> gh auth refresh -h github.com -s workflow
> git push -u origin main
> ```

<details>
<summary>Without <code>gh</code></summary>

Create the repository in the web UI as **public** with no README, licence, or
`.gitignore` (this repository has all three), then:

```bash
git remote add origin https://github.com/AliDousa/aether-eoc-reference.git
git branch -M main
git push -u origin main
```
</details>

## 2. Topics

```bash
gh repo edit AliDousa/aether-eoc-reference \
  --add-topic emergency-management \
  --add-topic public-health \
  --add-topic eoc \
  --add-topic ics \
  --add-topic nims \
  --add-topic realtime \
  --add-topic multi-agent \
  --add-topic human-in-the-loop \
  --add-topic typescript \
  --add-topic nextjs \
  --add-topic fastapi \
  --add-topic audit-log
```

## 3. Repository settings

```bash
# Issues on (bug reports are welcome), wiki and projects off.
gh repo edit AliDousa/aether-eoc-reference \
  --enable-issues \
  --enable-wiki=false \
  --enable-projects=false \
  --delete-branch-on-merge

# Private vulnerability reporting, so SECURITY.md points somewhere real.
gh api -X PUT repos/AliDousa/aether-eoc-reference/private-vulnerability-reporting
```

## 4. Pin it to the profile

Pinning is not exposed by `gh repo edit`; do it in the UI:

**github.com/AliDousa** → **Customize your pins** → tick
`aether-eoc-reference` and `phim`.

## 5. Confirm CI is green

```bash
gh run list --repo AliDousa/aether-eoc-reference --limit 5
gh run watch --repo AliDousa/aether-eoc-reference
```

Three jobs should pass with no secrets configured: **API**, **Web**, and
**Synthetic data sweep**. If the API or Web job needs a credential, something
has gone wrong — the whole demo is meant to run without one.

## 6. Profile README snippet

Add to `AliDousa/AliDousa/README.md`:

```markdown
### Public work
- **[aether-eoc-reference](https://github.com/AliDousa/aether-eoc-reference)** — reference slice of a next-gen public-health EOC: live board, resource contention, HITL agents, immutable audit log.
- **[phim](https://github.com/AliDousa/phim)** — epidemiological modeling and forecasting workbench (SEIR, agent-based, ML).

I build operational systems for public-health emergencies: situational awareness, resource coordination, and audited decision support. Production platforms stay private. These repos are the parts that are safe to inspect.
```

## 7. First commit message

If squashing local history before the first public push:

```
feat: public reference slice of an AI-orchestrated EOC

Live ICS board, resource requests with human-in-the-loop
recommendations, and an append-only audit log. Synthetic
heat-surge scenario only. No production data or integrations.
```

## Afterwards

- Do **not** open a PR against `phim`. It is a sibling repository, not a
  dependency.
- The README's "How this relates to `phim`" section is the only link between
  them, and it is one-directional by design.
- If you later add screenshots, see `docs/images/README.md` for what to capture
  and why none are committed.
