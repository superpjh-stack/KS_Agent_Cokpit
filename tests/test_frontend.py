from html.parser import HTMLParser
from pathlib import Path

import pytest
import streamlit

from scripts.prepare_frontend import HTML_TAG, META, prepare_html


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
