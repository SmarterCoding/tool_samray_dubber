"""
Offline subtitle translation using Meta's NLLB-200-3.3B model.
Provides high-quality translation across 200 languages, running fully locally.
"""
import os
import torch
from typing import Callable, Optional
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

# Mapping from your UI languages to NLLB's FLORES-200 language codes
LANG_CODES = {
    "Khmer": "khm_Khmr",
    "English": "eng_Latn",
    "Thai": "tha_Thai",
    "Chinese": "zho_Hans",
    "Japanese": "jpn_Jpan",
    "Korean": "kor_Hang",
    "Vietnamese": "vie_Latn",
    # Raw codes accepted as-is
    "khm_Khmr": "khm_Khmr", "eng_Latn": "eng_Latn", "tha_Thai": "tha_Thai",
    "zho_Hans": "zho_Hans", "jpn_Jpan": "jpn_Jpan", "kor_Hang": "kor_Hang",
    "vie_Latn": "vie_Latn"
}

def _code(lang: str) -> str:
    return LANG_CODES.get(lang, lang)


class Translator:
    def __init__(
        self,
        provider: str = "nllb",
        model_name: str = "facebook/nllb-200-3.3B",
        device: str = "auto",
        **kwargs
    ):
        self.provider = "nllb"
        self.model_name = model_name
        self.device = device
        self._tokenizer = None
        self._model = None
        self._current_src_lang = None

    def _load_model(self, src_lang: str):
        """Lazy-loads the heavy model into VRAM/RAM on first use."""
        if self._model is None:
            # Determine device
            if self.device == "auto":
                if torch.cuda.is_available():
                    self._device = "cuda"
                elif torch.backends.mps.is_available():
                    self._device = "mps"
                else:
                    self._device = "cpu"
            else:
                self._device = self.device

            print(f"Loading NLLB model {self.model_name} on {self._device}...")

            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)

            # Attempt 8-bit quantization to save VRAM if on CUDA
            load_kwargs = {}
            if self._device == "cuda":
                try:
                    import bitsandbytes
                    load_kwargs["load_in_8bit"] = True
                    print("Using 8-bit quantization to save VRAM.")
                except ImportError:
                    load_kwargs["torch_dtype"] = torch.float16
                    print("bitsandbytes not found. Falling back to float16.")
            elif self._device == "cpu":
                load_kwargs["torch_dtype"] = torch.float32
            else:
                load_kwargs["torch_dtype"] = torch.float16

            self._model = AutoModelForSeq2SeqLM.from_pretrained(
                self.model_name,
                device_map="auto" if self._device != "cpu" else None,
                **load_kwargs
            )
            if self._device == "cpu":
                self._model.to(self._device)

            print("NLLB model loaded successfully.")

    def translate_text(self, text: str, source_lang: str, target_lang: str) -> str:
        out = self.translate_batch([text], source_lang, target_lang)
        return out[0] if out else text

    def translate_batch(
        self,
        texts: list[str],
        source_lang: str,
        target_lang: str,
        progress: Optional[Callable[[str], None]] = None,
        progress_percent: Optional[Callable[[int], None]] = None,
        on_item_done: Optional[Callable[[int, str], None]] = None,
    ) -> list[str]:
        if not texts:
            return []

        src = _code(source_lang) if source_lang not in ("Auto", "auto", "") else "eng_Latn"
        tgt = _code(target_lang)

        if src == tgt:
            if progress: progress("Source and target are the same; skipping.")
            if progress_percent: progress_percent(100)
            return list(texts)

        if progress:
            progress("Loading NLLB model (this may take a moment)…")

        self._load_model(src)

        # Set the source language in the tokenizer
        if self._current_src_lang != src:
            self._tokenizer.src_lang = src
            self._current_src_lang = src

        # Get target language BOS token ID
        forced_bos_token_id = self._tokenizer.convert_tokens_to_ids(tgt)

        total = len(texts)
        results = []
        batch_size = 8  # Process 8 lines at a time to avoid OOM

        if progress_percent:
            progress_percent(0)

        for i in range(0, total, batch_size):
            chunk = texts[i:i+batch_size]

            # Skip empty lines
            valid_indices = [j for j, t in enumerate(chunk) if t.strip()]
            valid_texts = [chunk[j] for j in valid_indices]

            if not valid_texts:
                for t in chunk:
                    results.append(t)
                continue

            try:
                inputs = self._tokenizer(
                    valid_texts,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=512
                ).to(self._device)

                with torch.no_grad():
                    translated_tokens = self._model.generate(
                        **inputs,
                        forced_bos_token_id=forced_bos_token_id,
                        max_length=512,
                        num_beams=4,
                        early_stopping=True
                    )

                decoded = self._tokenizer.batch_decode(
                    translated_tokens, skip_special_tokens=True
                )

                # Map decoded text back to original positions
                chunk_results = list(chunk)
                for j, valid_idx in enumerate(valid_indices):
                    chunk_results[valid_idx] = decoded[j]

                results.extend(chunk_results)

            except Exception as e:
                # Fallback to original text if a batch fails
                if progress:
                    progress(f"Batch {i//batch_size + 1} failed: {str(e)[:50]}")
                results.extend(chunk)

            # Report progress per item
            if on_item_done:
                for j, res in enumerate(chunk):
                    on_item_done(i + j, res)

            done = min(i + batch_size, total)
            if progress:
                progress(f"Translated {done}/{total}")
            if progress_percent:
                progress_percent(int(done / total * 100))

        if progress_percent:
            progress_percent(100)

        return results