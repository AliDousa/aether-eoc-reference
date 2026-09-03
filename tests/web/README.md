# Web tests live in `apps/web/tests/`

Not here. This directory is a signpost.

`apps/web` is the npm package root, so that is where `node_modules` lives. A test
file under `<repo>/tests/web` cannot resolve `react` or `@testing-library/react`,
because Node resolution walks up from the importing file and finds no
`node_modules` above `tests/`.

The alternative was to convert the repository to npm workspaces so dependencies
hoist to the root. That works, but it changes the install command, moves the
lockfile, and complicates both Docker build contexts — a poor trade for a
reference slice that should be clonable and readable quickly.

Python has no equivalent constraint, so the API tests remain at
[`tests/api/`](../api).

```bash
cd apps/web && npm run test -- --run
```
