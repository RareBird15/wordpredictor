# Changelog

All notable changes to WordPredictor will be documented in this file.

## [1.4.0] - 2026-07-29

### Changed
- Bundled n-gram corpus expanded from 5,096 bigrams and 32,625 trigrams (1.6 MB) to 45,859 bigrams and 300,384 trigrams (25.4 MB), trained on 11 million tokens from 116 Project Gutenberg books. Predictions should be significantly more accurate with broader vocabulary coverage.

## [1.3.1] - 2026-07-27

### Fixed
- Backspace no longer triggers a new prediction cycle. Previously, pressing backspace was treated as punctuation, which ended the current word and generated predictions. Now backspace removes the last character from the current word and does not trigger predictions.
- Disabled apps settings field now uses comma-separated input instead of one-per-line. NVDA's settings dialog framework captures the Enter key for the default OK button, making multi-line entry impossible. The parser now accepts both commas and newlines as separators.

## [1.3.0] - 2026-07-26

### Added
- Predictions now only fire when focused on an editable text field. Uses NVDA's `Role.EDITABLETEXT` to detect edit fields, including browse mode documents (web pages, emails with text areas). Prevents false predictions when navigating Gmail, the file manager, or any non-edit context.
- Email address (`lanie@lanie.work`) added to manifest for easier contact by NV Access reviewers and users.

### Changed
- URL in manifest updated from personal website (`lanie.work`) to GitHub repository (`https://github.com/RareBird15/wordPredictor`).

### Fixed
- Bundled n-gram data (`data/ngrams.json`) was missing from the add-on package, causing predictions to only use words typed during the current session instead of the pre-built language model.

## [1.2.0] - 2026-07-23

### Added
- Kneser-Ney smoothing engine for improved prediction ranking. Can be toggled in Settings.
- Settings panel with configurable predictions count, learning toggle, and partial-word prediction interval.
- Custom app exclusion list in Settings.
- Terminal auto-detection (disables predictions in terminals automatically).

### Changed
- KneserNeyModel inlined into `wordPredictor.py` to avoid NVDA plugin loader misidentification.
- Modifier key conflict fixed: prediction selection keys changed from bare number keys to `NVDA+Control+number`.
- Typing deferred 100ms so modifier keys are physically released before predicted word is sent.

## [1.1.0] - 2026-07-22

### Fixed
- Accepted words inserted with improper spacing or capitalization after punctuation. Added `self._last_ending_char` tracker to handle spacing and capitalization correctly.

## [1.0.0] - 2026-07-21

### Added
- Application exclusion system with `_parse_disabled_apps`, `_is_user_disabled_app`, and `_should_disable` methods.
- Published to NVDA Add-on Store.

## [0.3.0] - 2026-07-20

### Added
- Settings panel with configurable predictions count, learning toggle, and partial-word prediction interval.
- Scripts correctly appear under "Word Predictor" category in NVDA's Input Gestures dialog.

### Fixed
- Contractions like "don't" now handled correctly.
- Capitalization for "I" corrected.
- Punctuation-triggered predictions enhanced.

## [0.2.0] - 2026-07-19

### Added
- Persistent learning across sessions.
- Partial-word prediction.
- On-demand prediction key.

## [0.1.0] - 2026-07-19

### Added
- Initial release. Proactive word prediction using n-gram analysis with NVDA speech announcements.
- Accept predictions with `NVDA+Control+number` keys (1 through 0).
- Learns from your writing over time.