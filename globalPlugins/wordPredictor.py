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

import globalPluginHandler
import scriptHandler
import ui
import tones
import os
import json
import config
import threading


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
		self._enabled = True
		self._word_buffer = []  # Last 3 completed words
		self._current_word = ""  # Word currently being typed
		self._predictions = []  # Current list of predictions
		self._partial_predictions = []  # Predictions for partial word
		self._max_predictions = 5
		self._learning_enabled = True
		self._bigrams = {}
		self._trigrams = {}
		self._save_lock = threading.Lock()
		self._dirty = False  # True when n-grams have been modified
		self._chars_since_partial = 0  # Characters typed since last partial prediction
		self._load_ngrams()

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
		"""
		predictions = self._partial_predictions if is_partial else self._predictions
		if index < 0 or index >= len(predictions):
			return

		word = predictions[index]

		# For partial predictions, only type the remaining characters
		if is_partial and self._current_word:
			remaining = word[len(self._current_word):]
			chars_to_type = remaining
		else:
			chars_to_type = word

		# Insert the characters by sending keystrokes
		import keyboardHandler
		for char in chars_to_type:
			keyboardHandler.KeyboardInputGesture.fromName(char).send()
		# Add a space after the word
		keyboardHandler.KeyboardInputGesture.fromName("space").send()

		# Learn from the accepted word
		self._learn_from_word(word)

		# Clear current word and predictions
		self._current_word = ""
		self._predictions = []
		self._partial_predictions = []

		# Announce what was inserted
		ui.message(f"Inserted: {word}")

	@scriptHandler.script(
		gesture="kb:NVDA+shift+p",
		description="Toggle word prediction on or off"
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
		description="Save learned word prediction data to disk"
	)
	def script_saveLearning(self, gesture):
		self._save_ngrams()
		ui.message("Word prediction learning saved")

	@scriptHandler.script(
		gesture="kb:NVDA+shift+o",
		description="Request word predictions on demand"
	)
	def script_onDemandPrediction(self, gesture):
		"""Request predictions manually without waiting for space."""
		if not self._enabled:
			return

		# If we're in the middle of typing a word, get partial predictions
		if self._current_word and len(self._current_word) >= self.MIN_PARTIAL_LENGTH:
			self._partial_predictions = self._get_partial_predictions(self._current_word)
			if self._partial_predictions:
				self._predictions = []  # Clear full predictions
				tones.beep(660, 50)
				self._announce_partial_predictions()
			else:
				# No partial matches, try full predictions for the context
				self._predictions = self._get_predictions()
				if self._predictions:
					self._partial_predictions = []
					tones.beep(660, 50)
					self._announce_predictions()
				else:
					ui.message("No predictions available")
		else:
			# No current word, get full next-word predictions
			self._predictions = self._get_predictions()
			if self._predictions:
				self._partial_predictions = []
				tones.beep(660, 50)
				self._announce_predictions()
			else:
				ui.message("No predictions available")

	@scriptHandler.script(
		gesture="kb:1",
		description="Accept word prediction 1"
	)
	def script_acceptPrediction1(self, gesture):
		if self._enabled and (self._predictions or self._partial_predictions):
			if self._partial_predictions:
				self._accept_prediction(0, is_partial=True)
			else:
				self._accept_prediction(0)
		else:
			gesture.send()

	@scriptHandler.script(
		gesture="kb:2",
		description="Accept word prediction 2"
	)
	def script_acceptPrediction2(self, gesture):
		if self._enabled and (
			len(self._predictions) > 1 or len(self._partial_predictions) > 1
		):
			if self._partial_predictions:
				self._accept_prediction(1, is_partial=True)
			else:
				self._accept_prediction(1)
		else:
			gesture.send()

	@scriptHandler.script(
		gesture="kb:3",
		description="Accept word prediction 3"
	)
	def script_acceptPrediction3(self, gesture):
		if self._enabled and (
			len(self._predictions) > 2 or len(self._partial_predictions) > 2
		):
			if self._partial_predictions:
				self._accept_prediction(2, is_partial=True)
			else:
				self._accept_prediction(2)
		else:
			gesture.send()

	@scriptHandler.script(
		gesture="kb:4",
		description="Accept word prediction 4"
	)
	def script_acceptPrediction4(self, gesture):
		if self._enabled and (
			len(self._predictions) > 3 or len(self._partial_predictions) > 3
		):
			if self._partial_predictions:
				self._accept_prediction(3, is_partial=True)
			else:
				self._accept_prediction(3)
		else:
			gesture.send()

	@scriptHandler.script(
		gesture="kb:5",
		description="Accept word prediction 5"
	)
	def script_acceptPrediction5(self, gesture):
		if self._enabled and (
			len(self._predictions) > 4 or len(self._partial_predictions) > 4
		):
			if self._partial_predictions:
				self._accept_prediction(4, is_partial=True)
			else:
				self._accept_prediction(4)
		else:
			gesture.send()

	def event_typedCharacter(self, obj, nextHandler, ch):
		"""Track typed characters to build words and trigger predictions."""
		# Always let the character through first
		nextHandler()

		if not self._enabled:
			return

		if ch.isalpha():
			# Building the current word
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
					tones.beep(660, 50)
					# Announce predictions
					self._announce_predictions()
		else:
			# Punctuation or other character ends the current word
			# without triggering predictions
			if self._current_word:
				word = self._current_word.lower()
				self._learn_from_word(word)
				self._current_word = ""
			self._predictions = []
			self._partial_predictions = []

	def terminate(self):
		"""Save learning when NVDA exits or add-on is unloaded."""
		self._save_ngrams()
		super().terminate()