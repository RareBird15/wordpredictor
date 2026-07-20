# WordPredictor - NVDA Add-on for Proactive Word Prediction

An NVDA add-on that watches what you type and predicts the next word using n-gram analysis. Predictions are announced through NVDA's own speech engine and can be accepted with keyboard shortcuts.

## Why This Exists

Existing word prediction tools like Lightkey Pro AT have significant accessibility barriers when used with NVDA:

- Gestures conflict with NVDA commands
- System-wide prediction requires mouse clicking
- Words get mangled when pasting alongside NVDA

This add-on solves those problems by working inside NVDA itself. No external TTS, no clipboard pasting, no mouse required. Predictions are spoken through NVDA's speech engine and inserted directly through NVDA's keyboard input system.

## Features

- **Proactive prediction:** After you complete a word (press space), NVDA announces the top 5 predicted next words.
- **Audible alert:** A short beep plays before predictions are announced, so you know to listen.
- **Keyboard selection:** Press Ctrl+NVDA+1 through 5 to accept a prediction. The word is typed automatically.
- **Learns from your writing:** The n-gram model updates in real time as you type, learning your vocabulary and word patterns.
- **Pre-trained:** Ships with n-gram data trained on the author's published writing and common English word pairs.
- **Toggle on/off:** Press NVDA+Shift+P to toggle prediction on or off without going into settings.
- **Works everywhere:** As a global plugin, prediction works in any application where you type text.

## Installation

1. Download the latest release `.nvda-addon` file from the releases page.
2. Open the file from Windows File Explorer to install it through NVDA's add-on installer.
3. Restart NVDA.

## Usage

1. Start typing in any text field.
2. When you press space after a word, you'll hear a short beep followed by up to 5 predictions.
3. Press Ctrl+NVDA+1 to accept the first prediction, Ctrl+NVDA+2 for the second, etc.
4. The predicted word is typed automatically with a trailing space.
5. Press NVDA+Shift+P to toggle prediction on or off.

## How It Works

The add-on uses n-gram language modeling:

- **Bigrams:** Tracks which words commonly follow other words (e.g., "the" -> "system")
- **Trigrams:** Tracks which words commonly follow two-word combinations (e.g., "I am" -> "not")
- **Trigram priority:** Trigram predictions are checked first for better context-aware results, falling back to bigrams if needed
- **Real-time learning:** Every word you type updates the n-gram counts, so the model adapts to your writing style

The n-gram data is stored as a JSON file and loaded at startup. No external Python dependencies are required.

## Technical Details

- **NVDA version:** Requires NVDA 2026.1 or later (Python 3.13, 64-bit)
- **Architecture:** Global plugin using `event_typedCharacter` for input tracking
- **Prediction engine:** Custom n-gram implementation, no NLTK dependency at runtime
- **Data file:** ~1.5 MB JSON file with bigram and trigram counts

## License

GPL v2, same as NVDA.

## Author

Lanie Carmelo-Molinar - [lanie.work](https://lanie.work)

A blind NVDA user who built this because existing word prediction tools don't work with screen readers.