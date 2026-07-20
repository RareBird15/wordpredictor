# WordPredictor - NVDA add-on for proactive word prediction
# Author: Lanie Carmelo-Molinar
# License: GPL v2
#
# A global plugin that watches what you type, predicts the next word
# using n-gram analysis, and announces predictions through NVDA's
# speech engine. Designed for screen reader users, by a screen reader user.

import globalPluginHandler
import scriptHandler
import ui
import tones
import os
import json


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""Global plugin that provides proactive word prediction for NVDA users."""

	DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "ngrams.json")

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self._enabled = True
		self._word_buffer = []  # Last 3 completed words
		self._current_word = ""  # Word currently being typed
		self._predictions = []  # Current list of predictions
		self._max_predictions = 5
		self._learning_enabled = True
		self._bigrams = {}
		self._trigrams = {}
		self._load_ngrams()

	def _load_ngrams(self):
		"""Load n-gram data from the JSON file."""
		try:
			with open(self.DATA_FILE, "r", encoding="utf-8") as f:
				data = json.load(f)
			self._bigrams = data.get("bigrams", {})
			self._trigrams = data.get("trigrams", {})
		except Exception:
			self._bigrams = {}
			self._trigrams = {}

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

	def _announce_predictions(self):
		"""Announce the current predictions through NVDA speech."""
		if not self._enabled or not self._predictions:
			return

		# Format: "Predictions: 1: word, 2: word, 3: word"
		parts = []
		for i, word in enumerate(self._predictions):
			parts.append(f"{i + 1}: {word}")
		ui.message("Predictions: " + ", ".join(parts))

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

	def _accept_prediction(self, index):
		"""Insert a predicted word into the current text field."""
		if index < 0 or index >= len(self._predictions):
			return

		word = self._predictions[index]

		# Insert the word by sending keystrokes
		import keyboardHandler
		for char in word:
			keyboardHandler.KeyboardInputGesture.fromName(f"kb:{char}").send()
		# Add a space after the word
		keyboardHandler.KeyboardInputGesture.fromName("kb:space").send()

		# Learn from the accepted word
		self._learn_from_word(word)

		# Clear current predictions
		self._predictions = []

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
			self._current_word = ""

	@scriptHandler.script(
		gesture="kb:control+NVDA+1",
		description="Accept word prediction 1"
	)
	def script_acceptPrediction1(self, gesture):
		self._accept_prediction(0)

	@scriptHandler.script(
		gesture="kb:control+NVDA+2",
		description="Accept word prediction 2"
	)
	def script_acceptPrediction2(self, gesture):
		self._accept_prediction(1)

	@scriptHandler.script(
		gesture="kb:control+NVDA+3",
		description="Accept word prediction 3"
	)
	def script_acceptPrediction3(self, gesture):
		self._accept_prediction(2)

	@scriptHandler.script(
		gesture="kb:control+NVDA+4",
		description="Accept word prediction 4"
	)
	def script_acceptPrediction4(self, gesture):
		self._accept_prediction(3)

	@scriptHandler.script(
		gesture="kb:control+NVDA+5",
		description="Accept word prediction 5"
	)
	def script_acceptPrediction5(self, gesture):
		self._accept_prediction(4)

	def event_typedCharacter(self, obj, nextHandler, ch):
		"""Track typed characters to build words and trigger predictions."""
		# Always let the character through first
		nextHandler()

		if not self._enabled:
			return

		if ch.isalpha():
			# Building the current word
			self._current_word += ch.lower()
		elif ch == " ":
			# Space completes the current word
			if self._current_word:
				word = self._current_word.lower()
				self._learn_from_word(word)
				self._current_word = ""

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