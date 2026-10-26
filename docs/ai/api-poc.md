# API integration notes

Historical private corpus experiments are preserved only in the ignored local
`private/public-readiness-backup/docs/ai/api-poc.md`. They are exploratory evidence,
not a reproducible public benchmark or a correctness guarantee.

## Current request contract

The Google Gen AI SDK Interactions adapter sends inline JPEG and structured-output
schema, `store=false`, `stream=false`, explicit image resolution and optional
thinking level. The timeout is 300 seconds per HTTP attempt (120 s was too short for dense pages). Retries are left to
the SDK (`HttpRetryOptions(attempts=2)`: at most three attempts for 408/409/429/5xx
with capped backoff); recheck this mapping when upgrading the pinned SDK.

The full provider response is saved before it is accepted. Only `completed`
responses with nonempty output, no reported errors and complete nonnegative token
usage are accepted; schema validation follows. Neither establishes source fidelity.
Transport errors can incur charges without reported usage; logged costs are
estimates of reported usage only.

## Experimental lessons

- Repeated agreement can reflect a shared systematic error; do not majority-vote
  transcriptions into canonical notes.
- Positional score schemas must express missing/struck-through values or a model
  can shift every later value into the wrong slot.
- Model self-critique can suggest schema improvements but is not image evidence.
- Reduced uncertainty flags do not prove better transcription.
- Resolution/thinking comparisons require independently verified gold and repeated,
  paired trials before quality or cost conclusions can generalize.

See the [README](../../README.md) for the workflow and the cloud privacy boundary.
