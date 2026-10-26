# Extraction experiments

Private corpus notes and diary-derived observations have been moved to ignored
`private/public-readiness-backup/docs/ai/extraktionsoptimierung.md` locally.
They are not a public benchmark. Historical summaries overstated correctness:
schema validity does not establish transcription accuracy, and the reported
second text CER was 0.0231, not below 0.02.

## Evaluation protocol

Use independently human-verified gold, compare every entry, and report omissions,
dates, completion and strike-through states as well as text error. Raw model
observations are predictions, not gold. Multiple runs detect instability, not
truth; shared systematic errors defeat majority voting.

Resolution and thinking-budget comparisons need a documented dataset, paired
settings and repeated measurements. No public handwriting-quality result is
claimed here. Synthetic fixtures test software contracts only.
