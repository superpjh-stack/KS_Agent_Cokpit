from html.parser import HTMLParser
from pathlib import Path

import pytest
import streamlit

from scripts.prepare_frontend import HTML_TAG, META, prepare_html
from kwangsung_agent.voice import VoiceService


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def test_translation_protection_precedes_react_and_preserves_assets():
    original = (Path(streamlit.__file__).parent / 'static/index.html').read_text()
    before, after = Tags(), Tags()
    before.feed(original)
    protected = prepare_html(original)
    after.feed(protected)
    assert prepare_html(protected) == protected
    assert protected.count(META) == 1
    assert protected.index(META) < protected.index('<script')
    root = next(attrs for tag, attrs in after.tags if tag == 'html')
    assert root == {'lang': 'ko', 'translate': 'no', 'class': 'notranslate'}
    assert [(t, a) for t, a in before.tags if t in {'script', 'link'}] == [
        (t, a) for t, a in after.tags if t in {'script', 'link'}]


def test_unrecognized_frontend_fails_build_instead_of_silently_skipping():
    with pytest.raises(ValueError):
        prepare_html('<html><head></head></html>')


def test_voice_prompt_uses_only_kwangsung_manufacturing_terms():
    class Transcriptions:
        def __init__(self):
            self.request = None

        def create(self, **kwargs):
            self.request = kwargs
            return type('Transcript', (), {'text': '프레스 상태를 알려줘'})()

    transcriptions = Transcriptions()
    client = type('Client', (), {
        'audio': type('Audio', (), {'transcriptions': transcriptions})()
    })()

    assert VoiceService(client).transcribe(b'audio') == '프레스 상태를 알려줘'
    prompt = transcriptions.request['prompt']
    assert all(term in prompt for term in ('광성정밀', '프레스', '금형', '전착', '마킹'))
    assert all(term not in prompt for term in ('배추', '율무', '염도', '산도'))
