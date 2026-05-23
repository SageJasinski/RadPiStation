import os
import time
import glob
import random
import subprocess
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from mutagen.id3 import ID3NoHeaderError
from gpiozero import LED, Button

# --- CONFIGURATION ---
MUSIC_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Lofi")
BROADCAST_FREQ = "107.9"
STATION_NAME = "RAD-PI"
RADIO_TEXT = "RadPiStation - Backpack Radio"
SONGS_BETWEEN_DJ = 3
ESPEAK_VOICE = "en-us+m4"
ESPEAK_SPEED = "150"
ESPEAK_PITCH = "40"

# Hardware Setup
STATUS_LED_PIN = 17
POWER_SWITCH_PIN = 27

class HardwareController:
    def __init__(self):
        try:
            self.status_led = LED(STATUS_LED_PIN)
            self.power_switch = Button(POWER_SWITCH_PIN, pull_up=True)
            self.is_hardware_available = True
        except Exception as e:
            print(f"Warning: Hardware GPIO not available. Running in software-only mode. Error: {e}")
            self.is_hardware_available = False

    def turn_on_led(self):
        if self.is_hardware_available:
            self.status_led.on()

    def turn_off_led(self):
        if self.is_hardware_available:
            self.status_led.off()

    def is_switch_on(self):
        if not self.is_hardware_available:
            return True # Always run if no hardware switch is present
        # Assuming the switch connects the pin to GND when ON (pull_up=True)
        return self.power_switch.is_pressed


class QueueManager:
    def __init__(self, folder_path):
        self.folder_path = folder_path
        self.queue = []
        self._refresh_queue()

    def _refresh_queue(self):
        print("Refreshing and shuffling playlist...")
        search_pattern = os.path.join(self.folder_path, "*.mp3")
        self.queue = glob.glob(search_pattern)
        random.shuffle(self.queue)
        if not self.queue:
            print("Warning: No MP3 files found in the specified folder!")

    def get_next_track(self):
        if not self.queue:
            self._refresh_queue()
        if self.queue:
            return self.queue.pop(0)
        return None

class MetadataExtractor:
    @staticmethod
    def get_track_info(file_path):
        title = "Unknown Track"
        artist = "Unknown Artist"
        try:
            audio = EasyID3(file_path)
            title = audio.get("title", [title])[0]
            artist = audio.get("artist", [artist])[0]
        except ID3NoHeaderError:
            pass # Fallback to trying to read as basic MP3
        except Exception:
            pass

        if title == "Unknown Track":
            # Fallback to filename
            basename = os.path.basename(file_path)
            title = os.path.splitext(basename)[0].replace("_", " ")

        return {"title": title, "artist": artist}

class DJEngine:
    def __init__(self):
        self.temp_wav = "/tmp/dj_announcement.wav"

    def generate_announcement(self, previous_track_info, next_track_info):
        prev_title = previous_track_info.get("title", "a great track")
        prev_artist = previous_track_info.get("artist", "")
        next_title = next_track_info.get("title", "another great track")
        next_artist = next_track_info.get("artist", "")

        text = f"That was {prev_title} by {prev_artist}. You are listening to {STATION_NAME}. Coming up next is {next_title} by {next_artist}."
        print(f"DJ: {text}")

        # Generate WAV using espeak-ng
        cmd = [
            "espeak-ng",
            "-v", ESPEAK_VOICE,
            "-s", ESPEAK_SPEED,
            "-p", ESPEAK_PITCH,
            "-w", self.temp_wav,
            text
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return self.temp_wav

class BroadcastEngine:
    def __init__(self):
        self.pi_fm_process = None

    def _create_wav_header(self, sample_rate=44100, channels=2, bits_per_sample=16):
        import struct
        # 0xFFFFFFFF indicates unknown/infinite length for data chunks
        header = b'RIFF' + struct.pack('<I', 0xFFFFFFFF) + b'WAVE'
        byte_rate = sample_rate * channels * (bits_per_sample // 8)
        block_align = channels * (bits_per_sample // 8)
        header += b'fmt ' + struct.pack('<IHHIIHH', 16, 1, channels, sample_rate, byte_rate, block_align, bits_per_sample)
        header += b'data' + struct.pack('<I', 0xFFFFFFFF)
        return header

    def start_broadcaster(self):
        print(f"Starting pi_fm_rds on frequency {BROADCAST_FREQ}...")
        cmd = [
            "sudo", "pi_fm_rds",
            "-freq", BROADCAST_FREQ,
            "-pi", "FFFF",
            "-ps", STATION_NAME,
            "-rt", RADIO_TEXT,
            "-audio", "-"
        ]
        try:
            self.pi_fm_process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            # Write a generic continuous WAV header so pi_fm_rds never expects the file to end
            wav_header = self._create_wav_header()
            self.pi_fm_process.stdin.write(wav_header)
            self.pi_fm_process.stdin.flush()
        except FileNotFoundError:
            print("ERROR: pi_fm_rds not found.")
            self.pi_fm_process = subprocess.Popen(["python3", "-c", "import sys, time; sys.stdin.read()"], stdin=subprocess.PIPE)

    def play_audio(self, audio_path):
        if not self.pi_fm_process:
            return

        print(f"Playing: {audio_path}")
        # Convert audio to RAW headerless PCM matching our WAV header
        sox_cmd = ["sox", audio_path, "-t", "raw", "-r", "44100", "-c", "2", "-b", "16", "-e", "signed", "-"]
        sox_proc = subprocess.Popen(sox_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        
        # Stream the raw PCM seamlessly into the pipe
        try:
            while True:
                chunk = sox_proc.stdout.read(4096)
                if not chunk:
                    break
                self.pi_fm_process.stdin.write(chunk)
                self.pi_fm_process.stdin.flush()
        except BrokenPipeError:
            print("Broadcaster pipeline broken during playback. The transmitter may have crashed.")
            self.pi_fm_process = None
        
        sox_proc.wait()

    def stop_broadcaster(self):
        if self.pi_fm_process:
            self.pi_fm_process.terminate()
            self.pi_fm_process = None
            print("Stopped broadcasting.")

def main():
    print("RadPiStation Orchestrator Initializing...")
    hardware = HardwareController()
    queue = QueueManager(MUSIC_FOLDER)
    dj = DJEngine()
    broadcaster = BroadcastEngine()

    tracks_played_since_dj = 0
    previous_track_info = None

    while True:
        # Wait until the hardware switch is turned ON
        if not hardware.is_switch_on():
            hardware.turn_off_led()
            if broadcaster.pi_fm_process is not None:
                broadcaster.stop_broadcaster()
            time.sleep(1)
            continue

        # If switch is ON but broadcaster isn't running, start it
        if broadcaster.pi_fm_process is None:
            hardware.turn_on_led()
            broadcaster.start_broadcaster()
            tracks_played_since_dj = 0
            previous_track_info = None

        # Get next track
        track_path = queue.get_next_track()
        if not track_path:
            print("No tracks available. Retrying in 5 seconds...")
            time.sleep(5)
            continue

        track_info = MetadataExtractor.get_track_info(track_path)

        # DJ Announcement Logic
        if tracks_played_since_dj >= SONGS_BETWEEN_DJ and previous_track_info is not None:
            dj_audio_path = dj.generate_announcement(previous_track_info, track_info)
            broadcaster.play_audio(dj_audio_path)
            tracks_played_since_dj = 0

        # Play the actual track
        broadcaster.play_audio(track_path)
        
        previous_track_info = track_info
        tracks_played_since_dj += 1

if __name__ == "__main__":
    main()
