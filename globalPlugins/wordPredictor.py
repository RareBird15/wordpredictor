# WordPredictor - NVDA add-on for proactive word prediction
# Author: Lanie Carmelo-Molinar
# License: GPL v2
#
# A global plugin that watches what you type, predicts the next word
# using n-gram analysis, and announces predictions through NVDA's
# speech engine. Designed for screen reader users, by a screen reader user.
#
# v0.2.0: Adds persistent learning, partial-word prediction, and
# on-demand prediction key.
# v0.3.0: Adds settings panel, configurable predictions count,
# learning toggle, and partial-word prediction interval.
# v0.4.0: Fixes modifier key conflict. Prediction selection keys
# changed from bare number keys to NVDA+control+number (1 through 0)
# to avoid breaking heading navigation in browse mode and number
# typing. Typing is now deferred 100ms so modifier keys (NVDA, Ctrl)
# are physically released before the predicted word is sent,
# preventing Ctrl+letter shortcuts from firing.

import globalPluginHandler
import scriptHandler
import ui
import tones
import os
import json
import config
import threading
import gui
import gui.settingsDialogs
import wx
import api

# Configuration key for the add-on
CONFIG_KEY = "wordPredictor"
DEFAULT_CONFIG = {
	"enabled": True,
	"maxPredictions": 5,
	"beepBeforePredictions": True,
	"learningEnabled": True,
	"disableInTerminals": True,
}

# Script category for NVDA Input Gestures dialog
SCRIPT_CATEGORY = "Word Predictor"

# Delay (ms) before typing accepted prediction, to allow modifier
# keys to be released. Without this, characters sent while Ctrl is
# still held trigger application shortcuts (Ctrl+H, Ctrl+S, etc.).
TYPE_DELAY_MS = 100

# Known terminal application names. When the focused app matches one
# of these, word prediction is automatically disabled to avoid
# interfering with command-line input. This list covers built-in
# Windows terminals, popular third-party terminal emulators, and WSL.
TERMINAL_APP_NAMES = frozenset([
	# Built-in Windows terminals
	"windowsterminal",  # Windows Terminal
	"cmd",              # Command Prompt
	"powershell",       # Windows PowerShell
	"pwsh",             # PowerShell Core
	"conhost",          # Console Host
	# Third-party terminal emulators
	"cmder",
	"conemu",
	"conemu64",
	"mintty",           # Git Bash
	"putty",
	"kitty",
	"terminus",
	"hyper",
	"alacritty",
	"wezterm",
	"wezterm-gui",
	"tabby",
	"fluent",
	# WSL
	"wsl",
	"bash",
	# Modern terminals
	"ghostty",
	"rio",
	"waveterm",
	"contour",
	"cool-retro-term",
	# Remote/professional terminals
	"mobaxterm",
	"securecrt",
	"ttermpro",
	"mremoteng",
	"royalts",
])


class SettingsPanel(gui.settingsDialogs.SettingsPanel):
	"""Settings panel for Word Predictor add-on."""

	# Required: title shown in NVDA Settings dialog
	title = "Word Predictor"

	# Class-level reference to the running plugin, set by GlobalPlugin
	_plugin = None

	def makeSettings(self, sizer):
		"""Create the settings controls."""
		settings = config.conf[CONFIG_KEY]

		# Helper to convert config values to proper Python types
		def to_bool(val, default=True):
			if isinstance(val, bool):
				return val
			if isinstance(val, str):
				return val.lower() in ("true", "1", "yes")
			return default

		def to_int(val, default=5):
			try:
				return int(val)
			except (TypeError, ValueError):
				return default

		# Enable/disable checkbox
		self.enabledCheckbox = wx.CheckBox(self, label="Enable word prediction")
		self.enabledCheckbox.SetValue(to_bool(settings.get("enabled", True)))
		sizer.Add(self.enabledCheckbox, border=10, flag=wx.BOTTOM)

		# Number of predictions
		sizer.Add(wx.StaticText(self, label="Number of predictions (1-10):"), border=10, flag=wx.TOP | wx.BOTTOM)
		self.predictionsSpinner = wx.SpinCtrl(self, min=1, max=10, value=str(to_int(settings.get("maxPredictions", 5))))
		sizer.Add(self.predictionsSpinner, border=10, flag=wx.BOTTOM)

		# Beep before predictions
		self.beepCheckbox = wx.CheckBox(self, label="Play beep before announcing predictions")
		self.beepCheckbox.SetValue(to_bool(settings.get("beepBeforePredictions", True)))
		sizer.Add(self.beepCheckbox, border=10, flag=wx.BOTTOM)

		# Learning enabled
		self.learningCheckbox = wx.CheckBox(self, label="Learn from my writing")
		self.learningCheckbox.SetValue(to_bool(settings.get("learningEnabled", True)))
		sizer.Add(self.learningCheckbox, border=10, flag=wx.BOTTOM)

		# Disable in terminals
		self.terminalCheckbox = wx.CheckBox(self, label="Disable in terminal applications")
		self.terminalCheckbox.SetValue(to_bool(settings.get("disableInTerminals", True)))
		sizer.Add(self.terminalCheckbox, border=10, flag=wx.BOTTOM)

	def onSave(self):
		"""Save settings when the user clicks OK or Apply."""
		settings = config.conf[CONFIG_KEY]
		settings["enabled"] = self.enabledCheckbox.IsChecked()
		settings["maxPredictions"] = int(self.predictionsSpinner.GetValue())
		settings["beepBeforePredictions"] = self.beepCheckbox.IsChecked()
		settings["learningEnabled"] = self.learningCheckbox.IsChecked()
		settings["disableInTerminals"] = self.terminalCheckbox.IsChecked()

		# Apply settings to the running plugin
		if SettingsPanel._plugin:
			SettingsPanel._plugin._enabled = settings["enabled"]
			SettingsPanel._plugin._max_predictions = settings["maxPredictions"]
			SettingsPanel._plugin._beep_enabled = settings["beepBeforePredictions"]
			SettingsPanel._plugin._learning_enabled = settings["learningEnabled"]
			SettingsPanel._plugin._disable_in_terminals = settings["disableInTerminals"]

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""Global plugin that provides proactive word prediction for NVDA users."""

	# Bundled data file (read-only, ships with add-on)
	BUNDLED_DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "ngrams.json")

	# Learned data file (writable, in NVDA user config directory)
	@property
	def _learned_data_file(self):
		"""Path to the learned n-gram data in NVDA's user config."""
		return os.path.join(config.getUserConfigPath(), "wordPredictor_learned.json")

	# Minimum characters before partial-word prediction kicks in
	MIN_PARTIAL_LENGTH = 2

	# Minimum interval between partial-word predictions (in characters typed)
	PARTIAL_PREDICTION_INTERVAL = 2

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		# Set plugin reference for the settings panel
		SettingsPanel._plugin = self
		# Initialize config with defaults if not present
		if CONFIG_KEY not in config.conf:
			config.conf[CONFIG_KEY] = DEFAULT_CONFIG.copy()
		settings = config.conf[CONFIG_KEY]
		# Convert config values to proper types (NVDA config stores as strings)
		def to_bool(val, default=True):
			if isinstance(val, bool):
				return val
			if isinstance(val, str):
				return val.lower() in ("true", "1", "yes")
			return default

		def to_int(val, default=5):
			try:
				return int(val)
			except (TypeError, ValueError):
				return default

		self._enabled = to_bool(settings.get("enabled", True))
		self._word_buffer = []  # Last 3 completed words
		self._current_word = ""  # Word currently being typed
		self._predictions = []  # Current list of predictions
		self._partial_predictions = []  # Predictions for partial word
		self._max_predictions = to_int(settings.get("maxPredictions", 5))
		self._beep_enabled = to_bool(settings.get("beepBeforePredictions", True))
		self._learning_enabled = to_bool(settings.get("learningEnabled", True))
		self._disable_in_terminals = to_bool(settings.get("disableInTerminals", True))
		self._terminal_cache = {}  # Cache for terminal app detection
		self._bigrams = {}
		self._trigrams = {}
		self._save_lock = threading.Lock()
		self._dirty = False  # True when n-grams have been modified
		self._chars_since_partial = 0  # Characters typed since last partial prediction
		# Register settings panel with NVDA
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(SettingsPanel)
		# Load n-grams
		self._load_ngrams()

	def _is_terminal(self):
		"""Check if the currently focused application is a terminal.

		Uses two detection methods:
		1. NVDA's own Terminal class classification (catches any terminal
		   NVDA already knows about, including ones not in our list).
		2. App name matching against TERMINAL_APP_NAMES (catches terminals
		   that NVDA might not classify but are known terminal emulators).

		Results are cached per app name to avoid repeated lookups.
		Returns True if in a terminal and disableInTerminals is enabled.
		"""
		if not self._disable_in_terminals:
			return False
		try:
			obj = api.getFocusObject()
			if not obj:
				return False
			# Check NVDA's own Terminal classification first
			from NVDAObjects.behaviors import Terminal
			if isinstance(obj, Terminal):
				return True
			# Check app name against known terminal list
			if not obj.appModule:
				return False
			app_name = obj.appModule.appName.lower()
			if not isinstance(app_name, str):
				return False
			# Check cache
			cached = self._terminal_cache.get(app_name)
			if cached is not None:
				return cached
			result = app_name in TERMINAL_APP_NAMES
			self._terminal_cache[app_name] = result
			return result
		except Exception:
			return False

	def _load_ngrams(self):
		"""Load n-gram data from learned file, falling back to bundled data."""
		# Try learned file first (has accumulated learning)
		try:
			learned_path = self._learned_data_file
			if os.path.exists(learned_path):
				with open(learned_path, "r", encoding="utf-8") as f:
					data = json.load(f)
				self._bigrams = data.get("bigrams", {})
				self._trigrams = data.get("trigrams", {})
				return
		except Exception:
			pass

		# Fall back to bundled data file
		try:
			with open(self.BUNDLED_DATA_FILE, "r", encoding="utf-8") as f:
				data = json.load(f)
			self._bigrams = data.get("bigrams", {})
			self._trigrams = data.get("trigrams", {})
		except Exception:
			self._bigrams = {}
			self._trigrams = {}

	def _save_ngrams(self):
		"""Save n-gram data to the learned file in NVDA's user config."""
		if not self._dirty:
			return

		try:
			with self._save_lock:
				data = {
					"bigrams": self._bigrams,
					"trigrams": self._trigrams,
				}
				with open(self._learned_data_file, "w", encoding="utf-8") as f:
					json.dump(data, f)
				self._dirty = False
		except Exception:
			# Don't crash NVDA if saving fails
			pass

	def _get_predictions(self):
		"""Get word predictions based on the current word buffer."""
		if not self._bigrams:
			return []

		predictions = []

		# Try trigram first (more context = better prediction)
		if len(self._word_buffer) >= 2:
			key = f"{self._word_buffer[-2]} {self._word_buffer[-1]}"
			if key in self._trigrams:
				sorted_preds = sorted(
					self._trigrams[key].items(),
					key=lambda x: x[1],
					reverse=True
				)
				predictions = [p[0] for p in sorted_preds[:self._max_predictions]]

		# Fall back to bigram if trigram didn't find enough
		if len(predictions) < self._max_predictions and self._word_buffer:
			last_word = self._word_buffer[-1]
			if last_word in self._bigrams:
				sorted_preds = sorted(
					self._bigrams[last_word].items(),
					key=lambda x: x[1],
					reverse=True
				)
				bigram_preds = [p[0] for p in sorted_preds[:self._max_predictions]]
				for p in bigram_preds:
					if p not in predictions:
						predictions.append(p)
					if len(predictions) >= self._max_predictions:
						break

		return predictions[:self._max_predictions]

	def _get_partial_predictions(self, partial):
		"""Get predictions for a partially typed word.

		Looks at ALL next-word predictions for the current context
		and filters to only words that start with the partial text.
		This searches beyond the top 5 so that less common but matching
		words still appear.
		"""
		if not partial or len(partial) < self.MIN_PARTIAL_LENGTH:
			return []

		partial_lower = partial.lower()
		matching = []

		# Gather all candidate words from trigrams first
		if len(self._word_buffer) >= 2:
			key = f"{self._word_buffer[-2]} {self._word_buffer[-1]}"
			if key in self._trigrams:
				for word, count in self._trigrams[key].items():
					if word.startswith(partial_lower) and word not in matching:
						matching.append((word, count))

		# Then from bigrams
		if self._word_buffer:
			last_word = self._word_buffer[-1]
			if last_word in self._bigrams:
				for word, count in self._bigrams[last_word].items():
					if word.startswith(partial_lower):
						# Check if already found via trigram
						already = any(w == word for w, _ in matching)
						if not already:
							matching.append((word, count))

		# Also search all bigrams globally as a fallback for words
		# that might follow any word and start with the partial
		if len(matching) < 3:
			for prev_word, nexts in self._bigrams.items():
				for word, count in nexts.items():
					if word.startswith(partial_lower):
						already = any(w == word for w, _ in matching)
						if not already:
							matching.append((word, count))
				if len(matching) >= 10:
					break

		# Sort by frequency (most common first)
		matching.sort(key=lambda x: x[1], reverse=True)

		return [w for w, _ in matching[:self._max_predictions]]

	def _beep(self):
		"""Play the prediction alert beep if enabled."""
		if self._beep_enabled:
			tones.beep(660, 50)

	def _announce_predictions(self):
		"""Announce the current predictions through NVDA speech."""
		if not self._enabled or not self._predictions:
			return

		# Format: "Predictions: 1: word, 2: word, 3: word"
		parts = []
		for i, word in enumerate(self._predictions):
			parts.append(f"{i + 1}: {word}")
		ui.message("Predictions: " + ", ".join(parts))

	def _announce_partial_predictions(self):
		"""Announce partial-word predictions through NVDA speech."""
		if not self._enabled or not self._partial_predictions:
			return

		# Format: "Suggestions: 1: word, 2: word"
		parts = []
		for i, word in enumerate(self._partial_predictions):
			parts.append(f"{i + 1}: {word}")
		ui.message("Suggestions: " + ", ".join(parts))

	def _learn_from_word(self, word):
		"""Update n-gram counts with the new word."""
		if not self._learning_enabled or not word:
			return

		word = word.lower()

		# Update bigram: previous word -> this word
		if self._word_buffer:
			prev = self._word_buffer[-1]
			if prev not in self._bigrams:
				self._bigrams[prev] = {}
			if word not in self._bigrams[prev]:
				self._bigrams[prev][word] = 0
			self._bigrams[prev][word] += 1

		# Update trigram: (two words ago, previous word) -> this word
		if len(self._word_buffer) >= 2:
			key = f"{self._word_buffer[-2]} {self._word_buffer[-1]}"
			if key not in self._trigrams:
				self._trigrams[key] = {}
			if word not in self._trigrams[key]:
				self._trigrams[key][word] = 0
			self._trigrams[key][word] += 1

		# Add word to buffer (keep last 3)
		self._word_buffer.append(word)
		if len(self._word_buffer) > 3:
			self._word_buffer.pop(0)

		# Mark as needing save
		self._dirty = True

	def _accept_prediction(self, index, is_partial=False):
		"""Insert a predicted word into the current text field.

		For partial predictions, we need to type only the remaining
		characters (the part the user hasn't typed yet).

		The prediction gesture includes NVDA+Control, so the Control
		key is still physically held down when this script runs. We
		must explicitly release it before sending character keystrokes,
		otherwise the OS interprets the characters as Control+letter
		shortcuts (Ctrl+S = save, Ctrl+H = history, etc.).

		We also defer the typing slightly (TYPE_DELAY_MS) to give the
		NVDA modifier key time to release, since NVDA's own key handling
		may not have completed the key-up by the time our script runs.
		"""
		predictions = self._partial_predictions if is_partial else self._predictions
		if index < 0 or index >= len(predictions):
			return

		word = predictions[index]

		# Capitalize "I" if it's a standalone word
		if word == "i":
			word = "I"

		# For partial predictions, only type the remaining characters
		if is_partial and self._current_word:
			chars_to_type = word[len(self._current_word):]
		else:
			chars_to_type = word

		word_to_learn = word.lower()

		# Clear state immediately so duplicate accepts don't fire
		self._current_word = ""
		self._predictions = []
		self._partial_predictions = []

		# Defer typing to allow the NVDA modifier key to be released.
		# We must release Control before sending characters, but we must
		# do it inside ignoreInjection() so NVDA doesn't intercept the
		# key-up event (which would prevent the OS from seeing it).
		def _do_type():
			import keyboardHandler
			import winUser

			# Release Control inside ignoreInjection so NVDA passes
			# the key-up through to the OS. Without this, NVDA's
			# internal_keyUpEvent intercepts the injected key-up
			# and returns False (consume), so the OS never sees
			# Control released and characters arrive as Ctrl+letter.
			with keyboardHandler.ignoreInjection():
				winUser.keybd_event(winUser.VK_CONTROL, 0, 2, 0)

			# Now type each character of the predicted word
			for char in chars_to_type:
				if char.isupper():
					keyboardHandler.KeyboardInputGesture.fromName(
						f"shift+{char.lower()}"
					).send()
				else:
					keyboardHandler.KeyboardInputGesture.fromName(char).send()
			# Add a space after the word
			keyboardHandler.KeyboardInputGesture.fromName("space").send()

			# Restore Control key state (these scripts only fire on
			# NVDA+Control+number, so Control was involved)
			with keyboardHandler.ignoreInjection():
				winUser.keybd_event(winUser.VK_CONTROL, 0, 0, 0)

			# Learn from the accepted word
			self._learn_from_word(word_to_learn)
			# Announce what was inserted
			ui.message(f"Inserted: {word}")

		wx.CallLater(TYPE_DELAY_MS, _do_type)

	@scriptHandler.script(
		gesture="kb:NVDA+shift+p",
		description="Toggle word prediction on or off",
		category=SCRIPT_CATEGORY
	)
	def script_togglePrediction(self, gesture):
		self._enabled = not self._enabled
		if self._enabled:
			ui.message("Word prediction on")
		else:
			ui.message("Word prediction off")
			self._predictions = []
			self._partial_predictions = []
			self._current_word = ""

	@scriptHandler.script(
		gesture="kb:NVDA+shift+s",
		description="Save learned word prediction data to disk",
		category=SCRIPT_CATEGORY
	)
	def script_saveLearning(self, gesture):
		self._save_ngrams()
		ui.message("Word prediction learning saved")

	@scriptHandler.script(
		gesture="kb:NVDA+shift+o",
		description="Request word predictions on demand",
		category=SCRIPT_CATEGORY
	)
	def script_onDemandPrediction(self, gesture):
		"""Request predictions manually without waiting for space."""
		if not self._enabled:
			return

		# Don't predict in terminal applications
		if self._is_terminal():
			return

		# If we're in the middle of typing a word, get partial predictions
		if self._current_word and len(self._current_word) >= self.MIN_PARTIAL_LENGTH:
			self._partial_predictions = self._get_partial_predictions(self._current_word)
			if self._partial_predictions:
				self._predictions = []  # Clear full predictions
				self._beep()
				self._announce_partial_predictions()
			else:
				# No partial matches, try full predictions for the context
				self._predictions = self._get_predictions()
				if self._predictions:
					self._partial_predictions = []
					self._beep()
					self._announce_predictions()
				else:
					ui.message("No predictions available")
		else:
			# No current word, get full next-word predictions
			self._predictions = self._get_predictions()
			if self._predictions:
				self._partial_predictions = []
				self._beep()
				self._announce_predictions()
			else:
				ui.message("No predictions available")

	@scriptHandler.script(
		gesture="kb:NVDA+control+1",
	description="Accept word prediction 1",
		category=SCRIPT_CATEGORY
	)
	def script_acceptPrediction1(self, gesture):
		if self._enabled and (self._predictions or self._partial_predictions):
			if self._partial_predictions:
				self._accept_prediction(0, is_partial=True)
			else:
				self._accept_prediction(0)

	@scriptHandler.script(
		gesture="kb:NVDA+control+2",
	description="Accept word prediction 2",
		category=SCRIPT_CATEGORY
	)
	def script_acceptPrediction2(self, gesture):
		if self._enabled and (
			len(self._predictions) > 1 or len(self._partial_predictions) > 1
		):
			if self._partial_predictions:
				self._accept_prediction(1, is_partial=True)
			else:
				self._accept_prediction(1)

	@scriptHandler.script(
		gesture="kb:NVDA+control+3",
	description="Accept word prediction 3",
		category=SCRIPT_CATEGORY
	)
	def script_acceptPrediction3(self, gesture):
		if self._enabled and (
			len(self._predictions) > 2 or len(self._partial_predictions) > 2
		):
			if self._partial_predictions:
				self._accept_prediction(2, is_partial=True)
			else:
				self._accept_prediction(2)

	@scriptHandler.script(
		gesture="kb:NVDA+control+4",
	description="Accept word prediction 4",
		category=SCRIPT_CATEGORY
	)
	def script_acceptPrediction4(self, gesture):
		if self._enabled and (
			len(self._predictions) > 3 or len(self._partial_predictions) > 3
		):
			if self._partial_predictions:
				self._accept_prediction(3, is_partial=True)
			else:
				self._accept_prediction(3)

	@scriptHandler.script(
		gesture="kb:NVDA+control+5",
	description="Accept word prediction 5",
		category=SCRIPT_CATEGORY
	)
	def script_acceptPrediction5(self, gesture):
		if self._enabled and (
			len(self._predictions) > 4 or len(self._partial_predictions) > 4
		):
			if self._partial_predictions:
				self._accept_prediction(4, is_partial=True)
			else:
				self._accept_prediction(4)

	@scriptHandler.script(
		gesture="kb:NVDA+control+6",
	description="Accept word prediction 6",
		category=SCRIPT_CATEGORY
	)
	def script_acceptPrediction6(self, gesture):
		if self._enabled and (
			len(self._predictions) > 5 or len(self._partial_predictions) > 5
		):
			if self._partial_predictions:
				self._accept_prediction(5, is_partial=True)
			else:
				self._accept_prediction(5)

	@scriptHandler.script(
		gesture="kb:NVDA+control+7",
	description="Accept word prediction 7",
		category=SCRIPT_CATEGORY
	)
	def script_acceptPrediction7(self, gesture):
		if self._enabled and (
			len(self._predictions) > 6 or len(self._partial_predictions) > 6
		):
			if self._partial_predictions:
				self._accept_prediction(6, is_partial=True)
			else:
				self._accept_prediction(6)

	@scriptHandler.script(
		gesture="kb:NVDA+control+8",
	description="Accept word prediction 8",
		category=SCRIPT_CATEGORY
	)
	def script_acceptPrediction8(self, gesture):
		if self._enabled and (
			len(self._predictions) > 7 or len(self._partial_predictions) > 7
		):
			if self._partial_predictions:
				self._accept_prediction(7, is_partial=True)
			else:
				self._accept_prediction(7)

	@scriptHandler.script(
		gesture="kb:NVDA+control+9",
	description="Accept word prediction 9",
		category=SCRIPT_CATEGORY
	)
	def script_acceptPrediction9(self, gesture):
		if self._enabled and (
			len(self._predictions) > 8 or len(self._partial_predictions) > 8
		):
			if self._partial_predictions:
				self._accept_prediction(8, is_partial=True)
			else:
				self._accept_prediction(8)

	@scriptHandler.script(
		gesture="kb:NVDA+control+0",
	description="Accept word prediction 10",
		category=SCRIPT_CATEGORY
	)
	def script_acceptPrediction10(self, gesture):
		if self._enabled and (
			len(self._predictions) > 9 or len(self._partial_predictions) > 9
		):
			if self._partial_predictions:
				self._accept_prediction(9, is_partial=True)
			else:
				self._accept_prediction(9)

	def event_typedCharacter(self, obj, nextHandler, ch):
		"""Track typed characters to build words and trigger predictions."""
		# Always let the character through first
		nextHandler()

		if not self._enabled:
			return

		# Don't predict in terminal applications
		if self._is_terminal():
			return

		if ch.isalpha() or ch == "'":
			# Building the current word (including apostrophes for contractions)
			self._current_word += ch.lower()
			self._chars_since_partial += 1

			# Clear full predictions when starting to type a new word
			if len(self._current_word) == 1:
				self._predictions = []

			# Check for partial-word predictions at intervals
			if (
				len(self._current_word) >= self.MIN_PARTIAL_LENGTH
				and self._chars_since_partial >= self.PARTIAL_PREDICTION_INTERVAL
			):
				self._chars_since_partial = 0
				self._partial_predictions = self._get_partial_predictions(
					self._current_word
				)
				# Don't auto-announce partials to avoid being too chatty
				# User can press NVDA+Shift+O to hear them on demand

		elif ch == " ":
			# Space completes the current word
			if self._current_word:
				word = self._current_word.lower()
				self._learn_from_word(word)
				self._current_word = ""
				self._partial_predictions = []

				# Get predictions for the next word
				self._predictions = self._get_predictions()

				if self._predictions:
					# Short beep to alert that predictions are available
					self._beep()
					# Announce predictions
					self._announce_predictions()
		else:
			# Punctuation or other character ends the current word
			if self._current_word:
				word = self._current_word.lower()
				self._learn_from_word(word)
				self._current_word = ""
				self._partial_predictions = []

				# Trigger predictions after punctuation too
				# (period, comma, etc. also end a word)
				self._predictions = self._get_predictions()

				if self._predictions:
					self._beep()
					self._announce_predictions()
			else:
				self._predictions = []
				self._partial_predictions = []

	def terminate(self):
		"""Save learning and unregister settings panel when NVDA exits."""
		self._save_ngrams()
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(SettingsPanel)
		super().terminate()