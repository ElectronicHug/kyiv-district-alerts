# Message examples

All posts, timestamps and areas below are fictional. These examples are generated through the app's real formatter. No private Telegram screenshot or source post is bundled. Notifications remain in Ukrainian.

## Area report

Fictional area and source.

```text
📍 Обрана зона

БпЛА в напрямку обраної зони.

@demo_source ↗ · 28.09 · 21:14
```

## Nearby report

Fictional area and source.

```text
📍 Поруч Сусідня зона

БпЛА над сусідньою зоною, рух на захід.

@demo_source ↗ · 28.09 · 21:16
```

## Local clear report

Fictional area and source.

```text
✅ Чисто / відбій Обрана зона

Обрана зона — чисто.

@demo_source ↗ · 28.09 · 21:24
```

## Official city status

Fictional post text; the official channel label shows the real format.

```text
🔴 Київ · червоний рівень тривоги

🔴 Червоний рівень небезпеки
Демонстраційний текст повідомлення.

@va_kyiv ↗ · 28.09 · 21:10
```

## Quiet digest

Sent silently during an active city alert; excerpts open original posts in real notifications.

```text
🗺️ Київ та правий берег

• Київ: демонстраційне загальне повідомлення.
• Правий берег: демонстраційне оновлення.
```

## Edited report with reply context

The footer can show an edit time and a link to the parent post.

```text
✅ Чисто / відбій Обрана зона

Чисто

@demo_source ↗ · 28.09 · 21:24 · оновлено 28.09 · 21:25 · Контекст ↗
```

The source label is a clickable original-post link in Telegram. Local “Чисто” reflects a source report, not an independently verified city all-clear. Run `python -m scripts.render_examples` to regenerate this page and the HTML mockup.
