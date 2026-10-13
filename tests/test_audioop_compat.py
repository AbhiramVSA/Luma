"""Regression coverage for pydub's PCM operations on supported Python versions."""

import struct

from pydub import AudioSegment


def test_pcm_rms_and_channel_conversion_use_audioop_backend():
    samples = (1000, -1000, 2000, -2000)
    pcm = struct.pack("<4h", *samples)
    mono = AudioSegment(data=pcm, sample_width=2, frame_rate=8000, channels=1)

    assert mono.rms == 1581

    stereo = mono.set_channels(2)
    assert stereo.channels == 2
    assert stereo.frame_width == 4
    assert stereo.frame_count() == 4
    assert stereo.rms == mono.rms
