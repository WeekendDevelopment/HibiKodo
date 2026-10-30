# Question schema

One YAML file per skill under `content/<cert>/`, containing a list of questions. `pipeline/validate.py` enforces everything below.

```yaml
- id: az-104.identities-governance.resource-access.0001
  cert: az-104
  domain: identities-governance      # id from outline.yaml
  skill: resource-access             # id from outline.yaml, must belong to domain
  type: multiple_choice              # multiple_choice | multi_select | scenario
  stem: "..."                        # original wording
  options:
    - {id: a, text: "..."}
    - {id: b, text: "..."}
  answer: [b]                        # list of option ids; exactly 1 for multiple_choice/scenario, 2+ for multi_select
  explanation: "..."                 # why the answer is right, and why distractors are not
  source_url: https://learn.microsoft.com/...
  quote: "..."                       # verbatim text from the page at source_url
  retrieved_at: 2026-10-29
  difficulty: 2                      # 1 (easy) to 3 (hard)
  tags: [rbac, scopes]
  status: draft                      # draft | approved | flagged
  last_reviewed: null                # date, required when status is approved
```

## Rules

- `id` is `<cert>.<domain>.<skill>.<4-digit number>` and unique across all files.
- `domain` and `skill` must exist in `content/<cert>/outline.yaml`, and the skill must sit under that domain.
- `options` has 3 to 6 entries with unique ids; every `answer` entry must be an option id.
- `source_url` must be an https URL on `learn.microsoft.com` (the allowed-source list; extend it deliberately).
- `quote` is required and non-empty. The pipeline separately checks it appears verbatim in the stored page text.
- `status: approved` requires `last_reviewed`.
- `stem` values must be unique within a cert (the validator checks exact matches; `generate.py` also rejects stems more than 70% similar to an existing one).
