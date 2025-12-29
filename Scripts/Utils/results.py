# utils/results.py
import os
from datetime import datetime


def save_results(text_per_page, results_dir):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    full_path = os.path.join(results_dir, f"full_results_{timestamp}.txt")
    clean_path = os.path.join(results_dir, f"text_{timestamp}.txt")
    stats_path = os.path.join(results_dir, f"stats_{timestamp}.txt")

    total_text = 0
    total_images = 0
    total_tables = 0

    with open(full_path, "w", encoding="utf-8") as f:
        for page_key in sorted(text_per_page):
            page_text, _, images, tables, content = text_per_page[page_key]
            total_text += len("".join(content))
            total_images += len(images)
            total_tables += len(tables)

            f.write(f"\nСТРАНИЦА {int(page_key.split('_')[1]) + 1}\n")
            f.write("".join(content))

    with open(clean_path, "w", encoding="utf-8") as f:
        for page_key in sorted(text_per_page):
            f.write("".join(text_per_page[page_key][4]))

    with open(stats_path, "w", encoding="utf-8") as f:
        f.write(f"Страниц: {len(text_per_page)}\n")
        f.write(f"Текст: {total_text} символов\n")
        f.write(f"Изображений: {total_images}\n")
        f.write(f"Таблиц: {total_tables}\n")

    return {
        "full": full_path,
        "clean": clean_path,
        "stats": stats_path
    }
