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
- **Partial-word prediction:** Type part of a word and press NVDA+Shift+O to get suggestions that complete what you're typing.
- **Audible alert:** A short beep plays before predictions are announced (configurable).
- **Keyboard selection:** Press 1-5 to accept a prediction. The word is typed automatically.
- **Learns from your writing:** The n-gram model updates in real time as you type, learning your vocabulary and word patterns.
- **Persistent learning:** Learned data saves to your NVDA user config and accumulates across restarts.
- **Pre-trained:** Ships with n-gram data trained on published writing and common English word pairs, including contractions.
- **Toggle on/off:** Press NVDA+Shift+P to toggle prediction on or off.
- **Settings panel:** Configure predictions count, beep, and learning from NVDA's Settings dialog.
- **Remappable keys:** All shortcuts appear under "Word Predictor" in NVDA's Input Gestures dialog.
- **Works everywhere:** As a global plugin, prediction works in any application where you type text.

## Key Bindings

| Key | Action |
|-----|--------|
| 1-0 | Accept prediction 1-10 (only intercepts when predictions are active) |
| NVDA+Shift+P | Toggle word prediction on/off |
| NVDA+Shift+O | Request predictions on demand (partial or full) |
| NVDA+Shift+S | Save learning to disk manually |

All key bindings can be remapped in NVDA's Input Gestures dialog under the "Word Predictor" category.

## Installation

1. Download the latest release `.nvda-addon` file from the [releases page](https://github.com/RareBird15/wordpredictor/releases).
2. Open the file from Windows File Explorer to install it through NVDA's add-on installer.
3. Restart NVDA.

## Usage

1. Start typing in any text field.
2. When you press space after a word, you'll hear a short beep followed by up to 5 predictions.
3. Press 1 to accept the first prediction, 2 for the second, etc.
4. The predicted word is typed automatically with a trailing space.
5. For partial-word prediction, type part of a word and press NVDA+Shift+O.
6. Press NVDA+Shift+P to toggle prediction on or off.
7. Configure settings in NVDA Menu > Settings > Word Predictor.

## How It Works

The add-on uses n-gram language modeling:

- **Bigrams:** Tracks which words commonly follow other words (e.g., "the" -> "system")
- **Trigrams:** Tracks which words commonly follow two-word combinations (e.g., "I am" -> "not")
- **Trigram priority:** Trigram predictions are checked first for better context-aware results, falling back to bigrams if needed
- **Partial matching:** When you type part of a word, the add-on searches all n-grams for words that start with what you've typed
- **Real-time learning:** Every word you type updates the n-gram counts, so the model adapts to your writing style
- **Persistent storage:** Learning saves to `wordPredictor_learned.json` in your NVDA user config directory

The n-gram data is stored as a JSON file and loaded at startup. No external Python dependencies are required.

## Technical Details

- **NVDA version:** Requires NVDA 2026.1 or later (Python 3.13, 64-bit)
- **Architecture:** Global plugin using `event_typedCharacter` for input tracking
- **Prediction engine:** Custom n-gram implementation, no NLTK dependency at runtime
- **Data file:** ~1.6 MB JSON file with bigram and trigram counts
- **Config:** Settings stored in NVDA's config under the `wordPredictor` key

## License

GPL v2, same as NVDA.

## Author

Lanie Carmelo-Molinar - [lanie.work](https://lanie.work)

A blind NVDA user who built this because existing word prediction tools don't work with screen readers.