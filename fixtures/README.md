# SYNTHETIC FIXTURE — not operational data

Everything in this directory is invented for a software demonstration.

- No real people. Operator names are role-shaped labels (`IC-Demo`,
  `LOGISTICS-1`, `Operator North`).
- No real places. Site names are generic sectors, and the coordinates are a
  regularly-spaced artificial grid — they are placeholders for a map that this
  slice does not ship, not real locations.
- No real stock, no real casualty figures, no patient or victim records, and no
  connection to any agency system.

JSON has no comment syntax, so the `# SYNTHETIC FIXTURE` banner required by the
repository's sanitisation rules appears as a `_notice` key at the top of every
`.json` file in this directory instead. This file carries the banner in the
literal form.

## Files

| File | Contents |
|------|----------|
| `operators.json` | Demo logins and their ICS roles |
| `incident.json` | The single seeded incident and its objectives |
| `sites.json` | Four resource sites with equity priorities |
| `skus.json` | Twelve fictional resource types |
| `inventory.json` | Opening stock, including the ORS contention |
| `timeline.json` | The six-hour scripted history the seeder replays |

## How the seeder uses these

`apps/api/app/seed.py` does not insert history rows directly. It replays
`timeline.json` through the same service functions the running application
uses — `requests.create`, `supervisor.run_intent`, `decisions.approve`,
`decisions.reject`. The seeded audit log is therefore produced by the real code
path and its hash chain verifies like any other.
