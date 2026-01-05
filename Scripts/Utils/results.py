# utils/results.py

def format_results(text_per_page):
    full_text = []
    clean_text = []
    stats_text = []

    total_text = 0
    total_images = 0
    total_tables = 0

    for page_key in sorted(text_per_page):
        page_text, _, images, tables, content = text_per_page[page_key]
        total_text += len("".join(content))
        total_images += len(images)
        total_tables += len(tables)

        full_text.append(f"\nСТРАНИЦА {int(page_key.split('_')[1]) + 1}")
        full_text.extend(content)

        clean_text.extend(content)

    stats_text.append(f"Страниц: {len(text_per_page)}")
    stats_text.append(f"Текст: {total_text} символов")
    stats_text.append(f"Изображений: {total_images}")
    stats_text.append(f"Таблиц: {total_tables}")

    return {
        "full": "\n".join(full_text),
        "clean": "\n".join(clean_text),
        "stats": "\n".join(stats_text)
    }