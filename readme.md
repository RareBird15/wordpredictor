# WordPredictor - NVDA Add-on for Proactive Word Prediction

An NVDA add-on that watches what you type and predicts the next word using n-gram analysis. Predictions are announced through NVDA's own speech engine and can be accepted with keyboard shortcuts.

## Why This Exists

Existing word prediction tools like Lightkey Pro AT have significant accessibility barriers when used with NVDA:

- Gestures conflict with NVDA commands
- System-wide prediction requires mouse clicking
- Words get mangled when pasting alongside NVDA

This add-on solves those problems by working inside NVDA itself. No external TTS, no clipboard pasting, no mouse required. Predictions are spoken through NVDA's speech engine and inserted directly through NVDA's keyboard input system.

## Features

- **Proactive prediction:** After you complete a word (press space or punctuation), NVDA announces up to 5 predicted next words.
- **Partial-word prediction:** Type part of a word and press NVDA+Alt+O to get suggestions that complete what you're typing.
- **Audible alert:** A short beep plays before predictions are announced (configurable).
- **Keyboard selection:** Press 1-5 to accept a prediction. The word is typed automatically.
- **Learns from your writing:** The n-gram model updates in real time as you type, learning your vocabulary and word patterns.
- **Persistent learning:** Learned data saves to your NVDA user config and accumulates across restarts.
- **Pre-trained:** Ships with n-gram data trained on published writing and common English word pairs, including contractions.
- **Toggle on/off:** Press NVDA+Alt+P to toggle prediction on or off.
- **Settings panel:** Configure predictions count, beep, and learning from NVDA's Settings dialog.
- **Remappable keys:** All shortcuts appear under "Word Predictor" in NVDA's Input Gestures dialog.
- **Works everywhere:** As a global plugin, prediction works in any application where you type text.
- **Terminal-aware:** Automatically disables prediction in terminal applications (Windows Terminal, PowerShell, CMD, WSL, PuTTY, and 25+ others). Can be turned off in settings.
- **Custom app exclusion:** Add your own apps where you don't want predictions (MUD clients, code editors, chat apps with slash commands, etc.) in Settings > Word Predictor. One app name per line.
- **Punctuation-aware insertion:** When you accept a prediction after a period, question mark, or exclamation point, it automatically inserts a leading space and capitalizes the first letter. After a comma, semicolon, or colon, it inserts a leading space without capitalization.

## Key Bindings

| Key | Action |
|-----|--------|
| NVDA+Control+1 through NVDA+Control+0 | Accept prediction 1-10 (only intercepts when predictions are active) |
| NVDA+Alt+P | Toggle word prediction on/off |
| NVDA+Alt+O | Request predictions on demand (partial or full) |
| NVDA+Alt+L | Save learning to disk manually |

All key bindings can be remapped in NVDA's Input Gestures dialog under the "Word Predictor" category.

## Installation

1. Download the latest release `.nvda-addon` file from the [releases page](https://github.com/RareBird15/wordpredictor/releases).
2. Open the file from Windows File Explorer to install it through NVDA's add-on installer.
3. Restart NVDA.

## Usage

1. Start typing in any text field.
2. When you press space after a word, you'll hear a short beep followed by up to 5 predictions.
3. Press NVDA+Control+1 to accept the first prediction, NVDA+Control+2 for the second, etc.
4. The predicted word is typed automatically with a trailing space.
5. For partial-word prediction, type part of a word and press NVDA+Alt+O.
6. Press NVDA+Alt+P to toggle prediction on or off.
7. Configure settings in NVDA Menu > Settings > Word Predictor.

## How It Works

The add-on uses two prediction engines:

**N-gram model (default):** Uses bigram and trigram analysis with Kneser-Ney smoothing. Fast, lightweight, and learns from your writing in real time. No external dependencies required.

**LSTM neural network (optional):** A small language model trained on 116 Project Gutenberg books (20,000-word vocabulary). Provides context-aware predictions that understand longer-range patterns. Toggle in Settings > Word Predictor. Requires onnxruntime (bundled DLLs included, or install via `pip install onnxruntime`).

Both engines work together — the n-gram model handles predictions by default, and you can switch to the LSTM for more contextually aware suggestions.

### N-gram Model Details

- **Bigrams:** Tracks which words commonly follow other words (e.g., "the" -> "system")
- **Trigrams:** Tracks which words commonly follow two-word combinations (e.g., "I am" -> "not")
- **Kneser-Ney smoothing:** Instead of ranking predictions by raw frequency, uses interpolated Kneser-Ney probability. This rewards words that appear in many different contexts (like "the", "is", "and") over words that appear frequently but only in specific phrases (like "York" after "New"). Handles unseen n-grams gracefully by backing off to lower-order n-grams with adjusted probabilities.
- **Three-level interpolation:** Trigram probability is blended with bigram probability, which is blended with unigram continuation probability. This means even words never seen in the exact context still get a probability based on how common they are as continuations.
- **Partial matching:** When you type part of a word, the add-on searches all n-grams for words that start with what you've typed and ranks them by KN probability
- **Real-time learning:** Every word you type updates the n-gram counts and derived statistics, so the model adapts to your writing style
- **Persistent storage:** Learning saves to `wordPredictor_learned.json` in your NVDA user config directory
- **Backward compatible:** Existing learned data from v1.1.0 loads without migration. Smoothing can be turned off in settings to restore the original frequency-based behavior.

The n-gram data is stored as a JSON file and loaded at startup. No external Python dependencies are required.

## Technical Details

- **NVDA version:** Requires NVDA 2026.1 or later (Python 3.13, 64-bit)
- **Architecture:** Global plugin using `event_typedCharacter` for input tracking
- **Prediction engine:** Custom n-gram implementation, no NLTK dependency at runtime
- **Data file:** ~1.6 MB JSON file with bigram and trigram counts
- **Config:** Settings stored in NVDA's config under the `wordPredictor` key

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the full version history.

## License

GPL v2, same as NVDA.

## Author

Lanie Carmelo-Molinar - [lanie.work](https://lanie.work)

A blind NVDA user who built this because existing word prediction tools don't work with screen readers.
