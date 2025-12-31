import os

from Scripts.PDFProcessor.pdf_converter import convert_pdf_to_text
from Scripts.Utils.logger import Logger


# ================================
# Entry point only
# ================================

def main():
    pdf_path = "C:/Users/Admin/Documents/PDF_import/Azbuka_1_kl_1_ch_Goretskiy_compressed.pdf"
    max_pages = 12
    verbose = True

    project_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(project_dir, "Output")
    logs_dir = os.path.join(output_dir, "Logs")
    results_dir = os.path.join(output_dir, "Results")
    temp_dir = os.path.join(output_dir, "Temp")

    for folder in (output_dir, logs_dir, results_dir, temp_dir):
        os.makedirs(folder, exist_ok=True)

    logger = Logger(logs_dir, console=verbose)

    logger.info("Запуск PDF-конвертера")

    try:
        text_per_page = convert_pdf_to_text(
            pdf_path=pdf_path,
            temp_dir=temp_dir,
            logger=logger,
            max_pages=max_pages,
        )

        #results = save_results(text_per_page, results_dir)

        print("\nРезультаты обработки:")
        #for name, path in results.items():
        #    print(f"{name}: {path}")

        logger.success("Обработка завершена успешно")

    except Exception as e:
        logger.error("Критическая ошибка", e)


if __name__ == "__main__":
    main()