import logging
import subprocess
from pathlib import Path


class PlaySound(object):
    """Controls audio playback functionality"""

    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)
        self._pa = None
        self._resources_path = Path(__file__).parent.parent.parent / 'sound'
        self._audio_backend = None  # Will be set in setup()
        self._pydub_available = False

    def setup(self):
        """Setup audio system"""
        self._logger.info('Setting up audio system...')
        
        # Import audio libraries
        import importlib
        
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
        
        # Test PulseAudio availability (highest priority)
        try:
            subprocess.run(['pulseaudio', '--check'], check=True, capture_output=True)
            self._logger.info('PulseAudio is available')
            self._audio_backend = 'pulseaudio'
        except (subprocess.CalledProcessError, FileNotFoundError):
            self._logger.warning('PulseAudio not available or not running')
            
        # Test ALSA availability (second priority)
        if self._audio_backend is None:
            try:
                subprocess.run(['aplay', '--version'], check=True, capture_output=True)
                self._logger.info('ALSA is available')
                self._audio_backend = 'alsa'
            except (subprocess.CalledProcessError, FileNotFoundError):
                self._logger.warning('ALSA not available')
        
        # Try PyAudio for native playback (lowest priority)
        if self._audio_backend is None:
            try:
                pyaudio_module = importlib.import_module('pyaudio')
                self._pa = pyaudio_module.PyAudio()
                self._logger.info('PyAudio initialized successfully')
                self._audio_backend = 'native'
            except (ImportError, Exception) as e:
                self._logger.warning(f'PyAudio initialization failed: {e}')
                self._pa = None
        
        if self._audio_backend is None:
            self._logger.error('No audio backend available')
        else:
            self._logger.info(f'Using audio backend: {self._audio_backend}')

    def play(self, audio_file):
        """Play audio file using available method
        
        :param audio_file: Path to audio file
        """
        # Check if file exists
        if not Path(audio_file).exists():
            self._logger.warning(f'Audio file not found: {audio_file}')
            return
        
        # Use the detected backend
        if self._audio_backend == 'pulseaudio':
            self._play_pulseaudio(audio_file)
        elif self._audio_backend == 'alsa':
            self._play_alsa(audio_file)
        elif self._audio_backend == 'native':
            self._play_native(audio_file)
        else:
            self._logger.error('No audio backend available for playback')

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
                    '-r', '44000',
                    '-f', 'S16_LE',
                    '-c', '1',
                    str(audio_file)
                ], check=True)
            elif extension in ['.wav', '.mp3', '.ogg']:
                # Play audio file with aplay (requires format support)
                self._logger.info(f'Playing {extension.upper()} file via ALSA: {audio_file}')
                subprocess.run(['aplay', str(audio_file)], check=True)
            else:
                self._logger.error(f'Unsupported audio format for ALSA: {extension}')
                
        except subprocess.CalledProcessError as e:
            self._logger.error(f'ALSA playback failed: {e}')
        except FileNotFoundError:
            self._logger.error('aplay command not found')

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

    def _play_native(self, audio_file):
        """Play audio file using native Python PyAudio
        
        :param audio_file: Path to audio file (.pcm, .wav, or .mp3, 44kHz)
        """
        if self._pa is None:
            self._logger.error('PyAudio not available for native playback')
            return

        try:
            file_path = Path(audio_file)
            extension = file_path.suffix.lower()
            
            if extension == '.pcm':
                self._logger.info(f'Playing PCM file natively: {audio_file}')
                self._play_pcm_native(audio_file)
            elif extension == '.wav':
                self._logger.info(f'Playing WAV file natively: {audio_file}')
                self._play_wav_native(audio_file)
            elif extension == '.mp3':
                self._logger.info(f'Playing MP3 file natively: {audio_file}')
                self._play_mp3_native(audio_file)
            elif extension == '.ogg':
                self._logger.info(f'Playing OGG file natively: {audio_file}')
                self._play_ogg_native(audio_file)
            else:
                self._logger.error(f'Unsupported audio format: {extension}')
            
        except Exception as e:
            self._logger.error(f'Native playback failed: {e}')

    def _play_pcm_native(self, pcm_file):
        """Play PCM file using PyAudio"""
        chunk = 1024
        
        stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=44000,
            output=True
        )
        
        try:
            with open(pcm_file, 'rb') as f:
                data = f.read(chunk)
                while data:
                    stream.write(data)
                    data = f.read(chunk)
        finally:
            stream.stop_stream()
            stream.close()

    def _play_wav_native(self, wav_file):
        """Play WAV file using PyAudio"""
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
                    stream.write(data)
                    data = wf.readframes(chunk)
            finally:
                stream.stop_stream()
                stream.close()

    def _play_mp3_native(self, mp3_file):
        """Play MP3 file using PyAudio via pydub"""
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

    def _play_ogg_native(self, ogg_file):
        """Play OGG file using PyAudio via pydub"""
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

    def awake(self):
        """Play awake sound"""
        self.play(self._resources_path / 'awake.wav')

    def dizzy(self):
        """Play dizzy sound"""
        self.play(self._resources_path / 'dizzy.wav')

    def greeting(self):
        """Play greeting sound"""
        self.play(self._resources_path / 'greeting.wav')

    def ready(self):
        """Play ready sound"""
        self.play(self._resources_path / 'ready.wav')

    def sad(self):
        """Play sad sound"""
        self.play(self._resources_path / 'sad.wav')

    def shutter(self):
        """Play shutter sound"""
        self.play(self._resources_path / 'shutter.wav')

    def close(self):
        """Cleanup audio resources"""
        if self._pa is not None:
            self._pa.terminate()
            self._pa = None
        self._logger.info('Audio system closed')