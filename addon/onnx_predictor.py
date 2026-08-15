"""
ONNX Runtime LSTM predictor for WordPredictor NVDA add-on.

Tries three paths in order:
1. Python onnxruntime package (pip install onnxruntime)
2. Bundled DLLs via ctypes (addon/lib/onnxruntime.dll)
3. Unavailable — n-gram model handles all predictions

Usage:
    from wordPredictor_lib.onnx_predictor import OnnxLstmPredictor
    
    predictor = OnnxLstmPredictor("data/model.onnx", "data/vocab.json", dll_dir="lib")
    if predictor.available:
        predictions = predictor.predict(["i", "need", "to", "schedule"], top_k=5)
"""

import ctypes
import json
import os
from ctypes import (
    POINTER, Structure, byref, c_char_p, c_float, c_int, c_longlong,
    c_size_t, c_void_p, c_uint32,
)
from typing import Optional


# ── ONNX Runtime C API constants ──────────────────────────────────

ORT_API_VERSION = 17

# OrtLoggingLevel
ORT_LOGGING_LEVEL_WARNING = 2

# ONNX tensor element data types
ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64 = 8
ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT = 1

# OrtMemType
OrtMemTypeDefault = 0

# OrtAllocatorType
OrtDeviceAllocator = 0

# Graph optimization level
ORT_DISABLE_ALL = 0


# ── Opaque struct types ──────────────────────────────────────────

class OrtEnv(Structure):
    pass

class OrtSession(Structure):
    pass

class OrtMemoryInfo(Structure):
    pass

class OrtValue(Structure):
    pass

class OrtStatus(Structure):
    pass

class OrtSessionOptions(Structure):
    pass

class OrtRunOptions(Structure):
    pass

class OrtAllocator(Structure):
    pass

class OrtApiBase(Structure):
    pass


# ── Function pointer types ───────────────────────────────────────

# OrtGetApiBase returns a pointer to OrtApiBase
# OrtApiBase.GetApi(version) returns a pointer to OrtApi (function table)
_OrtGetApiFunc = ctypes.CFUNCTYPE(c_void_p, c_void_p, c_uint32)

# Individual API function signatures
_OrtCreateEnvFunc = ctypes.CFUNCTYPE(c_void_p, c_int, c_char_p, c_void_p, POINTER(c_void_p))
_OrtCreateSessionFunc = ctypes.CFUNCTYPE(c_void_p, c_void_p, c_char_p, c_void_p, POINTER(c_void_p))
_OrtCreateSessionOptionsFunc = ctypes.CFUNCTYPE(c_void_p, POINTER(c_void_p))
_OrtSetSessionGraphOptimizationLevelFunc = ctypes.CFUNCTYPE(c_void_p, c_void_p, c_int)
_OrtCreateRunOptionsFunc = ctypes.CFUNCTYPE(c_void_p, POINTER(c_void_p))
_OrtCreateTensorWithDataAsOrtValueFunc = ctypes.CFUNCTYPE(
    c_void_p, c_void_p, c_void_p, c_size_t, POINTER(c_longlong),
    c_size_t, c_int, POINTER(c_void_p)
)
_OrtGetTensorMutableDataFunc = ctypes.CFUNCTYPE(c_void_p, c_void_p, POINTER(c_void_p))
_OrtRunFunc = ctypes.CFUNCTYPE(
    c_void_p, c_void_p, c_void_p,
    POINTER(c_char_p), POINTER(c_void_p), c_size_t,
    POINTER(c_char_p), c_size_t, POINTER(c_void_p)
)
_OrtReleaseStatusFunc = ctypes.CFUNCTYPE(None, c_void_p)
_OrtReleaseEnvFunc = ctypes.CFUNCTYPE(None, c_void_p)
_OrtReleaseSessionFunc = ctypes.CFUNCTYPE(None, c_void_p)
_OrtReleaseValueFunc = ctypes.CFUNCTYPE(None, c_void_p)
_OrtReleaseSessionOptionsFunc = ctypes.CFUNCTYPE(None, c_void_p)
_OrtReleaseRunOptionsFunc = ctypes.CFUNCTYPE(None, c_void_p)
_OrtReleaseMemoryInfoFunc = ctypes.CFUNCTYPE(None, c_void_p)
_OrtGetErrorMessageFunc = ctypes.CFUNCTYPE(c_char_p, c_void_p)
_OrtCreateCpuMemoryInfoFunc = ctypes.CFUNCTYPE(c_void_p, c_int, c_int, POINTER(c_void_p))


# ── OrtApi function indices (for API version 17) ─────────────────
# Source: onnxruntime/core/session/onnxruntime_c_api.h

_IDX_CreateEnv = 0
_IDX_CreateSession = 3
_IDX_CreateSessionOptions = 4
_IDX_SetSessionGraphOptimizationLevel = 6
_IDX_CreateRunOptions = 10
_IDX_CreateTensorWithDataAsOrtValue = 12
_IDX_GetTensorMutableData = 14
_IDX_Run = 17
_IDX_ReleaseStatus = 19
_IDX_ReleaseEnv = 20
_IDX_ReleaseSession = 21
_IDX_ReleaseValue = 22
_IDX_ReleaseSessionOptions = 24
_IDX_ReleaseRunOptions = 25
_IDX_GetErrorMessage = 27
_IDX_CreateCpuMemoryInfo = 30
_IDX_ReleaseMemoryInfo = 32


def _get_func(api_ptr, index, func_type):
    """Get a function pointer from the OrtApi by table index."""
    vtable = ctypes.cast(api_ptr, POINTER(POINTER(c_void_p))).contents
    func_ptr = ctypes.cast(vtable[index], c_void_p)
    return func_type(func_ptr.value)


# ── DLL loading ───────────────────────────────────────────────────

def _load_ort_dlls(dll_dir: str):
    """Load onnxruntime DLLs and return the OrtApi pointer."""
    # Load providers shared DLL first (dependency)
    providers_path = os.path.join(dll_dir, "onnxruntime_providers_shared.dll")
    if os.path.exists(providers_path):
        ctypes.cdll.LoadLibrary(providers_path)

    # Load main DLL
    ort_path = os.path.join(dll_dir, "onnxruntime.dll")
    ort_dll = ctypes.cdll.LoadLibrary(ort_path)

    # Get API base
    ort_dll.OrtGetApiBase.restype = c_void_p
    api_base_ptr = ort_dll.OrtGetApiBase()

    if not api_base_ptr:
        raise RuntimeError("OrtGetApiBase returned NULL")

    # Cast to OrtApiBase and call GetApi
    api_base = ctypes.cast(api_base_ptr, POINTER(OrtApiBase))
    vtable = ctypes.cast(
        api_base.contents,
        POINTER(POINTER(c_void_p))
    ).contents

    get_api = _OrtGetApiFunc(vtable[0])
    api_ptr = get_api(api_base, ORT_API_VERSION)

    if not api_ptr:
        raise RuntimeError(f"OrtApiBase.GetApi({ORT_API_VERSION}) returned NULL")

    return ort_dll, api_ptr


# ── Predictor class ───────────────────────────────────────────────

class OnnxLstmPredictor:
    """Load an ONNX LSTM model and run next-word prediction.

    Tries Python onnxruntime first, then ctypes DLL fallback.
    """

    def __init__(self, model_path: str, vocab_path: str, dll_dir: Optional[str] = None):
        self._model_path = model_path
        self._vocab_path = vocab_path
        self._session = None
        self._available = False
        self._use_ctypes = False
        self._ort_dll = None
        self._api_ptr = None
        self._ort_env = None
        self._ort_session = None
        self._ort_memory_info = None
        self.word2idx = {}
        self.idx2word = {}
        self.context_len = 4
        self.vocab_size = 0

        if dll_dir is None:
            dll_dir = os.path.join(os.path.dirname(__file__), "..", "..", "lib")

        # Load vocabulary (always available)
        try:
            with open(vocab_path, 'r') as f:
                vocab_data = json.load(f)
            self.word2idx = vocab_data['word2idx']
            self.idx2word = {int(k): v for k, v in vocab_data.get('idx2word', {}).items()}
            if not self.idx2word:
                self.idx2word = {v: k for k, v in self.word2idx.items()}
            self.context_len = vocab_data.get('context_len', 4)
            self.vocab_size = len(self.word2idx)
        except Exception:
            return

        # Path 1: Try Python onnxruntime package
        try:
            import onnxruntime as ort
            self._session = ort.InferenceSession(
                model_path, providers=['CPUExecutionProvider']
            )
            self._available = True
            return
        except ImportError:
            pass
        except Exception:
            pass

        # Path 2: Try ctypes with bundled DLLs
        try:
            self._ort_dll, self._api_ptr = _load_ort_dlls(dll_dir)
            self._init_ctypes_session(model_path)
            self._available = True
            self._use_ctypes = True
        except Exception:
            pass

    def _init_ctypes_session(self, model_path: str):
        """Create ONNX Runtime session using ctypes."""
        # Create environment
        env_ptr = c_void_p()
        create_env = _get_func(self._api_ptr, _IDX_CreateEnv, _OrtCreateEnvFunc)
        status = create_env(ORT_LOGGING_LEVEL_WARNING, b"WordPredictor", None, byref(env_ptr))
        self._check_status(status)
        self._ort_env = env_ptr

        # Create session options
        opts_ptr = c_void_p()
        create_opts = _get_func(self._api_ptr, _IDX_CreateSessionOptions, _OrtCreateSessionOptionsFunc)
        status = create_opts(byref(opts_ptr))
        self._check_status(status)

        # Disable graph optimizations for faster load
        set_opt = _get_func(self._api_ptr, _IDX_SetSessionGraphOptimizationLevel, _OrtSetSessionGraphOptimizationLevelFunc)
        status = set_opt(opts_ptr, ORT_DISABLE_ALL)
        self._check_status(status)

        # Create session
        session_ptr = c_void_p()
        create_session = _get_func(self._api_ptr, _IDX_CreateSession, _OrtCreateSessionFunc)
        model_path_bytes = model_path.encode('utf-8')
        status = create_session(env_ptr, model_path_bytes, opts_ptr, byref(session_ptr))
        self._check_status(status)
        self._ort_session = session_ptr

        # Release session options
        release_opts = _get_func(self._api_ptr, _IDX_ReleaseSessionOptions, _OrtReleaseSessionOptionsFunc)
        release_opts(opts_ptr)

        # Create CPU memory info
        mem_ptr = c_void_p()
        create_mem = _get_func(self._api_ptr, _IDX_CreateCpuMemoryInfo, _OrtCreateCpuMemoryInfoFunc)
        status = create_mem(OrtDeviceAllocator, OrtMemTypeDefault, byref(mem_ptr))
        self._check_status(status)
        self._ort_memory_info = mem_ptr

    def _check_status(self, status_ptr):
        """Check an OrtStatus pointer and raise on error."""
        if not status_ptr:
            return
        get_msg = _get_func(self._api_ptr, _IDX_GetErrorMessage, _OrtGetErrorMessageFunc)
        msg = get_msg(status_ptr)
        release_status = _get_func(self._api_ptr, _IDX_ReleaseStatus, _OrtReleaseStatusFunc)
        release_status(status_ptr)
        error_msg = msg.decode('utf-8') if msg else "Unknown ONNX Runtime error"
        raise RuntimeError(error_msg)

    @property
    def available(self) -> bool:
        """True if the ONNX model is loaded and ready for inference."""
        return self._available

    def predict(self, context_words: list[str], top_k: int = 5) -> list[tuple[str, float]]:
        """Predict the next word given context words."""
        if not self._available:
            return []

        import numpy as np

        # Pad/truncate to context_len
        words = context_words[-self.context_len:] if len(context_words) > self.context_len else context_words

        # Convert to token IDs. Pad with 0 (<pad>), unknown words map to 1 (<unk>).
        input_ids = [self.word2idx.get(w, 1) for w in words]
        while len(input_ids) < self.context_len:
            input_ids.insert(0, 0)  # 0 = <pad>

        if self._use_ctypes:
            return self._predict_ctypes(input_ids, top_k)
        else:
            return self._predict_python(input_ids, top_k)

    def _predict_python(self, input_ids: list[int], top_k: int) -> list[tuple[str, float]]:
        """Run prediction using Python onnxruntime."""
        import numpy as np
        input_array = np.array([input_ids], dtype=np.int64)
        outputs = self._session.run(None, {'input_ids': input_array})
        logits = outputs[0][0]

        exp_logits = np.exp(logits - np.max(logits))
        probs = exp_logits / exp_logits.sum()

        top_indices = np.argsort(probs)[::-1][:top_k]
        results = []
        for idx in top_indices:
            word = self.idx2word.get(int(idx), '<unk>')
            if word in ('<pad>', '<unk>'):
                continue
            results.append((word, float(probs[idx])))

        return results[:top_k]

    def _predict_ctypes(self, input_ids: list[int], top_k: int) -> list[tuple[str, float]]:
        """Run prediction using ctypes ONNX Runtime."""
        import numpy as np

        # Create input tensor
        input_array = np.array([input_ids], dtype=np.int64)
        input_shape = np.array([1, self.context_len], dtype=np.int64)

        input_tensor = c_void_p()
        create_tensor = _get_func(
            self._api_ptr, _IDX_CreateTensorWithDataAsOrtValue,
            _OrtCreateTensorWithDataAsOrtValueFunc
        )
        status = create_tensor(
            self._ort_memory_info,
            input_array.ctypes.data_as(c_void_p),
            input_array.nbytes,
            input_shape.ctypes.data_as(POINTER(c_longlong)),
            2,  # rank
            ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64,
            byref(input_tensor),
        )
        self._check_status(status)

        # Create run options
        run_opts = c_void_p()
        create_run_opts = _get_func(
            self._api_ptr, _IDX_CreateRunOptions, _OrtCreateRunOptionsFunc
        )
        status = create_run_opts(byref(run_opts))
        self._check_status(status)

        # Set up input/output
        input_name = c_char_p(b"input_ids")
        output_name = c_char_p(b"logits")

        input_names = (c_char_p * 1)(input_name)
        output_names = (c_char_p * 1)(output_name)
        input_values = (c_void_p * 1)(input_tensor)
        output_values = (c_void_p * 1)()

        # Run inference
        run_func = _get_func(self._api_ptr, _IDX_Run, _OrtRunFunc)
        status = run_func(
            self._ort_session,
            run_opts,
            input_names,
            input_values,
            1,
            output_names,
            1,
            output_values,
        )
        self._check_status(status)
        output_tensor = output_values[0]

        # Get output data
        get_data = _get_func(
            self._api_ptr, _IDX_GetTensorMutableData, _OrtGetTensorMutableDataFunc
        )
        data_ptr = c_void_p()
        status = get_data(output_tensor, byref(data_ptr))
        self._check_status(status)

        # Read logits as float array
        FloatArray = c_float * self.vocab_size
        logits = FloatArray.from_address(ctypes.addressof(data_ptr))

        # Convert to numpy for softmax and top-k
        logits_np = np.array(logits, dtype=np.float32)
        exp_logits = np.exp(logits_np - np.max(logits_np))
        probs = exp_logits / exp_logits.sum()

        top_indices = np.argsort(probs)[::-1][:top_k]
        results = []
        for idx in top_indices:
            word = self.idx2word.get(int(idx), '<unk>')
            if word in ('<pad>', '<unk>'):
                continue
            results.append((word, float(probs[idx])))

        # Cleanup
        release_val = _get_func(self._api_ptr, _IDX_ReleaseValue, _OrtReleaseValueFunc)
        release_val(input_tensor)
        release_val(output_tensor)

        release_run_opts = _get_func(self._api_ptr, _IDX_ReleaseRunOptions, _OrtReleaseRunOptionsFunc)
        release_run_opts(run_opts)

        return results[:top_k]

    def predict_single(self, context_words: list[str]) -> Optional[str]:
        """Return the single best prediction, or None."""
        preds = self.predict(context_words, top_k=1)
        return preds[0][0] if preds else None

    def __del__(self):
        """Release ONNX Runtime resources."""
        if not self._api_ptr:
            return
        try:
            release_val = _get_func(self._api_ptr, _IDX_ReleaseValue, _OrtReleaseValueFunc)
            release_mem = _get_func(self._api_ptr, _IDX_ReleaseMemoryInfo, _OrtReleaseMemoryInfoFunc)
            release_session = _get_func(self._api_ptr, _IDX_ReleaseSession, _OrtReleaseSessionFunc)
            release_env = _get_func(self._api_ptr, _IDX_ReleaseEnv, _OrtReleaseEnvFunc)

            if self._ort_memory_info:
                release_mem(self._ort_memory_info)
            if self._ort_session:
                release_session(self._ort_session)
            if self._ort_env:
                release_env(self._ort_env)
        except Exception:
            pass
