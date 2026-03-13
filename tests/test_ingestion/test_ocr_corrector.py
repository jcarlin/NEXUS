"""Tests for T3-14: OCR Error Correction."""

from app.ingestion.ocr_corrector import OCRCorrector


class TestOCRCorrector:
    """Test regex-based OCR corrections."""

    def setup_method(self):
        self.corrector = OCRCorrector()

    def test_ligature_fi(self):
        text = "The ﬁrst document was ﬁled."
        corrected, count = self.corrector.correct(text)
        assert "first" in corrected
        assert "filed" in corrected
        assert count == 2

    def test_ligature_fl(self):
        text = "The ﬂoor was reﬂected."
        corrected, count = self.corrector.correct(text)
        assert "floor" in corrected
        assert "reflected" in corrected

    def test_ligature_ff(self):
        text = "The eﬀect was ﬀective."
        corrected, count = self.corrector.correct(text)
        assert "effect" in corrected
        assert "ffective" in corrected

    def test_digit_letter_confusion_o_to_zero(self):
        # Pattern only matches O between digits (lookbehind + lookahead)
        text = "Case number 2O21"
        corrected, count = self.corrector.correct(text)
        assert "2021" in corrected

    def test_broken_hyphenated_words(self):
        text = "The docu-\nment was signed."
        corrected, count = self.corrector.correct(text)
        assert "document" in corrected

    def test_multiple_spaces(self):
        text = "Too   many    spaces here"
        corrected, count = self.corrector.correct(text)
        assert "Too many spaces here" in corrected

    def test_legal_term_plaintiff(self):
        text = "The Plaintitf filed a motion."
        corrected, count = self.corrector.correct(text)
        assert "Plaintiff" in corrected

    def test_legal_term_attorney(self):
        text = "The Attomey represented the client."
        corrected, count = self.corrector.correct(text)
        assert "Attorney" in corrected

    def test_legal_term_judgment(self):
        text = "The Judgrnent was entered."
        corrected, count = self.corrector.correct(text)
        assert "Judgment" in corrected

    def test_legal_term_exhibit(self):
        text = "See Exhibii A for details."
        corrected, count = self.corrector.correct(text)
        assert "Exhibit" in corrected

    def test_clean_text_unchanged(self):
        text = "This is perfectly clean legal text with no errors."
        corrected, count = self.corrector.correct(text)
        assert corrected == text
        assert count == 0

    def test_empty_text(self):
        corrected, count = self.corrector.correct("")
        assert corrected == ""
        assert count == 0

    def test_multiple_corrections(self):
        text = "The Plaintitf's Attomey ﬁled the Exhibii."
        corrected, count = self.corrector.correct(text)
        assert "Plaintiff" in corrected
        assert "Attorney" in corrected
        assert "filed" in corrected
        assert "Exhibit" in corrected
        assert count >= 4
