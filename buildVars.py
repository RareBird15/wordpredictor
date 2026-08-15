# Build customizations
# Change this file instead of sconstruct or manifest files, whenever possible.

from site_scons.site_tools.NVDATool.typings import AddonInfo, BrailleTables, SymbolDictionaries, SpeechDictionaries

# Since some strings in `addon_info` are translatable,
# we need to include them in the .po files.
# Gettext recognizes only strings given as parameters to the `_` function.
# To avoid initializing translations in this module we simply import a "fake" `_` function
# which returns whatever is given to it as an argument.
from site_scons.site_tools.NVDATool.utils import _


# Add-on information variables
addon_info = AddonInfo(
	# add-on Name/identifier, internal for NVDA
	addon_name="wordPredictor",
	# Add-on summary/title, usually the user visible name of the add-on
	# Translators: Summary/title for this add-on
	# to be shown on installation and add-on information found in add-on store
	addon_summary=_("Word Predictor"),
	# Add-on description
	# Translators: Long description to be shown for this add-on on add-on information from add-on store
	addon_description=_("""Watches what you type and predicts the next word using n-gram analysis with Kneser-Ney smoothing. Predictions are announced through NVDA's speech engine and can be accepted with NVDA+Control+number keys (1 through 0). Learns from your writing over time. Includes partial-word prediction and terminal auto-detection and a custom app exclusion list and a settings panel."""),
	# version
	addon_version="1.7.1",
	# Brief changelog for this version
	# Translators: what's new content for the add-on version to be shown in the add-on store
	addon_changelog=_("""Added a setting to silence automatic predictions while keeping on-demand predictions (NVDA+Alt+O) and the numbered acceptance keys working. Useful for users who find constant beeping and speech distracting and only want predictions when they ask for them."""),
	# Author(s)
	addon_author="Lanie Carmelo-Molinar <lanie@lanie.work>",
	# URL for the add-on documentation support
	addon_url="https://github.com/RareBird15/wordPredictor",
	# URL for the add-on repository where the source code can be found
	addon_sourceURL="https://github.com/RareBird15/wordPredictor",
	# Documentation file name
	addon_docFileName="readme.html",
	# Minimum NVDA version supported
	addon_minimumNVDAVersion="2026.1",
	# Last NVDA version supported/tested
	addon_lastTestedNVDAVersion="2026.1",
	# Add-on update channel (default is None, denoting stable releases)
	addon_updateChannel=None,
	# Add-on license such as GPL 2
	addon_license="GPL v2",
	# URL for the license document the add-on is licensed under
	addon_licenseURL=None,
)

# Define the python files that are the sources of your add-on.
pythonSources: list[str] = ["addon/globalPlugins/*.py"]

# Files that contain strings for translation. Usually your python sources
i18nSources: list[str] = pythonSources + ["buildVars.py"]

# Files that will be ignored when building the nvda-addon file
# Paths are relative to the addon directory, not to the root directory of your addon sources.
excludedFiles: list[str] = []

# Base language for the NVDA add-on
baseLanguage: str = "en"

# Markdown extensions for add-on documentation
markdownExtensions: list[str] = []

# Custom braille translation tables
brailleTables: BrailleTables = {}

# Custom speech symbol dictionaries
symbolDictionaries: SymbolDictionaries = {}

# Custom speech dictionaries
speechDictionaries: SpeechDictionaries = {}
