"""Coreference resolution for entity extraction pre-processing.

Replaces pronouns with their resolved referents before NER extraction,
improving entity recall on documents with heavy pronoun usage.

Uses spaCy + coreferee for neural coreference resolution.
Feature-flagged via ``ENABLE_COREFERENCE_RESOLUTION``.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


class CoreferenceResolver:
    """Lazy-loading coreference resolver wrapping spaCy + coreferee.

    The spaCy model and coreferee pipeline component are loaded on first
    call to :meth:`resolve`, not at construction time. This avoids paying
    the ~2s model load cost when the feature is disabled.

    Parameters
    ----------
    model_name:
        spaCy model to load (default ``en_core_web_lg``).
    """

    def __init__(self, model_name: str = "en_core_web_lg") -> None:
        self._model_name = model_name
        self._nlp = None

    def _load(self):
        """Lazy-load spaCy model with coreferee pipeline."""
        if self._nlp is not None:
            return

        import spacy

        self._nlp = spacy.load(self._model_name)

        # Add coreferee to the pipeline
        import coreferee  # noqa: F401 — registers the pipeline component

        self._nlp.add_pipe("coreferee")
        logger.info(
            "coreference.model_loaded",
            model=self._model_name,
            pipes=self._nlp.pipe_names,
        )

    def resolve(self, text: str) -> str:
        """Replace pronouns with their most likely referents.

        Parameters
        ----------
        text:
            Raw document text.

        Returns
        -------
        Text with pronouns replaced by resolved entity names.
        If coreference resolution finds no clusters, returns
        the original text unchanged.
        """
        self._load()
        assert self._nlp is not None

        doc = self._nlp(text)

        if not doc._.coref_chains or len(doc._.coref_chains) == 0:
            return text

        # Build token-level replacements
        replacements: dict[int, str] = {}
        for chain in doc._.coref_chains:
            # Find the most representative mention (first non-pronoun)
            representative = None
            for mention in chain:
                token_indices = mention.token_indexes
                span_text = " ".join(doc[i].text for i in token_indices)
                # Check if the mention is a pronoun
                if not all(doc[i].pos_ == "PRON" for i in token_indices):
                    representative = span_text
                    break

            if representative is None:
                continue

            # Replace pronoun mentions with the representative
            for mention in chain:
                token_indices = mention.token_indexes
                if all(doc[i].pos_ == "PRON" for i in token_indices):
                    # Replace the first token, mark others for deletion
                    replacements[token_indices[0]] = representative
                    for idx in token_indices[1:]:
                        replacements[idx] = ""

        if not replacements:
            return text

        # Rebuild text with replacements
        tokens = []
        for i, token in enumerate(doc):
            if i in replacements:
                if replacements[i]:
                    tokens.append(replacements[i])
                    # Preserve trailing whitespace
                    if token.whitespace_:
                        tokens.append(token.whitespace_)
            else:
                tokens.append(token.text_with_ws)

        resolved = "".join(tokens)
        logger.debug(
            "coreference.resolved",
            original_len=len(text),
            resolved_len=len(resolved),
            replacements=len(replacements),
        )
        return resolved
