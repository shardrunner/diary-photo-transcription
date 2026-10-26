"""Evaluation einer Extraktion gegen den Gold-Standard (`eval`)."""

from __future__ import annotations

import argparse

from diary_photo_transcription.evaluate import evaluate_observation
from diary_photo_transcription.runs import active_dir
from diary_photo_transcription.schemas import PhotoObservation


def run_eval(args: argparse.Namespace) -> int:
    """Evaluate one predicted extraction against its gold standard."""
    gold_path = args.gold.resolve(strict=True)
    pred_path = args.pred.resolve(strict=True)
    if pred_path.is_dir():
        pred_path = active_dir(pred_path) / "raw.json"
    gold_obs = PhotoObservation.model_validate_json(gold_path.read_text(encoding="utf-8"))
    pred_obs = PhotoObservation.model_validate_json(pred_path.read_text(encoding="utf-8"))
    report = evaluate_observation(gold_obs, pred_obs)

    print("=== Extraktions-Evaluation ===")
    print(f"Exakter Treffer: {report.is_exact_match}")
    print(f"Datum korrekt: {report.date_match}")
    print(
        f"Fließtext CER: {report.text_report.cer:.4f} "
        f"(Gold-Absätze: {report.text_report.paragraph_count_gold}, "
        f"Modell: {report.text_report.paragraph_count_pred})"
    )
    print(f"Score Positions-Genauigkeit: {report.score_report.position_accuracy:.2%}")
    print(f"Score Status-Genauigkeit: {report.score_report.state_accuracy:.2%}")
    print(f"Score Werte-Genauigkeit: {report.score_report.value_accuracy:.2%}")
    print(
        f"Formularfelder Präsenz P/R: {report.field_report.present_precision:.2%} / "
        f"{report.field_report.present_recall:.2%}"
    )
    print(f"Formular Item CER: {report.field_report.item_cer:.4f}")
    for note in report.notes:
        print(f"Note: {note}")

    if report.score_report.mismatches:
        print("\nScore-Abweichungen:")
        for m in report.score_report.mismatches:
            print(
                f"  Pos {m.position}: Gold={m.gold_state}:{m.gold_raw} vs "
                f"Pred={m.pred_state}:{m.pred_raw}"
            )
    if report.field_report.mismatches:
        print("\nFeld-Abweichungen:")
        for fm in report.field_report.mismatches:
            print(f"  {fm}")
    if report.text_report.missing_passages:
        print("\nAusgelassene Textpassagen:")
        for p in report.text_report.missing_passages:
            print(f"  - {p}")
    if report.text_report.inserted_passages:
        print("\nEingefügte oder abweichende Textpassagen (nicht verifiziert):")
        for hp in report.text_report.inserted_passages:
            print(f"  - {hp}")
    return 0
