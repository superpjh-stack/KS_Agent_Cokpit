"""Protect the Korean React document before browser translation can mutate it.

Run in the app's dedicated virtual environment or during the Docker build.
The Streamlit wheel is pinned in requirements.lock; reject unknown HTML layouts.
"""
from pathlib import Path

HTML_TAG = '<html lang="ko" translate="no" class="notranslate">'
META = '<meta name="google" content="notranslate" />'


def prepare_html(html: str) -> str:
    if '<html lang="en">' not in html and HTML_TAG not in html:
        raise ValueError('Unexpected Streamlit HTML root; review the frontend patch.')
    if '<head>' not in html:
        raise ValueError('Streamlit HTML head not found.')
    html = html.replace('<html lang="en">', HTML_TAG, 1)
    if META not in html:
        html = html.replace('<head>', '<head>\n    ' + META, 1)
    return html


def main() -> None:
    import streamlit
    entry = Path(streamlit.__file__).parent / 'static' / 'index.html'
    original = entry.read_text(encoding='utf-8')
    prepared = prepare_html(original)
    if prepared != original:
        entry.write_text(prepared, encoding='utf-8')
    print('Korean frontend translation protection is ready.')


if __name__ == '__main__':
    main()
