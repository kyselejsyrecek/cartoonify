import logging
import glob
import importlib
import random
import subprocess
import sys
from pathlib import Path


class PlaySound(object):
    """Controls audio playback functionality"""

    def __init__(self, enabled=True):
        """Initialize PlaySound with optional enabled flag
        
        :param enabled: If False, all sound operations are silently ignored
        """
        self._logger = logging.getLogger(self.__class__.__name__)
        self._pa = None
        self._resources_path = Path(__file__).parent.parent.parent / 'sound'
        self._audio_backend = None  # Will be set in setup()
        self._pydub_available = False
        self._max_volume = 1.0
        self._alsa_numid = 4
        self._mp3_player = None
        self._ogg_player = None
        self._enabled = enabled
        
        if not self._enabled:
            self._logger.info('Sound system disabled')
    

    def setup(self, audio_backend=None, volume=1.0, alsa_numid=4, tts_language='cs'):
        """Setup audio system
        
        :param audio_backend: Preferred audio backend ('pulseaudio', 'alsa', 'native')
        :param volume: Maximum volume level (0.0 to 1.0)
        :param alsa_numid: ALSA mixer control numid for volume adjustment
        :param tts_language: Text-to-speech language code
        """
        if not self._enabled:
            return
            
        self._logger.info('Setting up audio system...')
        
        # Store volume settings
        self._max_volume = max(0.0, min(1.0, volume))  # Clamp between 0.0 and 1.0
        self._alsa_numid = alsa_numid
        self._tts_language = tts_language
        
        # Try to import pydub
        try:
            self._pydub = importlib.import_module('pydub')
            self._pydub_available = True
            self._logger.info('pydub is available')
        except ImportError:
            self._pydub_available = False
            self._logger.warning('pydub not available - MP3/OGG support limited')
        
        # Try to import wave module
        try:
            self._wave = importlib.import_module('wave')
            self._logger.info('wave module is available')
        except ImportError:
            self._wave = None
            self._logger.warning('wave module not available')
        
        # Detect and set preferred audio backend
        self._audio_backend = None
        
        # Define backend detection functions
        def try_pulseaudio():
            try:
                subprocess.run(['pulseaudio', '--check'], check=True, capture_output=True)
                self._logger.info('PulseAudio is available')
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                self._logger.warning('PulseAudio not available or not running')
                return False
        
        def try_alsa():
            try:
                subprocess.run(['aplay', '--version'], check=True, capture_output=True)
                self._logger.info('ALSA is available')
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                self._logger.warning('ALSA not available')
                return False
        
        def try_native():
            try:
                pyaudio_module = importlib.import_module('pyaudio')
                self._pa = pyaudio_module.PyAudio()
                self._logger.info('PyAudio initialized successfully')
                return True
            except (ImportError, Exception) as e:
                self._logger.warning(f'PyAudio initialization failed: {e}')
                self._pa = None
                return False
        
        # Try backends in order based on preference
        backends_to_try = []
        if audio_backend:
            # If specific backend requested, try that first
            backends_to_try.append(audio_backend)
            # Add remaining backends in default priority order
            default_order = ['pulseaudio', 'alsa', 'native']
            for backend in default_order:
                if backend != audio_backend:
                    backends_to_try.append(backend)
        else:
            # Use default priority order
            backends_to_try = ['pulseaudio', 'alsa', 'native']
        
        # Try each backend until one works
        for backend in backends_to_try:
            if backend == 'pulseaudio' and try_pulseaudio():
                self._audio_backend = 'pulseaudio'
                break
            elif backend == 'alsa' and try_alsa():
                self._audio_backend = 'alsa'
                break
            elif backend == 'native' and try_native():
                self._audio_backend = 'native'
                break
        
        if self._audio_backend is None:
            self._logger.error('No audio backend available')
        else:
            self._logger.info(f'Using audio backend: {self._audio_backend}')
            self._logger.info(f'Maximum volume set to: {self._max_volume:.1%}')
            
            # Set system volume if using PulseAudio or ALSA
            self._set_system_volume(self._max_volume)
            
            # Detect available audio players for ALSA backend
            if self._audio_backend == 'alsa':
                self._detect_audio_players()

    def close(self):
        """Cleanup audio resources"""
        if not self._enabled:
            return
            
        if self._pa is not None:
            self._pa.terminate()
            self._pa = None
        self._logger.info('Audio system closed')

    def _resolve_audio_file(self, audio_file):
        """Resolve audio file pattern to actual file path
        
        :param audio_file: Single file path/pattern or list of patterns
        :return: Path object of selected file or None if not found
        """
        all_files = []
        
        # Convert single item to list for uniform processing
        items = audio_file if isinstance(audio_file, (list, tuple)) else [audio_file]
        
        if not items:
            self._logger.warning('Empty audio file list provided')
            return None
        
        # Process each item (file or pattern)
        for item in items:
            if '*' in item or '?' in item:
                # Wildcard pattern - convert to full path and glob
                pattern = str(self._resources_path / item) if not Path(item).is_absolute() else item
                matched_files = glob.glob(pattern)
                all_files.extend(matched_files)
            else:
                # Regular file - convert to full path
                full_path = self._resources_path / item if not Path(item).is_absolute() else Path(item)
                all_files.append(str(full_path))
        
        if not all_files:
            self._logger.warning(f'No files found matching: {audio_file}')
            return None
        
        # Select random file
        selected_file = random.choice(all_files)
        file_count = len(all_files)
        
        if file_count > 1:
            self._logger.info(f'Randomly selected: {Path(selected_file).name} from {file_count} matching files')
        
        return Path(selected_file)

    def play(self, audio_file, volume=1.0):
        """Play audio file using available method
        
        :param audio_file: Path to audio file, filename with wildcards, or list of paths/filenames for random selection
        :param volume: Relative volume (0.0 to 1.0, relative to max volume)
        """
        if not self._enabled:
            return
            
        # Resolve file pattern to actual file
        full_path = self._resolve_audio_file(audio_file)
        if not full_path or not full_path.exists():
            if full_path:
                self._logger.warning(f'Audio file not found: {full_path}')
            return
        
        # Calculate final volume
        final_volume = self._max_volume * max(0.0, min(1.0, volume))
        
        # Set temporary volume if different from max
        if volume != 1.0 and self._audio_backend in ['pulseaudio', 'alsa']:
            self._set_system_volume(final_volume)
        
        # Use the detected backend
        if self._audio_backend == 'pulseaudio':
            self._play_pulseaudio(str(full_path))
        elif self._audio_backend == 'alsa':
            self._play_alsa(str(full_path))
        elif self._audio_backend == 'native':
            self._play_native(str(full_path), volume)
        else:
            self._logger.error('No audio backend available for playback')
            
        # Restore max volume if it was temporarily changed
        if volume != 1.0 and self._audio_backend in ['pulseaudio', 'alsa']:
            self._set_system_volume(self._max_volume)

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
            self._logger.warning(f'Failed to set system volume: {e}')

    def _play_alsa(self, audio_file):
        """Play audio file using ALSA
        
        :param audio_file: Path to audio file
        """
        try:
            file_path = Path(audio_file)
            extension = file_path.suffix.lower()
            
            if extension == '.pcm':
                # Play PCM file with aplay
                self._logger.info(f'Playing PCM file via ALSA: {audio_file}')
                subprocess.run([
                    'aplay', 
                    '-r', '44100',
                    '-f', 'S16_LE',
                    '-c', '1',
                    str(audio_file)
                ], check=True)
            elif extension == '.wav':
                # Play WAV file with aplay
                self._logger.info(f'Playing WAV file via ALSA: {audio_file}')
                subprocess.run(['aplay', str(audio_file)], check=True)
            elif extension == '.mp3':
                # Play MP3 file with detected player
                if self._mp3_player == 'mpg123':
                    self._logger.info(f'Playing MP3 file via mpg123: {audio_file}')
                    subprocess.run(['mpg123', '-q', str(audio_file)], check=True)
                elif self._mp3_player == 'ffplay':
                    self._logger.info(f'Playing MP3 file via ffplay: {audio_file}')
                    subprocess.run(['ffplay', '-nodisp', '-autoexit', str(audio_file)], check=True)
                else:
                    self._logger.error('No MP3 player available')
            elif extension == '.ogg':
                # Play OGG file with detected player
                if self._ogg_player == 'ogg123':
                    self._logger.info(f'Playing OGG file via ogg123: {audio_file}')
                    subprocess.run(['ogg123', '-q', str(audio_file)], check=True)
                elif self._ogg_player == 'ffplay':
                    self._logger.info(f'Playing OGG file via ffplay: {audio_file}')
                    subprocess.run(['ffplay', '-nodisp', '-autoexit', str(audio_file)], check=True)
                else:
                    self._logger.error('No OGG player available')
            else:
                self._logger.error(f'Unsupported audio format for ALSA: {extension}')
        except subprocess.CalledProcessError as e:
            self._logger.error(f'ALSA playback failed: {e}')
        except Exception as e:
            self._logger.error(f'ALSA playback error: {e}')

    def _play_pulseaudio(self, audio_file):
        """Play audio file using PulseAudio
        
        :param audio_file: Path to audio file (.pcm, .wav, .mp3, or .ogg, 44kHz)
        """
        try:
            file_path = Path(audio_file)
            extension = file_path.suffix.lower()
            
            if extension == '.pcm':
                # Play PCM file with paplay
                self._logger.info(f'Playing PCM file: {audio_file}')
                subprocess.run([
                    'paplay', 
                    '--rate=44000',
                    '--format=s16le',
                    '--channels=1',
                    str(audio_file)
                ], check=True)
            elif extension in ['.wav', '.mp3', '.ogg']:
                # Play WAV/MP3/OGG file with paplay
                self._logger.info(f'Playing {extension.upper()} file: {audio_file}')
                subprocess.run(['paplay', str(audio_file)], check=True)
            else:
                self._logger.error(f'Unsupported audio format: {extension}')
            
        except subprocess.CalledProcessError as e:
            self._logger.error(f'PulseAudio playback failed: {e}')
        except FileNotFoundError:
            self._logger.error('paplay command not found')

    def _play_native(self, audio_file, volume=1.0):
        """Play audio file using native Python PyAudio
        
        :param audio_file: Path to audio file (.pcm, .wav, .mp3, or .ogg, 44.1kHz)
        :param volume: Relative volume (0.0 to 1.0, relative to max volume)
        """
        if self._pa is None:
            self._logger.error('PyAudio not available for native playback')
            return

        try:
            file_path = Path(audio_file)
            extension = file_path.suffix.lower()
            
            # Calculate final volume for native playback
            final_volume = self._max_volume * max(0.0, min(1.0, volume))
            
            if extension == '.pcm':
                self._logger.info(f'Playing PCM file natively: {audio_file}')
                self._play_pcm_native(audio_file, final_volume)
            elif extension == '.wav':
                self._logger.info(f'Playing WAV file natively: {audio_file}')
                self._play_wav_native(audio_file, final_volume)
            elif extension == '.mp3':
                self._logger.info(f'Playing MP3 file natively: {audio_file}')
                self._play_mp3_native(audio_file, final_volume)
            elif extension == '.ogg':
                self._logger.info(f'Playing OGG file natively: {audio_file}')
                self._play_ogg_native(audio_file, final_volume)
            else:
                self._logger.error(f'Unsupported audio format: {extension}')
            
        except Exception as e:
            self._logger.error(f'Native playback failed: {e}')

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
            self._logger.error('wave module not available for WAV playback')
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
            self._logger.error('pydub not available for MP3 playback')
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
            self._logger.error(f'MP3 playback failed: {e}')

    def _play_ogg_native(self, ogg_file, volume=1.0):
        """Play OGG file using PyAudio via pydub with volume control"""
        if not self._pydub_available:
            self._logger.error('pydub not available for OGG playback')
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
            self._logger.error(f'OGG playback failed: {e}')

    def _detect_audio_players(self):
        """Detect available audio players for different formats"""
        # Detect MP3 player
        try:
            subprocess.run(['mpg123', '--version'], capture_output=True, check=True)
            self._mp3_player = 'mpg123'
            self._logger.info('Detected MP3 player: mpg123')
        except (FileNotFoundError, subprocess.CalledProcessError):
            try:
                subprocess.run(['ffplay', '-version'], capture_output=True, check=True)
                self._mp3_player = 'ffplay'
                self._logger.info('Detected MP3 player: ffplay')
            except (FileNotFoundError, subprocess.CalledProcessError):
                self._logger.warning('No MP3 player found (install mpg123 or ffmpeg)')
        
        # Detect OGG player
        try:
            subprocess.run(['ogg123', '--version'], capture_output=True, check=True)
            self._ogg_player = 'ogg123'
            self._logger.info('Detected OGG player: ogg123')
        except (FileNotFoundError, subprocess.CalledProcessError):
            try:
                subprocess.run(['ffplay', '-version'], capture_output=True, check=True)
                self._ogg_player = 'ffplay'
                self._logger.info('Detected OGG player: ffplay')
            except (FileNotFoundError, subprocess.CalledProcessError):
                self._logger.warning('No OGG player found (install vorbis-tools or ffmpeg)')

    # Sound definitions
    def awake(self):
        """Play awake sound"""
        self.play('awake*.*')

    def dizzy(self):
        """Play dizzy sound"""
        self.play('dizzy*.*')

    def error(self):
        """Play error sound"""
        self.play('error*.*')

    def greeting(self):
        """Play greeting sound"""
        self.play('greeting*.*')

    def ready(self):
        """Play ready sound"""
        self.play('ready*.*')

    def sad(self):
        """Play sad sound"""
        self.play('sad*.*')

    def capture(self):
        """Play sound of a capture"""
        self.play('capture*.*')

    def say(self, text):
        """Speak text using text-to-speech
        
        :param text: Text to speak
        """
        if not self._enabled:
            return
            
        if not text or not text.strip():
            self._logger.warning('Empty text provided for TTS')
            return
            
        try:
            self._logger.info(f'Speaking text: "{text}"')
            subprocess.run([
                'spd-say', 
                '-l', self._tts_language, 
                text.strip()
            ], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            self._logger.error(f'Text-to-speech failed: {e}')
        except FileNotFoundError:
            self._logger.error('spd-say command not found - install speech-dispatcher package')