import glob
import importlib
import os
import random
import re
import subprocess
import sys
from pathlib import Path

from app.debugging.logging import getLogger

from .base import BaseIODevice


class SoundPlayer(BaseIODevice):
    """Controls audio playback functionality and exposes sounds via the `fx` collection.

    Access sounds as callables, e.g. `sound.fx.awake()`, using the `play()` method or play a sound file
    using the `play_file()` method.
    """

    def __init__(self, enabled=True):
        """Initialize SoundPlayer with optional enabled flag
        
        :param enabled: If False, all sound operations are silently ignored
        """
        BaseIODevice.__init__(self, enabled=enabled)
        
        # Disable auto-promotion because some debug messages legitimately contain the word 'error' as part of sound names.
        self._log = getLogger(self.__class__.__name__, disable_error_promotion=True)
        self._pa = None
        self._resources_path = Path(__file__).parent.parent.parent / 'sound'
        self._audio_backend = None  # Will be set in setup()
        self._pydub_available = False
        self._max_volume = 1.0
        self._alsa_numid = 4
        self._tts_language = 'cs'
        self._mp3_player = None
        self._ogg_player = None
        # Supported audio file extensions.
        self._supported_exts = ('.wav', '.mp3', '.ogg', '.pcm')
        # Predefined list of supported sounds. These names must correspond to file name prefixes inside the resources path.
        # New names may be discovered dynamically.
        self._predefined_sound_names = ['awake', 'dizzy', 'error', 'greeting', 'ready', 'sad', 'capture']
        self._sound_names = list(self._predefined_sound_names)
        # Active theme name.
        self._theme = 'default'
        # All indexed themes: theme -> { sound_name -> [Path, ...] }.
        self._themes: dict[str, dict[str, list[Path]]] = {}
        # Active mapping (points to self._themes[self._theme]).
        self._sound_files: dict[str, list[Path]] = {}

        # Attach collection object for sound effects under the `fx` namespace.
        self.fx = _SoundEffects(self)
    

    def setup(self, audio_backend=None, volume=1.0, alsa_numid=4, tts_language='cs', theme='default', enabled: bool | None = None):
        """Setup audio system
        
        :param audio_backend: Preferred audio backend ('pulseaudio', 'alsa', 'native')
        :param volume: Maximum volume level (0.0 to 1.0)
        :param alsa_numid: ALSA mixer control numid for volume adjustment
        :param tts_language: Text-to-speech language code
        :param theme: Sound theme to use (default 'default')
        :param enabled: Optional override of enabled flag (None keeps constructor state)
        """
        super().setup(enabled=enabled)
            
        self._log.info('Setting up audio system...')
        
        # Store volume settings
        self._max_volume = max(0.0, min(1.0, volume))  # Clamp between 0.0 and 1.0
        self._alsa_numid = alsa_numid
        self._tts_language = tts_language
        self._theme = theme

        if not self._enabled:
            self._log.info('Sound system disabled')
            return
        
        self._init_libraries()
        self._init_audio_backend(audio_backend)
        self._check_audio_output_available()
        
        if not self._available:
            self._log.error('No audio output device available - sound system disabled.')
            return
        
        self._index_all_themes()
        self._apply_active_theme(log_missing=True)
        
        # Log themes summary
        themes_list = self.list_themes()
        themes_str = ', '.join(themes_list) if themes_list else '(none)'
        self._log.info(f'Available sound themes: {themes_str}. Selected theme: {self._theme}')

    def close(self):
        """Cleanup audio resources"""
        if not self._enabled:
            return
            
        if self._pa is not None:
            self._pa.terminate()
            self._pa = None
        self._log.info('Audio system closed')

    def toggle(self):
        self._enabled = not self._enabled
        self.setup(self._audio_backend, self._max_volume, self._alsa_numid, self._tts_language)

    def _resolve_audio_file(self, audio_file):
        """Resolve audio file pattern to actual file path inside current theme.

        :param audio_file: Single file path/pattern or list of patterns (relative to theme dir unless absolute).
        :return: Path object of selected file or None if not found
        """
        theme_dir = self._resources_path / self._theme
        all_files = []
        
        # Convert single item to list for uniform processing
        items = audio_file if isinstance(audio_file, (list, tuple)) else [audio_file]
        
        if not items:
            self._log.warning('Empty audio file list provided')
            return None
        
        # Process each item (file or pattern)
        for item in items:
            if '*' in item or '?' in item:
                # Wildcard pattern - convert to full path and glob
                pattern = str(theme_dir / item) if not Path(item).is_absolute() else item
                all_files.extend(glob.glob(pattern))
            else:
                # Regular file - convert to full path
                full_path = theme_dir / item if not Path(item).is_absolute() else Path(item)
                all_files.append(str(full_path))
        
        if not all_files:
            self._log.warning(f'No files found matching: {audio_file}')
            return None
        
        # Select random file
        selected_file = random.choice(all_files)
        file_count = len(all_files)
        
        if file_count > 1:
            self._log.info(f'Randomly selected: {Path(selected_file).name} from {file_count} matching files')
        
        return Path(selected_file)

    def _set_system_volume(self, volume):
        """Set system volume using appropriate method
        
        :param volume: Volume level (0.0 to 1.0)
        """
        try:
            # Convert to percentage for system commands
            volume_percent = int(volume * 100)
            
            if self._audio_backend == 'pulseaudio':
                # Use pactl to set PulseAudio volume
                subprocess.run(['pactl', 'set-sink-volume', '@DEFAULT_SINK@', f'{volume_percent}%'], 
                             check=True, capture_output=True)
            elif self._audio_backend == 'alsa':
                # Use amixer cset with configurable numid to set ALSA volume
                subprocess.run(['amixer', 'cset', f'numid={self._alsa_numid}', f'{volume_percent}%'], 
                             check=True, capture_output=True)
                             
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            self._log.warning(f'Failed to set system volume: {e}')

    def _detect_audio_players(self):
        """Detect available audio players for different formats"""
        # Detect MP3 player
        try:
            subprocess.run(['mpg123', '--version'], capture_output=True, check=True)
            self._mp3_player = 'mpg123'
            self._log.info('Detected MP3 player: mpg123')
        except (FileNotFoundError, subprocess.CalledProcessError):
            try:
                subprocess.run(['ffplay', '-version'], capture_output=True, check=True)
                self._mp3_player = 'ffplay'
                self._log.info('Detected MP3 player: ffplay')
            except (FileNotFoundError, subprocess.CalledProcessError):
                self._log.warning('No MP3 player found (install mpg123 or ffmpeg)')
        
        # Detect OGG player
        try:
            subprocess.run(['ogg123', '--version'], capture_output=True, check=True)
            self._ogg_player = 'ogg123'
            self._log.info('Detected OGG player: ogg123')
        except (FileNotFoundError, subprocess.CalledProcessError):
            try:
                subprocess.run(['ffplay', '-version'], capture_output=True, check=True)
                self._ogg_player = 'ffplay'
                self._log.info('Detected OGG player: ffplay')
            except (FileNotFoundError, subprocess.CalledProcessError):
                self._log.warning('No OGG player found (install vorbis-tools or ffmpeg)')

    def _check_audio_output_available(self):
        """Check if audio output device is available for current backend.
        
        Tests audio output availability using backend-specific methods:
        - pulseaudio: Check for available sinks via pactl
        - alsa: Check for playback devices via aplay
        - native: Check PyAudio for output devices with maxOutputChannels > 0
        
        Sets _available to False if no output device is found.
        """
        if not self._audio_backend:
            self._log.warning('No audio backend initialized - cannot check output availability.')
            self._available = False
            return
        
        try:
            if self._audio_backend == 'pulseaudio':
                # Check for available PulseAudio sinks.
                result = subprocess.run(['pactl', 'list', 'short', 'sinks'], 
                                      capture_output=True, check=True, text=True)
                if not result.stdout.strip():
                    self._log.warning('No PulseAudio sinks found.')
                    self._available = False
                    return
                    
            elif self._audio_backend == 'alsa':
                # Check for ALSA playback devices.
                result = subprocess.run(['aplay', '-l'], 
                                      capture_output=True, check=True, text=True)
                if 'no soundcards found' in result.stdout.lower() or not result.stdout.strip():
                    self._log.warning('No ALSA playback devices found.')
                    self._available = False
                    return
                    
            elif self._audio_backend == 'native':
                # Check PyAudio for output devices (suppress ALSA errors).
                if not self._pa:
                    self._log.warning('PyAudio not initialized - cannot check output availability.')
                    self._available = False
                    return
                
                # Redirect stderr to suppress ALSA errors.
                stderr_fd = sys.stderr.fileno()
                old_stderr = os.dup(stderr_fd)
                devnull_fd = os.open(os.devnull, os.O_WRONLY)
                os.dup2(devnull_fd, stderr_fd)
                
                try:
                    device_count = self._pa.get_device_count()
                    has_output = False
                    
                    for i in range(device_count):
                        device_info = self._pa.get_device_info_by_index(i)
                        if device_info.get('maxOutputChannels', 0) > 0:
                            has_output = True
                            break
                    
                    if not has_output:
                        self._log.warning('No PyAudio output devices found.')
                        self._available = False
                        return
                        
                finally:
                    # Restore stderr.
                    os.dup2(old_stderr, stderr_fd)
                    os.close(old_stderr)
                    os.close(devnull_fd)
            
            self._log.info(f'Audio output available via {self._audio_backend} backend.')
            
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
            self._log.warning(f'Audio output availability check failed: {e}')
            self._available = False

    def list_sounds(self) -> list[str]:
        """Return list of all supported sound names (available or not)."""
        return list(self._sound_names)

    def list_available_sounds(self) -> list[str]:
        """Return list of sound names that currently have at least one file."""
        return [name for name, files in self._sound_files.items() if files]

    def _index_all_themes(self):
        """Index all theme subdirectories and discover extra sounds.

        Discovery logic (per theme):
        - Normalize file stem: collapse any run of non-alphanumeric chars to single underscore; trim edges.
        - Strip trailing numeric groups (optionally preceded by '_' or '-') to form logical base name.
          Examples:
              dizzy.wav -> dizzy
              dizzy2.wav -> dizzy
              dizzy-2.wav -> dizzy
              dizzy__003.wav -> dizzy
        - Collapse spaces/special chars: "dizzy scream.wav" -> dizzy_scream
        - Effectively similar to matching '<name>*.*' inside the theme directory.
        - New logical names merged into global set of sound names (union across themes + seeds).
        - Seeds ensured in every theme map (possibly empty list).
        Debug log prints compact summary per theme: theme 'X': name(count)=file1,file2; name2(0); ...
        """
        self._themes.clear()
        base = self._resources_path
        if not base.exists():
            self._log.warning(f'Sound resources directory not found: {base}')
            return
        
        for tdir in [d for d in base.iterdir() if d.is_dir() and not d.name.startswith('.')]:
            tname = tdir.name
            files = [p for p in tdir.rglob('*') if p.is_file() and p.suffix.lower() in self._supported_exts]
            theme_map: dict[str, list[Path]] = {}
            for f in files:
                norm = re.sub(r'[^A-Za-z0-9]+', '_', f.stem).strip('_')
                base_name = re.sub(r'([_-]?\d+)+$', '', norm) or norm
                theme_map.setdefault(base_name, []).append(f)
            # Ensure seeds exist
            for seed in self._predefined_sound_names:
                theme_map.setdefault(seed, [])
            self._themes[tname] = theme_map
        # Merge all discovered names into global list
        discovered_all = set(self._predefined_sound_names)
        for theme_map in self._themes.values():
            discovered_all.update(theme_map.keys())
        self._sound_names = sorted(discovered_all)
        # Debug summaries
        for tname, theme_map in self._themes.items():
            parts = []
            for sname, paths in sorted(theme_map.items()):
                if paths:
                    file_list = ','.join(p.name for p in paths)
                    parts.append(f"{sname}({len(paths)})={file_list}")
                else:
                    parts.append(f"{sname}(0)")
            self._log.debug(f"Theme '{tname}': {'; '.join(parts)}")

    def _apply_active_theme(self, log_missing=False):
        """Activate currently selected theme mapping."""
        if self._theme in self._themes:
            self._sound_files = self._themes[self._theme]
        else:
            self._log.warning(f"Selected theme '{self._theme}' not indexed; no sounds loaded.")
            self._sound_files = {}
        active_keys = set(self._sound_files.keys()) if self._sound_files else set()
        self._sound_names = sorted({*self._predefined_sound_names, *active_keys})
        if log_missing:
            for seed in self._predefined_sound_names:
                if not self._sound_files.get(seed):
                    self._log.warning(f'No files found for sound "{seed}" in theme "{self._theme}".')

    def list_themes(self) -> list[str]:
        """Return list of indexed sound themes."""
        return sorted(self._themes.keys())

    def set_theme(self, theme: str):
        """Switch active theme at runtime and apply mapping."""
        if theme == self._theme:
            return
        if theme not in self._themes:
            self._log.warning(f"Theme '{theme}' not available.")
            return
        self._theme = theme
        self._apply_active_theme(log_missing=True)
        self._log.info(f"Switched sound theme to '{theme}'.")

    def _init_libraries(self):
        """Import optional media libraries (pydub, wave)."""
        try:
            self._pydub = importlib.import_module('pydub')
            self._pydub_available = True
            self._log.info('pydub is available')
        except ImportError:
            self._pydub_available = False
            self._log.warning('pydub not available - MP3/OGG support limited')
        try:
            self._wave = importlib.import_module('wave')
            self._log.info('wave module is available')
        except ImportError:
            self._wave = None
            self._log.warning('wave module not available')

    def _init_audio_backend(self, preferred):
        """Detect and initialize an audio backend."""
        self._audio_backend = None

        def try_pulseaudio():
            try:
                subprocess.run(['pulseaudio', '--check'], check=True, capture_output=True)
                self._log.info('PulseAudio is available')
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                self._log.warning('PulseAudio not available or not running')
                return False

        def try_alsa():
            try:
                subprocess.run(['aplay', '--version'], check=True, capture_output=True)
                self._log.info('ALSA is available')
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                self._log.warning('ALSA not available')
                return False

        def try_native():
            try:
                pyaudio_module = importlib.import_module('pyaudio')
                self._pa = pyaudio_module.PyAudio()
                self._log.info('PyAudio initialized successfully')
                return True
            except (ImportError, Exception) as e:
                self._log.warning(f'PyAudio initialization failed: {e}')
                self._pa = None
                return False

        order = []
        if preferred:
            order.append(preferred)
            for b in ['pulseaudio', 'alsa', 'native']:
                if b != preferred:
                    order.append(b)
        else:
            order = ['pulseaudio', 'alsa', 'native']

        for b in order:
            if b == 'pulseaudio' and try_pulseaudio():
                self._audio_backend = 'pulseaudio'
                break
            if b == 'alsa' and try_alsa():
                self._audio_backend = 'alsa'
                break
            if b == 'native' and try_native():
                self._audio_backend = 'native'
                break

        if self._audio_backend is None:
            self._log.error('No audio backend available')
            return

        self._log.info(f'Using audio backend: {self._audio_backend}')
        self._log.info(f'Maximum volume set to: {self._max_volume:.1%}')
        self._set_system_volume(self._max_volume)
        if self._audio_backend == 'alsa':
            self._detect_audio_players()

    def _play_file(self, full_path: Path, volume: float):
        """Internal helper to play a resolved concrete file path with volume handling."""
        # Calculate final volume
        final_volume = self._max_volume * max(0.0, min(1.0, volume))
        # Temporary system volume for ALSA / PulseAudio
        if volume != 1.0 and self._audio_backend in ['pulseaudio', 'alsa']:
            self._set_system_volume(final_volume)
        try:
            # Use the detected backend
            if self._audio_backend == 'pulseaudio':
                self._play_pulseaudio(str(full_path))
            elif self._audio_backend == 'alsa':
                self._play_alsa(str(full_path))
            elif self._audio_backend == 'native':
                self._play_native(str(full_path), volume)
            else:
                self._log.error('No audio backend available for playback')
        finally:
            # Restore max volume if it was temporarily changed
            if volume != 1.0 and self._audio_backend in ['pulseaudio', 'alsa']:
                self._set_system_volume(self._max_volume)

    def _play_alsa(self, audio_file):
        """Play audio file using ALSA
        
        :param audio_file: Path to audio file
        """
        try:
            file_path = Path(audio_file)
            extension = file_path.suffix.lower()
            
            if extension == '.pcm':
                # Play PCM file with aplay
                self._log.info(f'Playing PCM file via ALSA: {audio_file}')
                subprocess.run([
                    'aplay', 
                    '-r', '44100',
                    '-f', 'S16_LE',
                    '-c', '1',
                    str(audio_file)
                ], check=True)
            elif extension == '.wav':
                # Play WAV file with aplay
                self._log.info(f'Playing WAV file via ALSA: {audio_file}')
                subprocess.run(['aplay', str(audio_file)], check=True)
            elif extension == '.mp3':
                # Play MP3 file with detected player
                if self._mp3_player == 'mpg123':
                    self._log.info(f'Playing MP3 file via mpg123: {audio_file}')
                    subprocess.run(['mpg123', '-q', str(audio_file)], check=True)
                elif self._mp3_player == 'ffplay':
                    self._log.info(f'Playing MP3 file via ffplay: {audio_file}')
                    subprocess.run(['ffplay', '-nodisp', '-autoexit', str(audio_file)], check=True)
                else:
                    self._log.error('No MP3 player available')
            elif extension == '.ogg':
                # Play OGG file with detected player
                if self._ogg_player == 'ogg123':
                    self._log.info(f'Playing OGG file via ogg123: {audio_file}')
                    subprocess.run(['ogg123', '-q', str(audio_file)], check=True)
                elif self._ogg_player == 'ffplay':
                    self._log.info(f'Playing OGG file via ffplay: {audio_file}')
                    subprocess.run(['ffplay', '-nodisp', '-autoexit', str(audio_file)], check=True)
                else:
                    self._log.error('No OGG player available')
            else:
                self._log.error(f'Unsupported audio format for ALSA: {extension}')
        except subprocess.CalledProcessError as e:
            self._log.error(f'ALSA playback failed: {e}')
        except Exception as e:
            self._log.error(f'ALSA playback error: {e}')

    def _play_pulseaudio(self, audio_file):
        """Play audio file using PulseAudio
        
        :param audio_file: Path to audio file (.pcm, .wav, .mp3, or .ogg, 44kHz)
        """
        try:
            file_path = Path(audio_file)
            extension = file_path.suffix.lower()
            
            if extension == '.pcm':
                # Play PCM file with paplay
                self._log.info(f'Playing PCM file: {audio_file}')
                subprocess.run([
                    'paplay', 
                    '--rate=44000',
                    '--format=s16le',
                    '--channels=1',
                    str(audio_file)
                ], check=True)
            elif extension in ['.wav', '.mp3', '.ogg']:
                # Play WAV/MP3/OGG file with paplay
                self._log.info(f'Playing {extension.upper()} file: {audio_file}')
                subprocess.run(['paplay', str(audio_file)], check=True)
            else:
                self._log.error(f'Unsupported audio format: {extension}')
            
        except subprocess.CalledProcessError as e:
            self._log.error(f'PulseAudio playback failed: {e}')
        except FileNotFoundError:
            self._log.error('paplay command not found')

    def _play_native(self, audio_file, volume=1.0):
        """Play audio file using native Python PyAudio
        
        :param audio_file: Path to audio file (.pcm, .wav, .mp3, or .ogg, 44.1kHz)
        :param volume: Relative volume (0.0 to 1.0, relative to max volume)
        """
        if self._pa is None:
            self._log.error('PyAudio not available for native playback')
            return

        try:
            file_path = Path(audio_file)
            extension = file_path.suffix.lower()
            
            # Calculate final volume for native playback
            final_volume = self._max_volume * max(0.0, min(1.0, volume))
            
            if extension == '.pcm':
                self._log.info(f'Playing PCM file natively: {audio_file}')
                self._play_pcm_native(audio_file, final_volume)
            elif extension == '.wav':
                self._log.info(f'Playing WAV file natively: {audio_file}')
                self._play_wav_native(audio_file, final_volume)
            elif extension == '.mp3':
                self._log.info(f'Playing MP3 file natively: {audio_file}')
                self._play_mp3_native(audio_file, final_volume)
            elif extension == '.ogg':
                self._log.info(f'Playing OGG file natively: {audio_file}')
                self._play_ogg_native(audio_file, final_volume)
            else:
                self._log.error(f'Unsupported audio format: {extension}')
            
        except Exception as e:
            self._log.exception(f'Native playback failed: {e}')

    def _play_pcm_native(self, pcm_file, volume=1.0):
        """Play PCM file using PyAudio with volume control"""
        chunk = 1024
        
        # Open audio stream for 44.1kHz playback
        stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=44100,  # 44.1kHz
            output=True
        )
        
        try:
            with open(pcm_file, 'rb') as f:
                data = f.read(chunk)
                while data:
                    # Scale volume
                    scaled_data = bytes(int(sample * volume) for sample in data)
                    stream.write(scaled_data)
                    data = f.read(chunk)
        finally:
            stream.stop_stream()
            stream.close()

    def _play_wav_native(self, wav_file, volume=1.0):
        """Play WAV file using PyAudio with volume control"""
        if self._wave is None:
            self._log.error('wave module not available for WAV playback')
            return
            
        with self._wave.open(str(wav_file), 'rb') as wf:
            chunk = 1024
            
            stream = self._pa.open(
                format=self._pa.get_format_from_width(wf.getsampwidth()),
                channels=wf.getnchannels(),
                rate=wf.getframerate(),
                output=True
            )
            
            try:
                data = wf.readframes(chunk)
                while data:
                    # Scale volume
                    scaled_data = bytes(int(sample * volume) for sample in data)
                    stream.write(scaled_data)
                    data = wf.readframes(chunk)
            finally:
                stream.stop_stream()
                stream.close()

    def _play_mp3_native(self, mp3_file, volume=1.0):
        """Play MP3 file using PyAudio via pydub with volume control"""
        if not self._pydub_available:
            self._log.error('pydub not available for MP3 playback')
            return
            
        try:
            # Load MP3 file with pydub
            audio = self._pydub.AudioSegment.from_mp3(str(mp3_file))
            
            # Convert to raw audio data
            raw_data = audio.raw_data
            sample_rate = audio.frame_rate
            channels = audio.channels
            sample_width = audio.sample_width
            
            # Play using PyAudio
            stream = self._pa.open(
                format=self._pa.get_format_from_width(sample_width),
                channels=channels,
                rate=sample_rate,
                output=True
            )
            
            try:
                chunk_size = 1024
                for i in range(0, len(raw_data), chunk_size):
                    stream.write(raw_data[i:i+chunk_size])
            finally:
                stream.stop_stream()
                stream.close()
                
        except Exception as e:
            self._log.exception(f'MP3 playback failed: {e}')

    def _play_ogg_native(self, ogg_file, volume=1.0):
        """Play OGG file using PyAudio via pydub with volume control"""
        if not self._pydub_available:
            self._log.error('pydub not available for OGG playback')
            return
            
        try:
            # Load OGG file with pydub
            audio = self._pydub.AudioSegment.from_ogg(str(ogg_file))
            
            # Convert to raw audio data
            raw_data = audio.raw_data
            sample_rate = audio.frame_rate
            channels = audio.channels
            sample_width = audio.sample_width
            
            # Play using PyAudio
            stream = self._pa.open(
                format=self._pa.get_format_from_width(sample_width),
                channels=channels,
                rate=sample_rate,
                output=True
            )
            
            try:
                chunk_size = 1024
                for i in range(0, len(raw_data), chunk_size):
                    stream.write(raw_data[i:i+chunk_size])
            finally:
                stream.stop_stream()
                stream.close()
                
        except Exception as e:
            self._log.exception(f'OGG playback failed: {e}')

    def play_file(self, audio_path: Path | str, volume: float = 1.0):
        """Play explicit audio file path or wildcard pattern/list.

        Supports wildcards '*' and '?'. If a pattern expands to multiple files, one is chosen at random.
        Relative paths/patterns are resolved inside the sound resources directory. Absolute paths are used as-is.


        :param audio_path: Path, glob pattern or list of patterns / paths.
        :param volume: Relative volume (0.0–1.0) multiplied by the maximum volume.
        """
        if not self._enabled:
            return
        # Convert Path -> str (resolver expects string or list of strings).
        if isinstance(audio_path, Path):
            audio_path = str(audio_path)

        resolved = self._resolve_audio_file(audio_path)
        if not resolved or not resolved.exists():
            if resolved:  # Path does not exist.
                self._log.warning(f'Audio file not found: {resolved}')
            return
        self._play_file(resolved, volume)

    def play(self, sound_name: str, volume: float = 1.0):
        """Play a logical sound by its predefined name using preloaded file list.

        :param sound_name: Name of the logical sound (e.g., 'dizzy').
        :param volume: Relative volume (0.0 to 1.0, relative to max volume).
        """
        if not self._enabled:
            return
        if sound_name not in self._sound_names:
            self._log.debug(f'Unknown sound name requested: {sound_name}')
            return
        files = self._sound_files.get(sound_name, [])
        if not files:
            # Sound declared but no files found during preload.
            self._log.debug(f'Sound "{sound_name}" not available (no files).')
            return
        full_path = random.choice(files)
        self._play_file(full_path, volume)

    def say(self, text):
        """Speak text using text-to-speech
        
        :param text: Text to speak
        """
        if not self._enabled:
            return
            
        if not text or not text.strip():
            self._log.warning('Empty text provided for TTS')
            return
            
        try:
            self._log.info(f'Speaking text: "{text}"')
            subprocess.run([
                'spd-say', 
                '-l', self._tts_language, 
                text.strip()
            ], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            self._log.exception(f'Text-to-speech failed: {e}')
        except FileNotFoundError:
            self._log.error('spd-say command not found - install speech-dispatcher package')


class _SoundEffects:
    """Collection of sound effect callables.

    Provides an attribute per sound name. Access returns a callable that plays the sound.
    """
    __slots__ = ("_player",)

    def __init__(self, player: SoundPlayer):
        self._player = player

    def __getattr__(self, name: str):
        if name in self._player._sound_names:
            def _wrapper(volume: float = 1.0):
                return self._player.play(name, volume=volume)
            return _wrapper
        raise AttributeError(f"Sound '{name}' is not defined.")

    def list(self):  # Optional helper
        return list(self._player._sound_names)