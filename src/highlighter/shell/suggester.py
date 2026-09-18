from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, Sequence

from ..library import PlayerHint
from .context import LineContext
from .document import Document
from .grammar import (
    DEMO_PLACEHOLDER,
    FLAG_PLACEHOLDER,
    Candidate,
    CandidateKind,
    Grammar,
    Option,
    ValueKind,
)

EMPTY_LINE_HINT = "a demo name, a flag, or help"
READY_HINT = "add a flag, or press Enter to record"
ANY_FLAG_PREFIX = "-"
UNKNOWN_FLAG_HINT = "no flag starts like that"
HISTORY_HINT = "from history"
TAB_HINT = "tab for"
MATCH_PREVIEW_LIMIT = 4


class HistorySource(Protocol):
    def suggest(self, prefix: str) -> str: ...


@dataclass(frozen=True, slots=True)
class Suggestion:
    completion: str = ""
    placeholder: str = ""
    hint: str = ""
    candidates: tuple[Candidate, ...] = ()

    @property
    def ghost(self) -> str:
        return self.completion or self.placeholder

    @property
    def has_completion(self) -> bool:
        return bool(self.completion)


class Suggester:
    def __init__(
        self,
        grammar: Grammar | None = None,
        demos: Callable[[], Sequence[str]] | None = None,
        history: HistorySource | None = None,
        players: Callable[[str], Sequence[PlayerHint]] | None = None,
    ) -> None:
        self._grammar = grammar or Grammar()
        self._demos = demos or (lambda: ())
        self._history = history
        self._players = players or (lambda demo_name: ())

    def suggest(self, document: Document) -> Suggestion:
        suggestion = self._from_grammar(LineContext.of(document))
        if suggestion.has_completion or not document.at_end:
            return suggestion
        return self._with_history(document, suggestion)

    def candidates(self, document: Document) -> tuple[Candidate, ...]:
        return self._from_grammar(LineContext.of(document)).candidates

    def _from_grammar(self, context: LineContext) -> Suggestion:
        pending = self._pending_value(context)
        if pending is not None:
            return self._value_suggestion(pending, context)
        if context.word_is_flag:
            return self._flag_suggestion(context)
        return self._word_suggestion(context)

    def _pending_value(self, context: LineContext) -> Option | None:
        option = self._grammar.option_for(context.preceding)
        if option is None or not option.takes_value:
            return None
        return option

    def _value_suggestion(self, option: Option, context: LineContext) -> Suggestion:
        candidates = self._value_candidates(option, context)
        if not context.word:
            return Suggestion(
                placeholder=option.placeholder,
                hint=self._hint(candidates) or option.summary,
                candidates=candidates,
            )
        if candidates:
            return self._built(candidates, context.word)
        return Suggestion(hint=option.summary)

    def _value_candidates(
        self, option: Option, context: LineContext
    ) -> tuple[Candidate, ...]:
        if option.value is ValueKind.PLAYER:
            return self._player_candidates(context)
        return self._grammar.value_candidates(option, context.word)

    def _player_candidates(self, context: LineContext) -> tuple[Candidate, ...]:
        return tuple(
            Candidate(text=hint.name, summary=hint.note, kind=CandidateKind.PLAYER)
            for hint in self._players(self._named_demo(context))
            if hint.starts_with(context.word)
        )

    def _flag_suggestion(self, context: LineContext) -> Suggestion:
        candidates = self._grammar.flag_candidates(context.word, context.other_flags())
        option = self._grammar.option_for(context.word)
        if option is not None and option.takes_value and len(candidates) <= 1:
            return Suggestion(placeholder=f" {option.placeholder}", hint=option.summary)
        if not candidates:
            return Suggestion(hint=UNKNOWN_FLAG_HINT)
        return self._built(candidates, context.word)

    def _word_suggestion(self, context: LineContext) -> Suggestion:
        if not context.word:
            return self._waiting_suggestion(context)
        candidates = self._opening_candidates(context)
        if candidates:
            return self._built(candidates, context.word)
        return Suggestion()

    def _waiting_suggestion(self, context: LineContext) -> Suggestion:
        if self._demo_already_given(context):
            return Suggestion(
                placeholder=FLAG_PLACEHOLDER,
                hint=READY_HINT,
                candidates=self._grammar.flag_candidates(
                    ANY_FLAG_PREFIX, context.other_flags()
                ),
            )
        return Suggestion(
            placeholder=DEMO_PLACEHOLDER,
            hint=EMPTY_LINE_HINT,
            candidates=self._opening_candidates(context),
        )

    def _opening_candidates(self, context: LineContext) -> tuple[Candidate, ...]:
        commands = (
            self._grammar.command_candidates(context.word) if context.is_first_word else ()
        )
        if self._demo_already_given(context):
            return commands
        return (*commands, *self._demo_candidates(context.word))

    def _demo_candidates(self, prefix: str) -> tuple[Candidate, ...]:
        lowered = prefix.lower()
        return tuple(
            Candidate(text=name, summary="demo file", kind=CandidateKind.DEMO)
            for name in self._demos()
            if name.lower().startswith(lowered)
        )

    def _demo_already_given(self, context: LineContext) -> bool:
        return bool(self._positionals(context))

    def _named_demo(self, context: LineContext) -> str:
        found = self._positionals(context)
        return found[0] if found else ""

    def _positionals(self, context: LineContext) -> list[str]:
        found: list[str] = []
        skip_next = False
        for position, token in enumerate(context.tokens):
            if token.start == context.word_start:
                continue
            if skip_next:
                skip_next = False
                continue
            if token.is_flag:
                option = self._grammar.option_for(token.text)
                skip_next = option is not None and option.takes_value
                continue
            if position == 0 and self._grammar.command_for(token.text) is not None:
                continue
            found.append(token.text)
        return found

    def _with_history(self, document: Document, suggestion: Suggestion) -> Suggestion:
        if self._history is None or not document.text:
            return suggestion
        remainder = self._history.suggest(document.text)
        if not remainder:
            return suggestion
        return Suggestion(
            completion=remainder,
            hint=suggestion.hint or HISTORY_HINT,
            candidates=suggestion.candidates,
        )

    @classmethod
    def _built(cls, candidates: tuple[Candidate, ...], word: str) -> Suggestion:
        chosen = candidates[0]
        completion = chosen.text[len(word) :] if chosen.text.startswith(word) else ""
        return Suggestion(
            completion=completion,
            hint=cls._hint(candidates, word, completion),
            candidates=candidates,
        )

    @classmethod
    def _hint(
        cls, candidates: tuple[Candidate, ...], word: str = "", completion: str = ""
    ) -> str:
        if not candidates:
            return ""
        if len(candidates) == 1:
            return cls._single_hint(candidates[0], word, completion)
        preview = ", ".join(item.text for item in candidates[:MATCH_PREVIEW_LIMIT])
        if len(candidates) > MATCH_PREVIEW_LIMIT:
            preview += ", ..."
        return f"{len(candidates)} matches: {preview}"

    @staticmethod
    def _single_hint(chosen: Candidate, word: str, completion: str) -> str:
        if completion or chosen.text.lower() == word.lower():
            return chosen.summary
        offered = f"{TAB_HINT} {chosen.text}"
        return f"{offered}, {chosen.summary}" if chosen.summary else offered
