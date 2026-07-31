# Changelog

## v1.5.0

- Adopted the NVDA add-on template for standardized builds and CI/CD.
- No functional changes to the add-on behavior.

## v1.4.0

- Bundled n-gram corpus expanded from 5,096 bigrams and 32,625 trigrams (1.6 MB) to 45,859 bigrams and 300,384 trigrams (25.4 MB), trained on 11 million tokens from 116 Project Gutenberg books. Predictions should be significantly more accurate with broader vocabulary coverage.

## v1.3.1

- Backspace no longer triggers a new prediction cycle. Previously, pressing backspace was treated as punctuation, which ended the current word and generated predictions. Now backspace removes the last character from the current word and does not trigger predictions.
- Disabled apps settings field now uses comma-separated input instead of one-per-line. NVDA's settings dialog framework captures the Enter key for the default OK button, making multi-line entry impossible. The parser now accepts both commas and newlines as separators.

## v1.3.0

- Predictions now only fire when focused on an editable text field. Uses NVDA's Role.EDITABLETEXT to detect edit fields, including browse mode documents (web pages, emails with text areas). Prevents false predictions when navigating Gmail, the file manager, or any non-edit context.
- Email address (lanie@lanie.work) added to manifest for easier contact by NV Access reviewers and users.
- URL in manifest updated from personal website (lanie.work) to GitHub repository.
- Fixed: bundled n-gram data (data/ngrams.json) was missing from the add-on package, causing predictions to only use words typed during the current session instead of the pre-built language model.

## v1.2.0

- Kneser-Ney smoothing engine for improved prediction ranking. Can be toggled in Settings.
- Settings panel with configurable predictions count, learning toggle, and partial-word prediction interval.
- Custom app exclusion list in Settings.
- Terminal auto-detection (disables predictions in terminals automatically).
- KneserNeyModel inlined into wordPredictor.py to avoid NVDA plugin loader misidentification.
- Modifier key conflict fixed: prediction selection keys changed from bare number keys to NVDA+Control+number.
- Typing deferred 100ms so modifier keys are physically released before predicted word is sent.

## v1.1.0

- Fixed: accepted words inserted with improper spacing or capitalization after punctuation. Added last_ending_char tracker to handle spacing and capitalization correctly.

## v1.0.0

- Application exclusion system with parse_disabled_apps, is_user_disabled_app, and should_disable methods.
- Published to NVDA Add-on Store.

## v0.3.0

- Settings panel with configurable predictions count, learning toggle, and partial-word prediction interval.
- Scripts correctly appear under "Word Predictor" category in NVDA's Input Gestures dialog.
- Fixed: contractions like "don't" now handled correctly.
- Fixed: capitalization for "I" corrected.
- Punctuation-triggered predictions enhanced.

## v0.2.0

- Persistent learning across sessions.
- Partial-word prediction.
- On-demand prediction key.

## v0.1.0

- Initial release. Proactive word prediction using n-gram analysis with NVDA speech announcements.
- Accept predictions with NVDA+Control+number keys (1 through 0).
- Learns from your writing over time.
