import logging
import subprocess
import wave
import pyaudio
from pathlib import Path


class PlaySound(object):
    """Controls audio playback functionality"""

    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)
        self._pa = None
        self._resources_path = Path(__file__).parent.parent.parent / 'sound'

    def setup(self):
        """Setup audio system"""
        self._logger.info('Setting up audio system...')
        try:
            # Initialize PyAudio for native playback
            self._pa = pyaudio.PyAudio()
            self._logger.info('PyAudio initialized successfully')
        except Exception as e:
            self._logger.warning(f'PyAudio initialization failed: {e}')
            self._pa = None
        
        #if not fast_init:
        #    # Test PulseAudio availability
        #    try:
        #        subprocess.run(['pulseaudio', '--check'], check=True, capture_output=True)
        #        self._logger.info('PulseAudio is available')
        #    except (subprocess.CalledProcessError, FileNotFoundError):
        #        self._logger.warning('PulseAudio not available or not running')

    def play(self, audio_file):
        """Play audio file using available method
        
        :param audio_file: Path to audio file
        """
        # Check if file exists
        if not Path(audio_file).exists():
            self._logger.warning(f'Audio file not found: {audio_file}')
            return
        
        if self._pa is not None:
            self._play_native(audio_file)
        else:
            self._play_pulseaudio(audio_file)

    def _play_pulseaudio(self, audio_file):
        """Play audio file using PulseAudio
        
        :param audio_file: Path to audio file (.pcm or .wav, 44kHz)
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
            elif extension == '.wav':
                # Play WAV file with paplay
                self._logger.info(f'Playing WAV file: {audio_file}')
                subprocess.run(['paplay', str(audio_file)], check=True)
            else:
                self._logger.error(f'Unsupported audio format: {extension}')
            
        except subprocess.CalledProcessError as e:
            self._logger.error(f'PulseAudio playback failed: {e}')
        except FileNotFoundError:
            self._logger.error('paplay command not found')

    def _play_native(self, audio_file):
        """Play audio file using native Python PyAudio
        
        :param audio_file: Path to audio file (.pcm or .wav, 44kHz)
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
        with wave.open(str(wav_file), 'rb') as wf:
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