"""Reviewed local vocabulary; suggestions never modify recognition hints themselves."""

import re
import unicodedata
from collections import Counter
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from localphraser.history import History

STOP_WORDS = set(
    "a about actually after again all also am an and another any app are as at be because "
    "been before but by can could did do does doing don't each first for from get good got "
    "had has have hello here hi how i if in is it it's just know like looks make maybe more "
    "most my need new no not now of okay on one only or other our out please really right "
    "said say see should so some something still test testing than thank thanks that the "
    "their them then there these they thing think this those time to today too try two um "
    "uh up us use used using very want was way we well were what when where which who why "
    "will with work works would yeah yes you your".split()
)
TERM = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:[._+-][A-Za-z0-9]+)*\b")
PRIVATE_PATTERNS = re.compile(r"https?://\S+|\b[\w.+-]+@[\w.-]+\.\w+\b")


def normalize_term(value: str) -> str:
    if any(unicodedata.category(char) in ("Cc", "Cf") for char in value) or "," in value:
        raise ValueError("Use one word or phrase without commas or control characters.")
    value = " ".join(value.split())
    if not 1 <= len(value) <= 64 or not any(char.isalnum() for char in value):
        raise ValueError("Enter a name or phrase of 1–64 characters.")
    return value


def terms(value: str) -> list[str]:
    return list(
        {
            part.strip().casefold(): part.strip() for part in value.split(",") if part.strip()
        }.values()
    )


def suggestions(samples: list[str], feedback: list[dict], approved: str) -> list[dict]:
    """Bounded recurring-name/technical-term hints, not LLM training or spelling truth."""
    excluded = {word.casefold() for word in terms(approved)}
    excluded.update(row["term"].casefold() for row in feedback if row["source"] == "dismissed")
    counts: Counter[str] = Counter()
    spellings: dict[str, str] = {}
    for sample in samples:
        found = {}
        for word in TERM.findall(PRIVATE_PATTERNS.sub(" ", sample)):
            key = word.casefold()
            distinctive = word != word.lower() or any(
                char.isdigit() or char in "._+" for char in word
            )
            if 3 <= len(word) <= 48 and key not in STOP_WORDS and distinctive:
                found[key] = word
        counts.update(found.keys())
        for key, word in found.items():
            spellings.setdefault(key, word)
    rows: dict[str, dict[str, Any]] = {
        key: {"term": spellings[key], "source": "repeated", "count": count}
        for key, count in counts.items()
        if count >= 2 and key not in excluded
    }
    for row in feedback:
        key = row["term"].casefold()
        if row["source"] == "correction" and key not in excluded:
            rows[key] = {"term": row["term"], "source": "correction", "count": 0}
    return sorted(
        rows.values(),
        key=lambda row: (row["source"] != "correction", -row["count"], row["term"].casefold()),
    )[:50]


class VocabularyPage(QScrollArea):
    def __init__(self, history: "History", current: Callable[[], str], save: Callable[[str], None]):
        super().__init__()
        self.history, self.current, self.save = history, current, save
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.viewport().setAutoFillBackground(False)
        body = QWidget()
        body.setObjectName("glassBody")
        self.setWidget(body)
        layout = QVBoxLayout(body)
        heading = QLabel("Your vocabulary")
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        description = QLabel(
            "Names, apps and terms you want recognized. Only words you add or approve guide "
            "future dictations. This does not retrain the speech model."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.entry = QLineEdit()
        self.entry.setMaxLength(64)
        self.entry.setPlaceholderText("A name or corrected spelling, e.g. Codex")
        self.entry.setAccessibleName("Vocabulary word or phrase")
        layout.addWidget(self.entry)
        actions = QHBoxLayout()
        self.add_button = QPushButton("Add word")
        self.add_button.setProperty("primary", True)
        self.add_button.clicked.connect(self.add_word)
        self.entry.returnPressed.connect(self.add_word)
        self.correct_button = QPushButton("Suggest corrected spelling")
        self.correct_button.clicked.connect(self.suggest_correction)
        actions.addWidget(self.add_button)
        actions.addWidget(self.correct_button)
        layout.addLayout(actions)
        self.notice = QLabel()
        self.notice.setTextFormat(Qt.TextFormat.PlainText)
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.budget = QLabel()
        layout.addWidget(self.budget)
        self.words = QListWidget()
        self.words.setAccessibleName("Approved vocabulary")
        self.words.setMaximumHeight(180)
        layout.addWidget(self.words)
        self.remove_button = QPushButton("Remove selected word")
        self.remove_button.clicked.connect(self.remove_word)
        layout.addWidget(self.remove_button)
        layout.addWidget(QLabel("Suggestions to review"))
        help_text = QLabel(
            "Recurring names and technical terms from the latest 200 saved dictations, plus "
            "spellings you submit above. Pattern-based suggestions can be wrong; approve only "
            "the spelling you want. No other app's text is read."
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.empty_suggestions = QLabel(
            "No suggestions yet. Recurring terms will appear here for review."
        )
        self.empty_suggestions.setWordWrap(True)
        layout.addWidget(self.empty_suggestions)
        self.pending = QListWidget()
        self.pending.setAccessibleName("Vocabulary suggestions")
        self.pending.setMinimumHeight(110)
        layout.addWidget(self.pending)
        review = QHBoxLayout()
        self.accept_button = QPushButton("Approve word")
        self.accept_button.clicked.connect(self.approve)
        self.dismiss_button = QPushButton("Dismiss")
        self.dismiss_button.clicked.connect(self.dismiss)
        review.addWidget(self.accept_button)
        review.addWidget(self.dismiss_button)
        layout.addLayout(review)
        self.forget_button = QPushButton("Forget suggestion history")
        self.forget_button.setToolTip(
            "Clear saved corrections and dismissed terms. Approved words remain. "
            "Recurring terms may reappear from saved dictations."
        )
        self.forget_button.clicked.connect(self.forget_suggestions)
        layout.addWidget(self.forget_button)
        layout.addStretch()
        self.words.currentRowChanged.connect(
            lambda: self.remove_button.setEnabled(self.words.currentRow() >= 0)
        )
        self.pending.currentRowChanged.connect(self.update_review)

    def update_review(self) -> None:
        selected = self.pending.currentItem() is not None
        self.accept_button.setEnabled(selected)
        self.dismiss_button.setEnabled(selected)

    def refresh(self, message: str = "") -> None:
        self.notice.setText(message)
        self.words.clear()
        self.words.addItems(terms(self.current()))
        self.words.setFixedHeight(max(70, min(180, self.words.count() * 44 + 20)))
        self.budget.setText(
            f"Recognition hints: {len(self.current())}/300 characters. Keep the list focused."
        )
        self.pending.clear()
        try:
            rows = suggestions(
                self.history.vocabulary_samples(),
                self.history.vocabulary_feedback(),
                self.current(),
            )
            for row in rows:
                origin = (
                    "Your correction"
                    if row["source"] == "correction"
                    else f"Seen in {row['count']} dictations"
                )
                item = QListWidgetItem(f"{row['term']} · {origin}")
                item.setData(Qt.ItemDataRole.UserRole, row["term"])
                self.pending.addItem(item)
        except Exception:
            self.notice.setText("Suggestions could not be read. Reopen Vocabulary to retry.")
        self.remove_button.setEnabled(False)
        self.pending.setFixedHeight(max(90, min(200, self.pending.count() * 44 + 20)))
        self.pending.setVisible(self.pending.count() > 0)
        self.empty_suggestions.setVisible(self.pending.count() == 0)
        self.update_review()

    def add_word(self) -> None:
        self.save_word(self.entry.text())

    def save_word(self, value: str) -> None:
        try:
            word = normalize_term(value)
            existing = terms(self.current())
            if word.casefold() in {term.casefold() for term in existing}:
                raise ValueError("That word is already in your vocabulary.")
            combined = ", ".join([*existing, word])
            if len(combined) > 300:
                raise ValueError(
                    "Recognition hints are limited to 300 characters. Remove a word first."
                )
            self.save(combined)
        except ValueError as exc:
            self.notice.setText(str(exc))
            return
        except Exception:
            self.notice.setText("Vocabulary could not be saved. Your existing words are unchanged.")
            return
        self.entry.clear()
        self.refresh("Word added. It will guide your next dictation.")

    def suggest_correction(self) -> None:
        try:
            word = normalize_term(self.entry.text())
            self.history.set_vocabulary_feedback(word, "correction")
        except ValueError as exc:
            self.notice.setText(str(exc))
            return
        except Exception:
            self.notice.setText(
                "Correction could not be saved. Try again after checking local storage."
            )
            return
        self.entry.clear()
        self.refresh("Correction saved for review. Select it below and approve to use it.")

    def approve(self) -> None:
        item = self.pending.currentItem()
        if item:
            self.save_word(item.data(Qt.ItemDataRole.UserRole))

    def dismiss(self) -> None:
        item = self.pending.currentItem()
        if item:
            try:
                self.history.set_vocabulary_feedback(
                    item.data(Qt.ItemDataRole.UserRole), "dismissed"
                )
            except Exception:
                self.notice.setText(
                    "Suggestion could not be dismissed. Reopen Vocabulary to retry."
                )
                return
            self.refresh()

    def remove_word(self) -> None:
        item = self.words.currentItem()
        if item:
            try:
                self.save(", ".join(word for word in terms(self.current()) if word != item.text()))
            except Exception:
                self.notice.setText(
                    "Word could not be removed. Your existing vocabulary is unchanged."
                )
                return
            self.refresh()

    def forget_suggestions(self) -> None:
        if (
            QMessageBox.question(
                self,
                "Forget suggestion history",
                "Forget saved corrections and dismissals? Approved words remain. "
                "Recurring terms may reappear from saved dictations.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.history.clear_vocabulary_feedback()
        except Exception:
            self.notice.setText(
                "Suggestion history could not be cleared. Try again after checking local storage."
            )
            return
        self.refresh("Suggestion history cleared. Approved vocabulary is unchanged.")
