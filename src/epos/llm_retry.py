"""LLM retry message helpers."""

from __future__ import annotations

from typing import Any


def _semantic_retry_messages(
    messages: list[dict[str, str]], report: dict[str, Any]
) -> list[dict[str, str]]:
    problems = [str(problem) for problem in report.get("problems", [])]
    text = " ".join(problems).casefold()
    note = (
        "\n\nCORREZIONE OBBLIGATORIA PER IL RETRY:\n"
        "- Mantieni narrative_policy, consenso, outfit e stato relazionale "
        "dello snapshot; non cambiare tono casualmente fra tentativi.\n"
        "- Non parlare per il player e non inventare dialogue speaker=player.\n"
        "- Non inventare una nuova azione, strategia, intenzione o obiettivo "
        "del player.\n"
        "- Non trasformare risveglio, osservazione, ascolto, attesa o immobilita "
        "in prova sociale, seduzione, attacco, esplorazione o inganno.\n"
        "- Mantieni il momento visuale esatto richiesto dal player e le sue "
        "conseguenze immediate.\n"
        "- Nudita da sola non equivale a sensualita, intimacy_detected o consenso.\n"
        "Errori validazione precedenti:\n- "
        + "\n- ".join(problems)
    )
    if any(alias in text for alias in ("ulisse", "odysseus", "odisseo")):
        note += (
            '\n- Nei campi strutturali che rappresentano entity ID usa sempre "player" '
            "per il protagonista.\n"
            '- Non usare "ulisse", "odysseus" o "odisseo" come ID interno.\n'
            '- Lascia "Ulisse" solo nella prosa narrativa, nei testi liberi e nei '
            "dialoghi naturali."
        )
    retry_messages = list(messages)
    if retry_messages and retry_messages[-1].get("role") == "user":
        retry_messages[-1] = {
            **retry_messages[-1],
            "content": retry_messages[-1].get("content", "") + note,
        }
    else:
        retry_messages.append({"role": "user", "content": note})
    return retry_messages
