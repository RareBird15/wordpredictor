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


# ---------------------------------------------------------------------------
# KneserNeyModel: N-gram language model with Kneser-Ney smoothing
# ---------------------------------------------------------------------------
# Inlined directly in this file because NVDA's plugin loader scans every .py
# file in globalPlugins/ and tries to import it as a GlobalPlugin subclass.
# A separate helper module would cause "module has no attribute 'GlobalPlugin'"
# errors. Keeping everything in one file is the standard NVDA add-on pattern.
#
# When smoothing is enabled, predictions are ranked by interpolated KN
# probability instead of raw frequency. When disabled, falls back to the
# original behavior. Data format is backward compatible:
# {"bigrams": {...}, "trigrams": {...}}
# All derived statistics are computed at load time from the raw counts.


class KneserNeyModel:
	"""N-gram language model with optional Kneser-Ney smoothing.

	Stores bigram and trigram counts and computes derived statistics
	for Kneser-Ney interpolation. When smoothing is enabled, predictions
	are ranked by interpolated KN probability instead of raw frequency.
	When disabled, falls back to the original frequency-based ranking.

	Data format is backward compatible: {bigrams: {...}, trigrams: {...}}
	All derived statistics are computed at load time.
	"""

	# Discount constant for absolute discounting (standard value).
	# Values between 0.1 and 0.9 work; 0.75 is the most commonly used.
	D = 0.75

	def __init__(self, use_smoothing=True):
		self._bigrams = {}
		self._trigrams = {}
		self._use_smoothing = use_smoothing
		# Derived statistics (computed from raw counts)
		self._bigram_context_counts = {}    # {prev: total_count}
		self._bigram_context_types = {}     # {prev: num_distinct_next}
		self._trigram_context_counts = {}   # {key: total_count}
		self._trigram_context_types = {}    # {key: num_distinct_next}
		self._continuation_counts = {}      # {word: num_distinct_prev}
		self._total_bigram_types = 0
		self._unigram_candidates = []       # sorted [(word, count)]
		self._unigram_dirty = False

	def set_smoothing(self, enabled):
		"""Toggle Kneser-Ney smoothing on or off."""
		self._use_smoothing = enabled

	def load(self, bigrams, trigrams):
		"""Load raw n-gram counts and compute derived statistics."""
		self._bigrams = bigrams if bigrams else {}
		self._trigrams = trigrams if trigrams else {}
		self._compute_statistics()

	def _compute_statistics(self):
		"""Compute all derived statistics from raw n-gram counts.

		Called once at load time. After this, incremental updates
		happen in learn() to keep statistics consistent.
		"""
		self._bigram_context_counts = {}
		self._bigram_context_types = {}
		self._trigram_context_counts = {}
		self._trigram_context_types = {}
		self._continuation_counts = {}

		# Bigram context counts, types, and continuation counts
		for prev, nexts in self._bigrams.items():
			self._bigram_context_counts[prev] = sum(nexts.values())
			self._bigram_context_types[prev] = len(nexts)
			for word in nexts:
				self._continuation_counts[word] = self._continuation_counts.get(word, 0) + 1

		# Trigram context counts and types
		for key, nexts in self._trigrams.items():
			self._trigram_context_counts[key] = sum(nexts.values())
			self._trigram_context_types[key] = len(nexts)

		# Total distinct bigram types (N_{1+}(., .))
		self._total_bigram_types = sum(len(nexts) for nexts in self._bigrams.values())

		# Pre-sort unigram candidates by continuation count
		self._unigram_candidates = sorted(
			self._continuation_counts.items(),
			key=lambda x: x[1],
			reverse=True
		)
		self._unigram_dirty = False

	def learn(self, word, word_buffer):
		"""Update n-gram counts with a new word.

		Args:
			word: The word that was just completed (lowercase).
			word_buffer: List of last 2+ completed words (before this one).
			             The caller manages the buffer; this method does
			             NOT append to it.
		"""
		if not word:
			return

		# Update bigram: prev -> word
		if word_buffer:
			prev = word_buffer[-1]
			if prev not in self._bigrams:
				self._bigrams[prev] = {}
			is_new_pair = word not in self._bigrams[prev]
			if is_new_pair:
				self._bigrams[prev][word] = 0
				# New distinct bigram pair: update continuation count
				self._continuation_counts[word] = self._continuation_counts.get(word, 0) + 1
				# New distinct next word for this context
				self._bigram_context_types[prev] = self._bigram_context_types.get(prev, 0) + 1
				self._total_bigram_types += 1
				self._unigram_dirty = True
			self._bigrams[prev][word] += 1
			self._bigram_context_counts[prev] = self._bigram_context_counts.get(prev, 0) + 1

		# Update trigram: (word_buffer[-2], word_buffer[-1]) -> word
		if len(word_buffer) >= 2:
			key = f"{word_buffer[-2]} {word_buffer[-1]}"
			if key not in self._trigrams:
				self._trigrams[key] = {}
			is_new_triple = word not in self._trigrams[key]
			if is_new_triple:
				self._trigrams[key][word] = 0
				self._trigram_context_types[key] = self._trigram_context_types.get(key, 0) + 1
			self._trigrams[key][word] += 1
			self._trigram_context_counts[key] = self._trigram_context_counts.get(key, 0) + 1

	def predict(self, word_buffer, max_predictions=5):
		"""Get next-word predictions.

		Args:
			word_buffer: List of last 2+ completed words.
			max_predictions: Maximum number of predictions to return.

		Returns:
			List of predicted words, best first.
		"""
		if not self._bigrams:
			return []
		if self._use_smoothing:
			return self._predict_kn(word_buffer, max_predictions)
		return self._predict_frequency(word_buffer, max_predictions)

	def _predict_frequency(self, word_buffer, max_predictions=5):
		"""Original frequency-based prediction (backward compatible)."""
		predictions = []

		# Try trigram first (more context = better prediction)
		if len(word_buffer) >= 2:
			key = f"{word_buffer[-2]} {word_buffer[-1]}"
			if key in self._trigrams:
				sorted_preds = sorted(
					self._trigrams[key].items(),
					key=lambda x: x[1],
					reverse=True
				)
				predictions = [p[0] for p in sorted_preds[:max_predictions]]

		# Fall back to bigram if trigram didn't find enough
		if len(predictions) < max_predictions and word_buffer:
			last_word = word_buffer[-1]
			if last_word in self._bigrams:
				sorted_preds = sorted(
					self._bigrams[last_word].items(),
					key=lambda x: x[1],
					reverse=True
				)
				bigram_preds = [p[0] for p in sorted_preds[:max_predictions]]
				for p in bigram_preds:
					if p not in predictions:
						predictions.append(p)
						if len(predictions) >= max_predictions:
							break

		return predictions[:max_predictions]

	def _predict_kn(self, word_buffer, max_predictions=5):
		"""Kneser-Ney smoothed prediction.

		Gathers candidates from all three levels (trigram, bigram,
		unigram), scores each by interpolated KN probability, and
		returns the top N.
		"""
		# Refresh unigram candidates if dirty (new words learned)
		if self._unigram_dirty:
			self._unigram_candidates = sorted(
				self._continuation_counts.items(),
				key=lambda x: x[1],
				reverse=True
			)
			self._unigram_dirty = False

		# Gather candidates from all levels
		candidates = set()

		# Trigram candidates: words that follow the 2-word context
		if len(word_buffer) >= 2:
			key = f"{word_buffer[-2]} {word_buffer[-1]}"
			if key in self._trigrams:
				candidates.update(self._trigrams[key].keys())

		# Bigram candidates: words that follow the last word
		if word_buffer:
			prev = word_buffer[-1]
			if prev in self._bigrams:
				candidates.update(self._bigrams[prev].keys())

		# Unigram candidates: top words by continuation probability
		# These provide backoff for words not seen in the current context
		for word, _ in self._unigram_candidates[:max_predictions * 3]:
			candidates.add(word)

		if not candidates:
			return []

		# Score each candidate by interpolated KN probability
		scored = [(word, self._kn_probability(word, word_buffer)) for word in candidates]
		scored.sort(key=lambda x: x[1], reverse=True)

		return [word for word, _ in scored[:max_predictions]]

	def _kn_probability(self, word, word_buffer):
		"""Compute interpolated Kneser-Ney probability for a word.

		P(w | context) = max(count - D, 0) / context_count
		               + lambda * P_lower(w | shorter_context)

		The interpolation cascades: trigram -> bigram -> unigram.
		At each level, the discounted high-order probability is
		blended with the lower-order probability via lambda.
		"""
		# Trigram level
		if len(word_buffer) >= 2:
			key = f"{word_buffer[-2]} {word_buffer[-1]}"
			trigram_count = self._trigrams.get(key, {}).get(word, 0)
			context_count = self._trigram_context_counts.get(key, 0)
			context_types = self._trigram_context_types.get(key, 0)

			if context_count > 0:
				# Discounted trigram probability
				first_term = max(trigram_count - self.D, 0) / context_count
				# Interpolation weight: how much probability mass to
				# give to the lower-order (bigram) model
				lambda_val = (self.D / context_count) * context_types
				return first_term + lambda_val * self._bigram_kn(word, word_buffer[-1])

		# No trigram context: fall back to bigram level
		if word_buffer:
			return self._bigram_kn(word, word_buffer[-1])

		# No context at all: unigram only
		return self._unigram_kn(word)

	def _bigram_kn(self, word, prev_word):
		"""KN probability at the bigram level.

		P(w | prev) = max(count(prev, w) - D, 0) / count(prev)
		           + lambda(prev) * P_unigram(w)
		"""
		bigram_count = self._bigrams.get(prev_word, {}).get(word, 0)
		context_count = self._bigram_context_counts.get(prev_word, 0)
		context_types = self._bigram_context_types.get(prev_word, 0)

		if context_count > 0:
			first_term = max(bigram_count - self.D, 0) / context_count
			lambda_val = (self.D / context_count) * context_types
			return first_term + lambda_val * self._unigram_kn(word)

		# No bigram context: unigram only
		return self._unigram_kn(word)

	def _unigram_kn(self, word):
		"""KN continuation probability at the unigram level.

		Instead of raw word frequency, uses continuation probability:
		how many distinct contexts does this word appear in?

		P(w) = |{prev : (prev, w) seen at least once}| / total_bigram_types

		This rewards words that appear in many different contexts
		(like "the", "is", "and") over words that appear frequently
		but only in specific phrases (like "York" after "New").
		"""
		if self._total_bigram_types == 0:
			return 0.0
		return self._continuation_counts.get(word, 0) / self._total_bigram_types

	def predict_partial(self, partial, word_buffer, max_predictions=5):
		"""Get partial-word predictions.

		Args:
			partial: The partially typed word (at least 2 characters).
			word_buffer: List of last 2+ completed words.
			max_predictions: Maximum number of predictions to return.

		Returns:
			List of predicted completions, best first.
		"""
		if not partial or len(partial) < 2 or not self._bigrams:
			return []
		if self._use_smoothing:
			return self._predict_partial_kn(partial, word_buffer, max_predictions)
		return self._predict_partial_frequency(partial, word_buffer, max_predictions)

	def _predict_partial_frequency(self, partial, word_buffer, max_predictions=5):
		"""Original frequency-based partial prediction (backward compatible)."""
		partial_lower = partial.lower()
		matching = []

		# Gather from trigrams first
		if len(word_buffer) >= 2:
			key = f"{word_buffer[-2]} {word_buffer[-1]}"
			if key in self._trigrams:
				for word, count in self._trigrams[key].items():
					if word.startswith(partial_lower) and word not in matching:
						matching.append((word, count))

		# Then from bigrams
		if word_buffer:
			last_word = word_buffer[-1]
			if last_word in self._bigrams:
				for word, count in self._bigrams[last_word].items():
					if word.startswith(partial_lower):
						already = any(w == word for w, _ in matching)
						if not already:
							matching.append((word, count))

		# Global bigram scan as fallback for words that might follow
		# any word and start with the partial
		if len(matching) < 3:
			for prev_word, nexts in self._bigrams.items():
				for word, count in nexts.items():
					if word.startswith(partial_lower):
						already = any(w == word for w, _ in matching)
						if not already:
							matching.append((word, count))
				if len(matching) >= 10:
					break

		matching.sort(key=lambda x: x[1], reverse=True)
		return [w for w, _ in matching[:max_predictions]]

	def _predict_partial_kn(self, partial, word_buffer, max_predictions=5):
		"""KN-smoothed partial-word prediction.

		Same candidate gathering as frequency mode, but ranks by
		KN probability instead of raw count. This means a word that
		starts with the partial AND fits the context well will rank
		higher than a more frequent word that doesn't fit the context.
		"""
		partial_lower = partial.lower()
		candidates = set()

		# Gather candidates that start with the partial
		if len(word_buffer) >= 2:
			key = f"{word_buffer[-2]} {word_buffer[-1]}"
			if key in self._trigrams:
				for word in self._trigrams[key]:
					if word.startswith(partial_lower):
						candidates.add(word)

		if word_buffer:
			prev = word_buffer[-1]
			if prev in self._bigrams:
				for word in self._bigrams[prev]:
					if word.startswith(partial_lower):
						candidates.add(word)

		# Global bigram scan as fallback
		if len(candidates) < 3:
			for prev_word, nexts in self._bigrams.items():
				for word in nexts:
					if word.startswith(partial_lower):
						candidates.add(word)
				if len(candidates) >= 10:
					break

		if not candidates:
			return []

		# Score by KN probability
		scored = [(word, self._kn_probability(word, word_buffer)) for word in candidates]
		scored.sort(key=lambda x: x[1], reverse=True)

		return [word for word, _ in scored[:max_predictions]]

	def to_dict(self):
		"""Serialize raw counts for persistence.

		Format is identical to the original: {"bigrams": {...}, "trigrams": {...}}
		Derived statistics are NOT saved; they are recomputed at load time.
		"""
		return {"bigrams": self._bigrams, "trigrams": self._trigrams}

	@property
	def bigrams(self):
		"""Direct access to bigram data (for backward compatibility)."""
		return self._bigrams

	@property
	def trigrams(self):
		"""Direct access to trigram data (for backward compatibility)."""
		return self._trigrams

	@property
	def has_data(self):
		"""True if the model has any n-gram data loaded."""
		return bool(self._bigrams)


# ---------------------------------------------------------------------------
# End KneserNeyModel
# ---------------------------------------------------------------------------

# Configuration key for the add-on
CONFIG_KEY = "wordPredictor"
DEFAULT_CONFIG = {
	"enabled": True,
	"maxPredictions": 5,
	"beepBeforePredictions": True,
	"learningEnabled": True,
	"disableInTerminals": True,
	"disabledApps": "",
	"useSmoothing": True,
}

# Script category for NVDA Input Gestures dialog
SCRIPT_CATEGORY = "Word Predictor"

# Delay (ms) before typing accepted prediction, to allow modifier
# keys to be released. Without this, characters sent while Ctrl is
# still held trigger application shortcuts (Ctrl+H, Ctrl+S, etc.).
TYPE_DELAY_MS = 100

# Punctuation that ends a sentence (capitalize next word + leading space)
SENTENCE_ENDING_PUNCT = frozenset(".!?")

# Punctuation that ends a clause (leading space only, no capitalization)
CLAUSE_ENDING_PUNCT = frozenset(",;:")

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

	@staticmethod
	def _to_bool(val, default=True):
		if isinstance(val, bool):
			return val
		if isinstance(val, str):
			return val.lower() in ("true", "1", "yes")
		return default

	@staticmethod
	def _to_int(val, default=5):
		try:
			return int(val)
		except (TypeError, ValueError):
			return default

	def makeSettings(self, sizer):
		"""Create the settings controls."""
		settings = config.conf[CONFIG_KEY]

		# Enable/disable checkbox
		self.enabledCheckbox = wx.CheckBox(self, label="Enable word prediction")
		self.enabledCheckbox.SetValue(self._to_bool(settings.get("enabled", True)))
		sizer.Add(self.enabledCheckbox, border=10, flag=wx.BOTTOM)

		# Number of predictions
		sizer.Add(wx.StaticText(self, label="Number of predictions (1-10):"), border=10, flag=wx.TOP | wx.BOTTOM)
		self.predictionsSpinner = wx.SpinCtrl(self, min=1, max=10, value=str(self._to_int(settings.get("maxPredictions", 5))))
		sizer.Add(self.predictionsSpinner, border=10, flag=wx.BOTTOM)

		# Beep before predictions
		self.beepCheckbox = wx.CheckBox(self, label="Play beep before announcing predictions")
		self.beepCheckbox.SetValue(self._to_bool(settings.get("beepBeforePredictions", True)))
		sizer.Add(self.beepCheckbox, border=10, flag=wx.BOTTOM)

		# Learning enabled
		self.learningCheckbox = wx.CheckBox(self, label="Learn from my writing")
		self.learningCheckbox.SetValue(self._to_bool(settings.get("learningEnabled", True)))
		sizer.Add(self.learningCheckbox, border=10, flag=wx.BOTTOM)

		# Kneser-Ney smoothing
		self.smoothingCheckbox = wx.CheckBox(self, label="Use Kneser-Ney smoothing (better predictions, same speed)")
		self.smoothingCheckbox.SetValue(self._to_bool(settings.get("useSmoothing", True)))
		sizer.Add(self.smoothingCheckbox, border=10, flag=wx.BOTTOM)

		# Disable in terminals
		self.terminalCheckbox = wx.CheckBox(self, label="Disable in terminal applications")
		self.terminalCheckbox.SetValue(self._to_bool(settings.get("disableInTerminals", True)))
		sizer.Add(self.terminalCheckbox, border=10, flag=wx.BOTTOM)

		# Custom app exclusion list
		sizer.Add(wx.StaticText(self, label="Disable prediction in these applications:"), border=10, flag=wx.TOP | wx.BOTTOM)
		sizer.Add(wx.StaticText(self, label="Enter one app name per line (e.g. vipmud, mushclient). Names are case-insensitive."), border=5, flag=wx.BOTTOM)
		self.disabledAppsText = wx.TextCtrl(
			self,
			value=str(settings.get("disabledApps", "")),
			style=wx.TE_MULTILINE | wx.TE_PROCESS_ENTER,
			size=(400, 100),
		)
		sizer.Add(self.disabledAppsText, border=10, flag=wx.EXPAND | wx.BOTTOM)

	def onSave(self):
		"""Save settings when the user clicks OK or Apply."""
		settings = config.conf[CONFIG_KEY]
		settings["enabled"] = self.enabledCheckbox.IsChecked()
		settings["maxPredictions"] = int(self.predictionsSpinner.GetValue())
		settings["beepBeforePredictions"] = self.beepCheckbox.IsChecked()
		settings["learningEnabled"] = self.learningCheckbox.IsChecked()
		settings["useSmoothing"] = self.smoothingCheckbox.IsChecked()
		settings["disableInTerminals"] = self.terminalCheckbox.IsChecked()
		settings["disabledApps"] = self.disabledAppsText.GetValue()

		# Apply settings to the running plugin
		if SettingsPanel._plugin:
			SettingsPanel._plugin._enabled = self._to_bool(settings.get("enabled", True))
			SettingsPanel._plugin._max_predictions = self._to_int(settings.get("maxPredictions", 5))
			SettingsPanel._plugin._beep_enabled = self._to_bool(settings.get("beepBeforePredictions", True))
			SettingsPanel._plugin._learning_enabled = self._to_bool(settings.get("learningEnabled", True))
			SettingsPanel._plugin._model.set_smoothing(self._to_bool(settings.get("useSmoothing", True)))
			SettingsPanel._plugin._disable_in_terminals = self._to_bool(settings.get("disableInTerminals", True))
			SettingsPanel._plugin._disabled_app_names = SettingsPanel._plugin._parse_disabled_apps(
				settings.get("disabledApps", "")
			)

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
		self._disabled_app_names = self._parse_disabled_apps(
			settings.get("disabledApps", "")
		)
		self._terminal_cache = {}  # Cache for terminal/disabled app detection
		self._model = KneserNeyModel(
			use_smoothing=to_bool(settings.get("useSmoothing", True))
		)
		self._save_lock = threading.Lock()
		self._dirty = False  # True when n-grams have been modified
		self._chars_since_partial = 0  # Characters typed since last partial prediction
		self._last_ending_char = None  # Last punctuation that ended a word (for spacing/capitalization)
		# Register settings panel with NVDA
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(SettingsPanel)
		# Load n-grams
		self._load_ngrams()

	def _is_edit_field(self):
		"""Check if the currently focused object is an editable text field.

		NVDA assigns ROLE_EDITABLETEXT to edit fields, document areas,
		and other text input controls. This catches standard edit fields,
		rich text editors, document content areas, and most text inputs.

		For browse mode documents (web pages, emails), NVDA uses a
		virtual buffer with its own editable text role, so predictions
		will work in those contexts too.

		Returns True if the focused object is an editable text field.
		"""
		try:
			obj = api.getFocusObject()
			if not obj:
				return False
			from controlTypes import Role
			if obj.role == Role.EDITABLETEXT:
				return True
			# Also check the tree interceptor (browse mode documents like
			# web pages and emails where you can type in text areas)
			ti = obj.treeInterceptor
			if ti and hasattr(ti, 'role') and ti.role == Role.EDITABLETEXT:
				return True
			return False
		except Exception:
			return False

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

	@staticmethod
	def _parse_disabled_apps(raw):
		"""Parse the user's disabled-apps text into a frozenset of names.

		Accepts one app name per line. Names are lowercased and stripped.
		Blank lines and comment lines (starting with #) are ignored.
		"""
		if not raw or not isinstance(raw, str):
			return frozenset()
		names = set()
		for line in raw.strip().splitlines():
			line = line.strip().lower()
			if line and not line.startswith("#"):
				names.add(line)
		return frozenset(names)

	def _should_disable(self):
		"""Check if prediction should be disabled in the current app.

		Returns True if the focused app is a terminal (and terminal
		detection is on) OR if it's in the user's custom exclusion list.
		"""
		if self._is_terminal():
			return True
		return self._is_user_disabled_app()

	def _is_user_disabled_app(self):
		"""Check if the focused app is in the user's custom exclusion list.

		Uses the same app-name cache as terminal detection. Returns
		True if the app matches one of the names the user entered in
		Settings > Word Predictor > "Disable prediction in these apps".
		"""
		if not self._disabled_app_names:
			return False
		try:
			obj = api.getFocusObject()
			if not obj or not obj.appModule:
				return False
			app_name = obj.appModule.appName
			if not isinstance(app_name, str):
				return False
			app_name = app_name.lower()
			# Reuse the terminal cache since both check the same app
			cached = self._terminal_cache.get(app_name)
			if cached is not None:
				# Cache stores terminal result; check user list separately
				# but still benefit from knowing the app name
				pass
			return app_name in self._disabled_app_names
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
				self._model.load(
					data.get("bigrams", {}),
					data.get("trigrams", {})
				)
				return
		except Exception:
			pass

		# Fall back to bundled data file
		try:
			with open(self.BUNDLED_DATA_FILE, "r", encoding="utf-8") as f:
				data = json.load(f)
			self._model.load(
				data.get("bigrams", {}),
				data.get("trigrams", {})
			)
		except Exception:
			self._model.load({}, {})

	def _save_ngrams(self):
		"""Save n-gram data to the learned file in NVDA's user config."""
		if not self._dirty:
			return

		try:
			with self._save_lock:
				data = self._model.to_dict()
				with open(self._learned_data_file, "w", encoding="utf-8") as f:
					json.dump(data, f)
				self._dirty = False
		except Exception:
			# Don't crash NVDA if saving fails
			pass

	def _get_predictions(self):
		"""Get word predictions based on the current word buffer."""
		return self._model.predict(self._word_buffer, self._max_predictions)

	def _get_partial_predictions(self, partial):
		"""Get predictions for a partially typed word.

		Delegates to the model, which uses KN-smoothed probability
		when smoothing is enabled, or frequency-based ranking otherwise.
		"""
		return self._model.predict_partial(
			partial, self._word_buffer, self._max_predictions
		)

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

		# Delegate to the model, which updates both raw counts and
		# derived statistics (continuation counts, context types)
		# incrementally.
		self._model.learn(word, self._word_buffer)

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

		# Determine if we need a leading space and/or capitalization
		# based on what punctuation ended the previous word.
		need_leading_space = False
		capitalize = False

		if not is_partial and self._last_ending_char:
			if self._last_ending_char in SENTENCE_ENDING_PUNCT:
				# After . ! ? : add space + capitalize
				need_leading_space = True
				capitalize = True
			elif self._last_ending_char in CLAUSE_ENDING_PUNCT:
				# After , ; : : add space, no capitalization
				need_leading_space = True

		# Apply capitalization for sentence start
		if capitalize and word:
			word = word[0].upper() + word[1:]

		# For partial predictions, only type the remaining characters
		if is_partial and self._current_word:
			chars_to_type = word[len(self._current_word):]
		else:
			chars_to_type = word

		# Build the full sequence to type (leading space + word chars)
		if need_leading_space and not is_partial:
			chars_to_type = " " + chars_to_type

		word_to_learn = word.lower()

		# Clear state immediately so duplicate accepts don't fire
		self._current_word = ""
		self._predictions = []
		self._partial_predictions = []

		# Defer typing until Control is physically released.
		# The prediction gesture includes NVDA+Control, so Control is
		# physically held when the script fires. We poll for its release
		# using getAsyncKeyState (physical keyboard state) and only type
		# once it's up. This avoids all the problems of manually
		# injecting key-up events (which can get intercepted by NVDA,
		# corrupt modifier tracking, or get stuck).
		def _do_type(retry_count=0):
			import keyboardHandler
			import winUser

			# Check if Control is still physically held
			if winUser.getAsyncKeyState(winUser.VK_CONTROL) & 0x8000:
				# Retry up to 20 times (50ms each = ~1 second total)
				if retry_count < 20:
					wx.CallLater(50, lambda: _do_type(retry_count + 1))
					return
				else:
					# Timeout: Control still held after 1 second
					ui.message("Unable to insert prediction")
					return

			# Control is released — type the characters normally
			for char in chars_to_type:
				if char.isupper():
					keyboardHandler.KeyboardInputGesture.fromName(
						f"shift+{char.lower()}"
					).send()
				else:
					keyboardHandler.KeyboardInputGesture.fromName(char).send()
			# Add a space after the word
			keyboardHandler.KeyboardInputGesture.fromName("space").send()

			# Learn from the accepted word
			self._learn_from_word(word_to_learn)
			# Announce what was inserted
			ui.message(f"Inserted: {word}")

		wx.CallLater(TYPE_DELAY_MS, _do_type)

	@scriptHandler.script(
		gesture="kb:NVDA+alt+p",
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
		gesture="kb:NVDA+alt+l",
		description="Save learned word prediction data to disk",
		category=SCRIPT_CATEGORY
	)
	def script_saveLearning(self, gesture):
		self._save_ngrams()
		ui.message("Word prediction learning saved")

	@scriptHandler.script(
		gesture="kb:NVDA+alt+o",
		description="Request word predictions on demand",
		category=SCRIPT_CATEGORY
	)
	def script_onDemandPrediction(self, gesture):
		"""Request predictions manually without waiting for space."""
		if not self._enabled:
			return

		# Don't predict in terminal or user-excluded applications
		if self._should_disable():
			return

		# Only predict when focused on an editable text field
		if not self._is_edit_field():
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

		# Don't predict in terminal or user-excluded applications
		if self._should_disable():
			return

		# Only predict when focused on an editable text field
		if not self._is_edit_field():
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
				# User can press NVDA+Alt+O to hear them on demand

		elif ch == " ":
			# Space completes the current word
			if self._current_word:
				word = self._current_word.lower()
				self._learn_from_word(word)
				self._current_word = ""
				self._partial_predictions = []
				self._last_ending_char = None  # Space already provides separation

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
				self._last_ending_char = ch  # Remember for spacing/capitalization

				# Trigger predictions after punctuation too
				# (period, comma, etc. also end a word)
				self._predictions = self._get_predictions()

				if self._predictions:
					self._beep()
					self._announce_predictions()
			else:
				self._predictions = []
				self._partial_predictions = []
				# Track punctuation even if no word was being typed
				# (e.g., user typed ". " then more punctuation)
				if ch in SENTENCE_ENDING_PUNCT or ch in CLAUSE_ENDING_PUNCT:
					self._last_ending_char = ch

	def terminate(self):
		"""Save learning and unregister settings panel when NVDA exits."""
		self._save_ngrams()
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(SettingsPanel)
		super().terminate()