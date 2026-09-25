"""Small, dependency-free UI audio cues."""

from __future__ import annotations

from array import array
from math import pi, sin

import pygame


class AudioFeedback:
    """Generate a short UI click when the active mixer format supports it."""

    def __init__(self, volume_percent: int = 70):
        self._sound = None
        mixer_format = pygame.mixer.get_init()
        if mixer_format is not None:
            frequency, sample_format, channels = mixer_format
            if sample_format == -16 and channels in (1, 2):
                duration = 0.035
                frames = max(1, int(frequency * duration))
                samples = array("h")
                for frame in range(frames):
                    envelope = 1.0 - frame / frames
                    sample = int(4200 * envelope * sin(2 * pi * 620 * frame / frequency))
                    samples.extend([sample] * channels)
                try:
                    self._sound = pygame.mixer.Sound(buffer=samples)
                except pygame.error:
                    self._sound = None
        self.set_volume(volume_percent)

    @property
    def available(self) -> bool:
        return self._sound is not None

    def set_volume(self, volume_percent: int) -> None:
        if self._sound is not None:
            self._sound.set_volume(max(0, min(100, int(volume_percent))) / 100)

    def play_click(self) -> None:
        if self._sound is not None:
            self._sound.play()
