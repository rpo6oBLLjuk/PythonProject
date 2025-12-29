from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QSpinBox, QTextEdit,
    QTabWidget
)
from PySide6.QtGui import QFont
import os

from Scripts.PDFProcessor.pdf_converter import PDFConverterThread
from Scripts.Utils.results import format_results

class PDFConverterUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Конвертер")
        self.setMinimumSize(700, 500)
        self.setFont(QFont("Segoe UI", 10))
        self.pdf_path = ""
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        pdf_layout = QHBoxLayout()
        self.pdf_input = QLineEdit()
        self.pdf_input.setPlaceholderText("Выберите PDF файл...")
        browse_btn = QPushButton("Обзор")
        browse_btn.clicked.connect(self.browse_pdf)
        pdf_layout.addWidget(self.pdf_input)
        pdf_layout.addWidget(browse_btn)
        layout.addLayout(pdf_layout)

        pages_layout = QHBoxLayout()
        pages_layout.addWidget(QLabel("Макс. страниц:"))
        self.pages_spin = QSpinBox()
        self.pages_spin.setMinimum(1)
        self.pages_spin.setMaximum(1000)
        self.pages_spin.setValue(10)
        pages_layout.addWidget(self.pages_spin)
        layout.addLayout(pages_layout)

        self.run_btn = QPushButton("Конвертировать PDF")
        self.run_btn.clicked.connect(self.run_conversion)
        layout.addWidget(self.run_btn)

        self.tabs = QTabWidget()
        self.results_tab = QTextEdit()
        self.results_tab.setReadOnly(True)
        self.logs_tab = QTextEdit()
        self.logs_tab.setReadOnly(True)
        self.tabs.addTab(self.results_tab, "Результаты")
        self.tabs.addTab(self.logs_tab, "Логи")

        layout.addWidget(self.tabs)
        self.setLayout(layout)

    def browse_pdf(self):
        file_dialog = QFileDialog(self, "Выберите PDF файл", "", "PDF Files (*.pdf)")
        if file_dialog.exec():
            self.pdf_path = file_dialog.selectedFiles()[0]
            self.pdf_input.setText(self.pdf_path)

    def run_conversion(self):
        if not self.pdf_input.text() or not os.path.exists(self.pdf_input.text()):
            self.results_tab.setText("Ошибка: PDF файл не выбран или не существует.")
            return

        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Output")
        temp_dir = os.path.join(output_dir, "Temp")
        for folder in (output_dir, temp_dir):
            os.makedirs(folder, exist_ok=True)

        max_pages = self.pages_spin.value()

        self.thread = PDFConverterThread(self.pdf_input.text(), temp_dir, max_pages)
        self.thread.progress.connect(self.update_logs)
        self.thread.page_ready.connect(self.update_page)
        self.thread.finished_conversion.connect(self.on_conversion_finished)
        self.thread.start()
        self.run_btn.setEnabled(False)
        self.results_tab.setText("Конвертация в процессе...")

    def update_logs(self, message):
        self.logs_tab.append(message)

    def update_page(self, page_number, content):
        self.results_tab.append(f"\nСТРАНИЦА {page_number}")
        for line in content:
            self.results_tab.append(line)

    def on_conversion_finished(self, text_per_page):
        self.run_btn.setEnabled(True)
        if text_per_page:
            self.logs_tab.append("\nКонвертация завершена.")
        else:
            self.results_tab.append("Произошла ошибка при конвертации")

if __name__ == "__main__":
    app = QApplication([])
    window = PDFConverterUI()
    window.show()
    app.exec()
