import openai
import os
import pyaudio
from dotenv import load_dotenv
from assemblyai.streaming.v3 import (
    BeginEvent,
    RealTimeError,
    RealTimeEvents,
    RealTimeParameters,
    RealTimeTranscriber,
    TurnEvent,
)
import deepl
from pydub import AudioSegment
from pydub.playback import play
import time

load_dotenv()

READ_TRANSLATION = False
TARGET_LANG = os.environ.get("TARGET_LANG", "ES")
SAMPLE_RATE = 16_000
FRAMES_PER_BUFFER = 800  # 50ms at 16kHz

translator = deepl.Translator(os.environ["DEEPL_API_KEY"])
openai.api_key = os.environ["OPENAI_API_KEY"]

client = None
if READ_TRANSLATION:
    client = openai.OpenAI()


def on_begin(_, event: BeginEvent):
    "This function is called when the connection has been established."
    print("Session ID:", event.id)


def gen_speech_file(speech_file_path, text):
    st = time.time()
    response = client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=text
    )
    response.stream_to_file(speech_file_path)
    print('to speech for:', (time.time() - st), 'sec')
    return speech_file_path


def play_audio(speech_file_path):
    audio_clip = AudioSegment.from_mp3(speech_file_path)
    play(audio_clip)


def on_turn(_, event: TurnEvent):
    "This function is called when a new transcript has been received."

    if not event.transcript:
        return

    if event.end_of_turn:
        result = translator.translate_text(event.transcript, target_lang=TARGET_LANG)
        print(event.transcript, end="\r\n")
        print(f"{TARGET_LANG}: " + result.text)

        if READ_TRANSLATION:
            speech_file_path = "speech.mp3"
            gen_speech_file(speech_file_path, result.text)
            play_audio(speech_file_path)
    else:
        print(event.transcript, end="\r")


def on_terminated(*_):
    "This function is called when the connection has been closed."
    print("Closing Session")


def on_error(transcriber, error: RealTimeError):
    "This function is called when an error occurs."
    print("An error occured:", error)


def microphone_chunks():
    "Yields raw PCM audio chunks read from the default microphone."
    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=FRAMES_PER_BUFFER,
    )
    try:
        while True:
            yield stream.read(FRAMES_PER_BUFFER, exception_on_overflow=False)
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()


transcriber = RealTimeTranscriber(api_key=os.environ["ASSEMBLY_API_KEY"])
transcriber.on(RealTimeEvents.Begin, on_begin)
transcriber.on(RealTimeEvents.Turn, on_turn)
transcriber.on(RealTimeEvents.Termination, on_terminated)
transcriber.on(RealTimeEvents.Error, on_error)

# Start the connection
transcriber.connect(RealTimeParameters(sample_rate=SAMPLE_RATE, format_turns=True))

try:
    # Press CTRL+C to abort
    transcriber.stream(microphone_chunks())
except KeyboardInterrupt:
    pass
finally:
    transcriber.disconnect(terminate=True)
