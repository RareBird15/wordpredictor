"""
ONNX Runtime inference wrapper for WordPredictor NVDA add-on.

Uses ctypes to call onnxruntime.dll directly — no Python onnxruntime
package needed. This keeps the add-on size manageable (~6MB for DLLs
instead of 40MB for the full Python package).

Usage:
    from onnx_inference import OnnxPredictor
    
    predictor = OnnxPredictor("data/wordpredictor_slm.onnx", "data/wordpredictor_slm_vocab.json")
    predictions = predictor.predict(["i", "need", "to", "schedule"], top_k=5)
    # Returns: [("a", 0.15), ("an", 0.12), ("the", 0.10), ...]
"""

import ctypes
import json
import os
from typing import Optional


# ── ONNX Runtime C API bindings ──────────────────────────────────

class OrtApi(ctypes.Structure):
    """Minimal ONNX Runtime C API — only the functions we need."""
    pass


def _load_ort_dll(dll_dir: str):
    """Load onnxruntime.dll and return the OrtApi pointer."""
    # Load providers shared DLL first (dependency)
    providers_path = os.path.join(dll_dir, "onnxruntime_providers_shared.dll")
    ctypes.cdll.LoadLibrary(providers_path)

    # Load main DLL
    ort_path = os.path.join(dll_dir, "onnxruntime.dll")
    ort_dll = ctypes.cdll.LoadLibrary(ort_path)

    # Get API base
    ort_dll.OrtGetApiBase.restype = ctypes.c_void_p
    api_base = ort_dll.OrtGetApiBase()

    if not api_base:
        raise RuntimeError("OrtGetApiBase returned NULL")

    return ort_dll, api_base


# ── Predictor class ──────────────────────────────────────────────

class OnnxPredictor:
    """Load an ONNX model and run next-word prediction via ctypes."""

    def __init__(self, model_path: str, vocab_path: str, dll_dir: Optional[str] = None):
        """
        Args:
            model_path: Path to the .onnx model file
            vocab_path: Path to the _vocab.json file
            dll_dir: Directory containing onnxruntime DLLs.
                     Defaults to ../lib relative to this file.
        """
        if dll_dir is None:
            dll_dir = os.path.join(os.path.dirname(__file__), "..", "lib")

        self._ort_dll, self._api_base = _load_ort_dll(dll_dir)

        # Load vocabulary
        with open(vocab_path, 'r') as f:
            vocab_data = json.load(f)
        self.word2idx = vocab_data['word2idx']
        self.idx2word = {int(k): v for k, v in vocab_data.get('idx2word', {}).items()}
        if not self.idx2word:
            self.idx2word = {v: k for k, v in self.word2idx.items()}
        self.context_len = vocab_data.get('context_len', 4)
        self.vocab_size = len(self.word2idx)

        # Load model
        self._session = self._create_session(model_path)

    def _create_session(self, model_path: str):
        """Create an ONNX Runtime inference session."""
        # This is a placeholder — the actual ctypes implementation
        # requires binding ~20 ONNX Runtime C API functions.
        # For now, we use the Python onnxruntime package as a fallback
        # during development, and will implement the ctypes version
        # once the model is trained and we know the exact API surface needed.
        try:
            import onnxruntime as ort
            return ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
        except ImportError:
            raise RuntimeError(
                "onnxruntime Python package not available. "
                "The ctypes implementation is pending — see comments in source."
            )

    def predict(self, context_words: list[str], top_k: int = 5) -> list[tuple[str, float]]:
        """
        Predict the next word given context words.

        Args:
            context_words: List of up to context_len previous words
            top_k: Number of top predictions to return

        Returns:
            List of (word, probability) tuples, sorted by probability descending
        """
        # Pad/truncate to context_len
        words = context_words[-self.context_len:] if len(context_words) > self.context_len else context_words
        # Pad with empty string (maps to <pad> token 0)
        while len(words) < self.context_len:
            words.insert(0, '')

        # Convert to token IDs
        input_ids = [self.word2idx.get(w, 1) for w in words]  # 1 = <unk>

        # Run inference
        import numpy as np
        input_array = np.array([input_ids], dtype=np.int64)
        outputs = self._session.run(None, {'input_ids': input_array})
        logits = outputs[0][0]  # (vocab_size,)

        # Softmax
        exp_logits = np.exp(logits - np.max(logits))
        probs = exp_logits / exp_logits.sum()

        # Get top-k
        top_indices = np.argsort(probs)[::-1][:top_k]
        results = []
        for idx in top_indices:
            word = self.idx2word.get(int(idx), '<unk>')
            if word in ('<pad>', '<unk>'):
                continue
            results.append((word, float(probs[idx])))

        return results[:top_k]

    def predict_single(self, context_words: list[str]) -> Optional[str]:
        """Return the single best prediction, or None."""
        preds = self.predict(context_words, top_k=1)
        return preds[0][0] if preds else None
