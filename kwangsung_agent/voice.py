"""On-demand speech conversion; recordings and playback bytes stay in session memory."""
from typing import Any

MAX_RECORDING_BYTES = 20 * 1024 * 1024


class VoiceService:
    def __init__(self, client: Any):
        self.client = client

    def transcribe(self, recording: bytes) -> str:
        if not recording or len(recording) > MAX_RECORDING_BYTES:
            raise ValueError("녹음이 비어 있거나 너무 큽니다. 20MB 이하로 다시 녹음하세요.")
        response = self.client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe", file=("question.wav", recording, "audio/wav"),
            language="ko", response_format="json",
            prompt=(
                "금속 가공품 제조 업무 질문. 광성정밀, 프레스, 금형, 전착, 마킹, "
                "수입검사, 출하검사, 소재 LOT, 작업지시, 예지보전."
            ),
        )
        text = response.text.strip()
        if not text:
            raise ValueError("말소리를 인식하지 못했습니다. 다시 녹음하거나 글로 입력하세요.")
        return text

    def speak(self, text: str) -> bytes:
        if not text.strip():
            raise ValueError("읽을 답변이 없습니다.")
        if len(text) > 4000:
            raise ValueError("답변이 너무 깁니다. 짧게 다시 질문한 뒤 음성으로 들어주세요.")
        with self.client.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts", voice="coral", input=text,
            instructions="한국어로 차분하고 또렷하게 읽으세요. 숫자와 단위는 천천히 읽으세요.",
            response_format="mp3",
        ) as response:
            audio = response.read()
        if not audio:
            raise ValueError("음성을 만들지 못했습니다. 다시 시도하세요.")
        return audio
