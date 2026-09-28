"""Generate fictional documentation examples through the real message formatter."""
from __future__ import annotations
import argparse
from html import escape, unescape
from pathlib import Path
import re
from src.formatting import digest_message, message_chunks
from src.official_alerts import official_kyiv_alert_intro, official_kyiv_alert_state
from src.relevance import RelevanceRules

ROOT = Path(__file__).resolve().parents[1]


def examples() -> list[tuple[str, str, str]]:
    rules = RelevanceRules.from_yaml(ROOT / 'config.example.yaml')
    result = []
    for title, text, at in (
        ('Area report', 'БпЛА в напрямку обраної зони.', '2026-09-28T18:14:00+00:00'),
        ('Nearby report', 'БпЛА над сусідньою зоною, рух на захід.', '2026-09-28T18:16:00+00:00'),
        ('Local clear report', 'Обрана зона — чисто.', '2026-09-28T18:24:00+00:00'),
    ):
        decision = rules.classify(text)
        if decision.action != 'notify':
            raise ValueError(f'Demo must be selected by sample rules: {title}')
        label = '✅ Чисто / відбій' if decision.is_clear else '📍 Поруч' if decision.tier == 'nearby' else '📍'
        body = message_chunks('demo_source', len(result) + 1, at, text,
                              intro=f"{label} {', '.join(decision.places)}")[0]
        result.append((title, body, 'Fictional area and source.'))
    text = '🔴 Червоний рівень небезпеки\nДемонстраційний текст повідомлення.'
    state = official_kyiv_alert_state(text)
    result.append(('Official city status', message_chunks('va_kyiv', 4,
        '2026-09-28T18:10:00+00:00', text, intro=official_kyiv_alert_intro(state))[0],
        'Fictional post text; the official channel label shows the real format.'))
    result.append(('Quiet digest', digest_message([
        {'text': 'Київ: демонстраційне загальне повідомлення.', 'channel_username': 'demo_source', 'message_id': 5},
        {'text': 'Правий берег: демонстраційне оновлення.', 'channel_username': 'demo_source', 'message_id': 6},
    ]), 'Sent silently during an active city alert; excerpts open original posts in real notifications.'))
    result.append(('Edited report with reply context', message_chunks('demo_source', 7,
        '2026-09-28T18:24:00+00:00', 'Чисто', edited_at='2026-09-28T18:25:00+00:00',
        intro='✅ Чисто / відбій Обрана зона', context_message_id=1)[0],
        'The footer can show an edit time and a link to the parent post.'))
    return result


def plain(body: str) -> str:
    return unescape(re.sub(r'<[^>]+>', '', body))


def outputs() -> dict[Path, str]:
    rows = examples()
    markdown = '# Message examples\n\nAll posts, timestamps and areas below are fictional. These examples are generated through the app\'s real formatter. No private Telegram screenshot or source post is bundled. Notifications remain in Ukrainian.\n\n'
    for title, body, note in rows:
        markdown += f'## {title}\n\n{note}\n\n```text\n{plain(body)}\n```\n\n'
    markdown += 'The source label is a clickable original-post link in Telegram. Local “Чисто” reflects a source report, not an independently verified city all-clear. Run `python -m scripts.render_examples` to regenerate this page and the HTML mockup.\n'
    cards = []
    for index in (0, 2, 3):
        title, body, _ = rows[index]
        safe_body = re.sub(r'<a href="[^"]+">(.*?)</a>', r'<span class="link">\1</span>', body)
        cards.append(f'<article aria-label="{escape(title)}">{safe_body}</article>')
    page = '''<!doctype html>
<html lang="uk"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kyiv District Alerts — fictional message preview</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#edf2f7;color:#182b3b;font:17px/1.5 "Segoe UI",sans-serif;padding:36px}
main{max-width:940px;margin:auto}h1{margin:0;font-size:32px}p{color:#53697e;margin:8px 0 24px}
.phone{background:#dae6e2;border:1px solid #c4d5d2;border-radius:20px;overflow:hidden}
header{background:white;padding:18px 24px;font-weight:700}header small{display:block;font-weight:400;color:#64798a}
.messages{padding:24px;display:grid;gap:16px}article{white-space:pre-wrap;background:white;border-radius:14px;padding:20px 24px;max-width:730px;box-shadow:0 2px 5px #233d4210}.link{color:#2281bb}
footer{padding:16px 24px;background:#f5f9f7;color:#53697e;font-size:14px}
</style><main><h1>Kyiv District Alerts</h1><p>Telegram-style preview · fictional messages and areas</p>
<section class="phone"><header>Демонстраційна група<small>Вигадані приклади · український формат повідомлень</small></header><div class="messages">'''
    page += ''.join(cards)
    page += '</div><footer>Макет, не скриншот Telegram. Джерела й місцевості демонстраційні.</footer></section></main></html>\n'
    return {ROOT / 'docs/MESSAGES.md': markdown, ROOT / 'docs/demo.html': page}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for path, body in outputs().items():
        if args.check:
            if not path.exists() or path.read_text(encoding='utf-8') != body:
                parser.exit(1, f'Outdated example: {path.name}\n')
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding='utf-8')
    print('Documentation examples match the real formatter.' if args.check else 'Fictional examples generated.')


if __name__ == '__main__':
    main()
