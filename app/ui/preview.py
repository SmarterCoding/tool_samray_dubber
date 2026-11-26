import os
from PySide6.QtCore import Qt, QObject, QUrl, Signal, QTimer
from PySide6.QtGui import QFont
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import QLabel


class SubtitleOverlay(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.setWordWrap(True)
        self.setTextFormat(Qt.PlainText)
        self.setMargin(6)
        self._family = "Khmer OS"
        self._size = 20
        self.setFont(QFont(self._family, self._size, QFont.Bold))
        self.setStyleSheet(
            "QLabel { color: white; background: rgba(0,0,0,155);"
            " border-radius: 6px; padding: 6px 10px; }")
        self.hide()

    def set_subtitle_font(self, family: str, size: int):
        self._family = family or self._family
        self._size = max(10, int(size))
        self.setFont(QFont(self._family, self._size, QFont.Bold))

    def show_text(self, text: str):
        text = (text or "").strip()
        if not text:
            if self.isVisible():
                self.hide()
            return
        self.setText(text)
        self.show()
        self.raise_()


class DubPreviewController(QObject):
    state_changed = Signal(bool)
    position_synced = Signal(int)

    def __init__(self, video_player: QMediaPlayer, video_audio: QAudioOutput, parent=None):
        super().__init__(parent)
        self.video_player = video_player
        self.video_audio = video_audio

        self.dub_player = QMediaPlayer(self)
        self.dub_audio = QAudioOutput(self)
        self.dub_audio.setVolume(1.0)
        self.dub_player.setAudioOutput(self.dub_audio)

        self._enabled = False
        self._mute_original = True
        self._original_volume = video_audio.volume()
        self._track_path = ""

        # ---- Smooth-sync tuning ----
        # Only resync when drift exceeds this (ms).  Higher than the old
        # 150 ms so normal clock drift between two QMediaPlayers does not
        # cause constant micro-seeking / audio stutter.
        self._sync_threshold_ms = 300
        # Hysteresis: drift must exceed the threshold this many times in a
        # row before we actually seek.  Prevents one-off jitter from moving
        # the dub track.
        self._sync_hysteresis_count = 2
        self._drift_strikes = 0

        # Debounce timer: we never seek more often than ~150 ms.  The
        # positionChanged signal can fire 60+ times/sec; seeking on every
        # one causes audible crackling.
        self._sync_debounce = QTimer(self)
        self._sync_debounce.setSingleShot(True)
        self._sync_debounce.setInterval(150)
        self._sync_debounce.timeout.connect(self._flush_pending_sync)

        self._pending_sync_ms = None
        self._user_seeking = False

        self.video_player.positionChanged.connect(self._on_video_position)
        self.video_player.playbackStateChanged.connect(self._on_video_state)
        self.dub_player.mediaStatusChanged.connect(self._on_dub_status)

    def set_mute_original(self, mute: bool):
        self._mute_original = mute
        if self._enabled:
            if mute:
                self.video_audio.setVolume(0.0)
            else:
                self.video_audio.setVolume(self._original_volume)

    def load_dub_track(self, wav_path: str):
        path = os.path.abspath(wav_path)

        if not os.path.isfile(path):
            self.invalidate()
            return

        self.dub_player.stop()
        self._track_path = path

        # Use absolute path to guarantee QMediaPlayer finds the file
        self.dub_player.setSource(QUrl.fromLocalFile(path))

        # The source loads asynchronously; mediaStatusChanged applies the
        # position once the track is actually ready.
        if self._enabled:
            self._sync_now()

    def has_track(self) -> bool:
        return (
            bool(self._track_path)
            and os.path.isfile(self._track_path)
            and self.dub_player.source().isValid()
        )

    def invalidate(self):
        if self._enabled:
            self.set_enabled(False)
        self.dub_player.stop()
        self._track_path = ""
        self.dub_player.setSource(QUrl())

    def set_enabled(self, on: bool):
        if on == self._enabled:
            return

        if on and not self.has_track():
            return

        self._enabled = on

        if on:
            self._original_volume = self.video_audio.volume()
            if self._mute_original:
                self.video_audio.setVolume(0.0)
            self.dub_audio.setVolume(1.0)
            self._sync_now(immediate=True)
        else:
            self._sync_debounce.stop()
            self._pending_sync_ms = None
            self._drift_strikes = 0
            self.video_audio.setVolume(self._original_volume)
            self.dub_player.pause()

        self.state_changed.emit(on)

    def is_enabled(self) -> bool:
        return self._enabled

    def sync_to_position(self, ms: int):
        """Public entry point for an immediate dub sync (e.g. user seek).

        Stops any pending debounce and seeks the dub track right away so
        the voice stays glued to the video after a manual timeline jump.
        """
        if not self._enabled or not self.has_track():
            return
        self._sync_now(immediate=True)

    def _sync_now(self, immediate: bool = False):
        """Seek the dub track to the video and match its play state.

        When ``immediate`` is False (the default) the request is debounced
        through a short timer so we never seek more than once every ~150 ms.
        """
        video_position = max(0, int(self.video_player.position()))

        if immediate:
            self._sync_debounce.stop()
            self._pending_sync_ms = None
            self._do_sync(video_position)
            return

        # Debounce: remember the target and let the timer fire the actual
        # seek.  This coalesces rapid positionChanged events.
        self._pending_sync_ms = video_position
        if not self._sync_debounce.isActive():
            self._sync_debounce.start()

    def _flush_pending_sync(self):
        """Fire a pending debounced sync."""
        if self._pending_sync_ms is None:
            return
        pos = self._pending_sync_ms
        self._pending_sync_ms = None
        self._do_sync(pos)

    def _do_sync(self, video_position: int):
        """Perform the actual seek + play/pause decision."""
        duration = self.dub_player.duration()

        # Past the end of the dub track: stay silent instead of repeatedly
        # restarting the last 50 ms. Seeking back into range resumes it.
        if duration > 0 and video_position >= int(duration) - 50:
            self.dub_player.pause()
            return

        self.dub_player.setPosition(video_position)

        if self.video_player.playbackState() == QMediaPlayer.PlayingState:
            self.dub_player.play()
        else:
            self.dub_player.pause()

    def _on_video_position(self, ms: int):
        self.position_synced.emit(ms)
        if not self._enabled:
            return

        playing = (
            self.video_player.playbackState()
            == QMediaPlayer.PlayingState
        )

        if not playing:
            if (self.dub_player.playbackState()
                    == QMediaPlayer.PlayingState):
                self.dub_player.pause()
            return

        # Restart the dub track if it ended before the video.
        dub_stopped = (
            self.dub_player.playbackState()
            == QMediaPlayer.StoppedState
        )
        drift = abs(self.dub_player.position() - ms)

        if dub_stopped:
            # Dub track ended — resync immediately so the voice doesn't
            # stay silent while the video continues.
            self._sync_now(immediate=True)
            self._drift_strikes = 0
            return

        if drift > self._sync_threshold_ms:
            self._drift_strikes += 1
            if self._drift_strikes >= self._sync_hysteresis_count:
                # Drift is persistent: debounce the actual seek so we
                # don't seek on every single positionChanged event.
                self._sync_now()
                self._drift_strikes = 0
        else:
            # Drift is within tolerance — clear strikes and make sure
            # the dub track is playing.
            self._drift_strikes = 0
            if (self.dub_player.playbackState()
                    != QMediaPlayer.PlayingState):
                self.dub_player.play()

    def _on_video_state(self, state):
        if not self._enabled:
            return
        if state == QMediaPlayer.PlayingState:
            # When playback starts (e.g. after a user seek), sync immediately
            # so the dub voice starts at the right place.
            if (abs(self.dub_player.position()
                    - self.video_player.position())
                    > self._sync_threshold_ms):
                self._sync_now(immediate=True)
            else:
                self.dub_player.play()
        elif state == QMediaPlayer.PausedState:
            self.dub_player.pause()
        elif state == QMediaPlayer.StoppedState:
            self.dub_player.stop()

    def _on_dub_status(self, status):
        if not self._enabled:
            return

        if status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            self._sync_now()
        elif (status == QMediaPlayer.MediaStatus.EndOfMedia
                and self.video_player.playbackState()
                == QMediaPlayer.PlayingState):
            # The dubbed track ended. Restart only when the video is still
            # inside the track; otherwise let the rest of the video play.
            duration = self.dub_player.duration()
            if (duration <= 0
                    or self.video_player.position() < int(duration) - 100):
                self._sync_now()