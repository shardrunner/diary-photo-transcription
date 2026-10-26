---
summary: Dependency snapshot, compatibility checks and Gemini maintenance constraints.
read_when:
  - Updating dependencies, CI actions or the Gemini model
---

# Software maintenance audit

This snapshot describes the committed dependency resolution and the application's
maintenance constraints. Versions below come from `uv.lock`; supported Python
versions and CI settings come from `pyproject.toml` and `.github/workflows/ci.yml`.
It does not establish live provider compatibility or transcription accuracy.

## Dependency snapshot

| Component | Locked version |
| --- | --- |
| google-genai | 2.31.0 |
| openai | 3.39.0 |
| Claude Code CLI (external, optional) | 2.1.310 |
| Pillow | 13.0.0 |
| Pydantic | 2.14.1 |
| python-dotenv | 1.2.4 |
| pytest | 9.1.1 |
| Ruff | 0.17.1 |
| Pyrefly | 1.4.0 |
| prek | 0.5.5 |
| PyYAML | 6.0.3 |
| detect-secrets | 1.5.0 |

Python 3.12 is the minimum; the CI matrix targets 3.12, 3.14 and 3.15. Ruff's
explicit `py312` target preserves that minimum. CI pins uv to 0.13.1 and pins its
GitHub Actions to commit SHAs. Hatchling remains an unpinned build requirement;
the runtime lockfile alone does not make the build environment reproducible.

## Maintenance constraints

**Image handling.** Upload preparation EXIF-orients and re-encodes JPEG pixels
without source metadata. Keep the orientation and metadata-removal tests when
upgrading Pillow. See the [Pillow release notes](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html).

**SDK behavior.** The adapter consumes `interaction.output_text` and accepts only
completed responses with nonempty output, no reported errors and complete,
nonnegative token counts. It saves the provider response before validation.
Continuation support would require separate handling of partial responses and
costs; it is not enabled. Check [SDK releases](https://github.com/googleapis/python-genai/releases)
when upgrading.

**Retries and timeout.** A synthetic `httpx.MockTransport` regression exercises a
503/503/200 sequence and verifies exactly three HTTP attempts with the pinned SDK.
The request uses a 300-second timeout per attempt. Keep this regression rather
than assuming the SDK's retry-count semantics remain unchanged.

**Request contract.** The transport test checks `store=false`, `stream=false`,
JSON schema, image resolution and thinking level, plus response text and usage
parsing. This verifies local serialization and adapter behavior, not server
acceptance. The CLI accepts `low`, `medium` and `high` thinking and rejects
`minimal`; the configuration dataclass does not validate programmatic construction
at runtime. Recheck [provider thinking options](https://ai.google.dev/gemini-api/docs/thinking)
before changing these choices.

**Cost estimates.** The estimator includes thinking tokens and uses the UTC date
when estimating usage. Its configured Flash Standard rates double on 2027-01-01;
previously stored estimates remain unchanged. Estimates are not billing guarantees,
and failed requests can incur charges without reported usage. Recheck
[provider pricing](https://ai.google.dev/gemini-api/docs/pricing) when updating the
model or rates.

**Run identity.** `config_fingerprint()` excludes the SDK version, so an SDK
upgrade does not resubmit unchanged photos; `run.json` still records the version.
To compare an upgrade, re-run selected photos with `--photos ... --force`; do not
automatically select competing runs.

**Storage semantics.** Requests are synchronous and stateless. Background
execution would require a separate review of provider retention, polling,
resumable local state and failure handling. Do not introduce it as an incidental
SDK upgrade. See [provider background execution](https://ai.google.dev/gemini-api/docs/background-execution).

## Verification and limits

Local checks performed during the publication review:

| Check | Result |
| --- | --- |
| Offline pytest suite | 889 passed |
| Ruff lint and formatting | Pass |
| Default Pyrefly check | Zero errors; three PyYAML-stub warnings |
| Offline demo | Pass |
| sdist and wheel build | Pass |
| Staged-content secret scan | Pass |

Tests block Internet sockets and disable local credentials and configuration.
The secret scan is heuristic; it does not establish that prose or images contain
no personal information. Local checks do not verify GitHub runner integration or
all Python versions in the CI matrix. Run hosted CI before treating that matrix
as verified for a published revision.

No paid API requests were made for this publication review. Live provider
acceptance and transcription quality against independently human-verified gold
remain separate verification tasks. Synthetic fixtures test software contracts,
not handwriting recognition quality.
