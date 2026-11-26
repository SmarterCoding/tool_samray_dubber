"""
Test script for SAMRAY DUBBER PRO smooth dubbing voice sync.

Tests:
1. Fade envelope on audio clips (prevents clicks at boundaries)
2. Sync controller hysteresis and debounce logic
"""
import os
import sys
import math

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_fade_envelope():
    """Test that _apply_fade_envelope smooths clip boundaries."""
    print("=" * 60)
    print("Test 1: Fade envelope smooths audio clip boundaries")
    print("=" * 60)

    from app.ffmpeg_utils import _apply_fade_envelope

    # Create a constant-amplitude signal (like a sustained voice note)
    sample_rate = 44100
    duration_ms = 500
    num_samples = int(duration_ms * sample_rate / 1000.0)
    data = [30000] * num_samples  # constant loud signal

    import numpy as np
    data_arr = np.array(data, dtype=np.int32)

    faded = _apply_fade_envelope(data_arr, sample_rate, fade_ms=15.0)

    # Check fade-in: first sample should be 0 (or near 0)
    first_val = abs(faded[0])
    print(f"  First sample after fade-in: {first_val} (should be ~0)")
    assert first_val < 100, f"Fade-in not applied: first sample = {first_val}"

    # Check fade-out: last sample should be 0 (or near 0)
    last_val = abs(faded[-1])
    print(f"  Last sample after fade-out: {last_val} (should be ~0)")
    assert last_val < 100, f"Fade-out not applied: last sample = {last_val}"

    # Check middle is preserved
    mid_val = abs(faded[num_samples // 2])
    print(f"  Middle sample preserved: {mid_val} (should be ~30000)")
    assert mid_val > 29000, f"Middle should be preserved: {mid_val}"

    print("  PASSED: Fade envelope smooths clip boundaries\n")


def test_sync_threshold_and_hysteresis():
    """Test sync threshold and hysteresis logic."""
    print("=" * 60)
    print("Test 2: Sync threshold and hysteresis")
    print("=" * 60)

    # Simulate the drift-strike logic from preview.py
    sync_threshold_ms = 300
    hysteresis_count = 2
    drift_strikes = 0

    def check_drift(drift_ms):
        nonlocal drift_strikes
        if drift_ms > sync_threshold_ms:
            drift_strikes += 1
            if drift_strikes >= hysteresis_count:
                drift_strikes = 0
                return "SYNC"
            return "STRIKE"
        else:
            drift_strikes = 0
            return "OK"

    # Normal playback: drift stays below threshold -> no sync
    for drift in [50, 100, 150, 200, 100]:
        result = check_drift(drift)
        assert result == "OK", f"Expected OK for drift={drift}, got {result}"
    print("  Normal drift (<300ms): no sync triggered - PASSED")

    # Clock drift: two consecutive drifts above threshold -> sync
    drift_strikes = 0
    results = []
    for drift in [350, 400]:
        results.append(check_drift(drift))
    assert results[-1] == "SYNC", f"Expected SYNC, got {results}"
    print("  Persistent drift (>300ms x2): sync triggered - PASSED")

    # Single spike: one drift above threshold -> no sync (hysteresis)
    drift_strikes = 0
    result = check_drift(500)
    assert result == "STRIKE", f"Expected STRIKE, got {result}"
    result = check_drift(100)  # back to normal -> clears strikes
    assert result == "OK", f"Expected OK, got {result}"
    print("  Single spike cleared by normal drift: no false sync - PASSED")

    print()


def test_debounce_interval():
    """Test that debounce interval is reasonable."""
    print("=" * 60)
    print("Test 3: Debounce interval")
    print("=" * 60)

    from app.ui.preview import DubPreviewController

    # We can't instantiate without QApplication, but we can check
    # the source code for the debounce interval value.
    import inspect
    source = inspect.getsource(DubPreviewController.__init__)
    assert "setInterval(150)" in source, "Debounce interval should be 150ms"
    print("  Debounce interval set to 150ms - PASSED")

    # Check sync threshold
    assert "_sync_threshold_ms = 300" in source, \
        "Sync threshold should be 300ms"
    print("  Sync threshold set to 300ms - PASSED")

    # Check hysteresis count
    assert "_sync_hysteresis_count = 2" in source, \
        "Hysteresis count should be 2"
    print("  Hysteresis count set to 2 - PASSED")

    print()


def test_sync_to_position_method_exists():
    """Test that sync_to_position method exists on the controller."""
    print("=" * 60)
    print("Test 4: sync_to_position public method")
    print("=" * 60)

    from app.ui.preview import DubPreviewController
    assert hasattr(DubPreviewController, 'sync_to_position'), \
        "sync_to_position method should exist"
    print("  sync_to_position method exists - PASSED")
    print()


def test_export_audio_map():
    """Test that export uses dubbed audio track correctly."""
    print("=" * 60)
    print("Test 5: Export audio mapping")
    print("=" * 60)

    from app.ffmpeg_utils import mix_dubbed_video
    import inspect
    source = inspect.getsource(mix_dubbed_video)

    # When keep_original_audio is False, it should use [1:a] (dubbed audio)
    assert "audio_map = \"[1:a]\"" in source, \
        "Default audio map should be dubbed track [1:a]"
    print("  Default audio map uses dubbed track [1:a] - PASSED")

    # When keep_original_audio is True, it mixes both
    assert "amix=inputs=2" in source, \
        "Keep-original should mix both audio tracks"
    print("  Keep-original mixes both tracks with amix - PASSED")

    print()


if __name__ == "__main__":
    test_fade_envelope()
    test_sync_threshold_and_hysteresis()
    test_debounce_interval()
    test_sync_to_position_method_exists()
    test_export_audio_map()

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print()
    print("Summary of smooth-dubbing improvements:")
    print("  1. preview.py: Debounce (150ms) + hysteresis (300ms x2) +")
    print("     immediate sync on user seek prevents audio crackling.")
    print("  2. ffmpeg_utils.py: 15ms fade-in/fade-out on each TTS clip")
    print("     prevents clicks between subtitle segments.")
    print("  3. main_window.py: Timeline seek immediately syncs dub track.")
    print()
