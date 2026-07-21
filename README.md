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

## Changelog

### v1.0.0

First stable release. This version combines a key binding fix with a new feature.

**Breaking change — key bindings:**
- Management key bindings changed from NVDA+Shift+P/O/S to NVDA+Alt+P/O/L to resolve conflicts with NVDA's built-in commands:
  - NVDA+Shift+S conflicted with sleep mode toggle (desktop layout) and read selection (laptop layout)
  - NVDA+Shift+O conflicted with report current navigator object (laptop layout)
  - NVDA+Shift+P was conflict-free but moved for consistency with the other management keys
- New bindings: NVDA+Alt+P (toggle), NVDA+Alt+O (on-demand), NVDA+Alt+L (save learning)
- Prediction selection keys (NVDA+Control+1-0) unchanged

**New feature — custom app exclusion list:**
- Users can now specify applications where word prediction should be disabled, in addition to the built-in terminal auto-detection
- Configure in Settings > Word Predictor > "Disable prediction in these applications"
- Enter one app executable name per line (case-insensitive, comments with #)
- Useful for MUD clients (VIP Mud, MushClient), code editors, or any app where predictions are unwanted
- Uses `appModule.appName` for matching, same mechanism as terminal detection

### v0.5.0

- **New feature:** Terminal auto-detection. Prediction is automatically disabled in terminal applications (Windows Terminal, PowerShell, CMD, WSL, PuTTY, Alacritty, WezTerm, and 25+ others). Detection uses both NVDA's own Terminal class classification and a list of known terminal app names. Can be toggled off in Settings > Word Predictor > "Disable in terminal applications".

### v0.4.0

- **Breaking change:** Prediction selection keys changed from bare number keys (1-0) to NVDA+Control+1 through NVDA+Control+0. The old bare number keys broke heading navigation in browse mode (keys 1-6 jump to heading levels) and interfered with typing numbers in edit fields. NVDA+Control+numbers don't conflict with browse mode (which uses bare numbers) or normal typing.
- **Bug fix:** Typing of accepted predictions is now deferred by 100ms so modifier keys (NVDA, Ctrl) are physically released before character keystrokes are sent. Previously, characters were sent while Ctrl was still held, triggering application shortcuts (Ctrl+H = history, Ctrl+S = save, etc.).
- Removed the `gesture.send()` passthrough on number keys since the add-on no longer intercepts bare number keys.

### v0.3.0

- Added settings panel in NVDA Settings
- Added configurable prediction count (1-10)
- Added learning on/off toggle
- Added partial-word prediction interval
- Added NVDA+Alt+O for on-demand predictions

### v0.2.0

- Added persistent learning (saves to NVDA user config)
- Added partial-word prediction
- Added on-demand prediction key

### v0.1.0

- Initial release
- N-gram prediction engine (bigrams + trigrams)
- Real-time learning
- Predictions announced through NVDA speech

## License

GPL v2, same as NVDA.

## Author

Lanie Carmelo-Molinar - [lanie.work](https://lanie.work)

A blind NVDA user who built this because existing word prediction tools don't work with screen readers.