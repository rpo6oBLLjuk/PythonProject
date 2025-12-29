from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QSpinBox, QTextEdit,
    QTabWidget
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt
import os

from Scripts.PDFProcessor.pdf_converter import PDFConverterThread

class PDFConverterUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Конвертер")
        self.setMinimumSize(700, 500)
        self.setFont(QFont("Segoe UI", 10))
        self.pdf_path = ""
        self.pages_content = {}
        self.current_page = 1
        self.total_pages = 0
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

        # Навигация по страницам
        nav_layout = QHBoxLayout()
        self.prev_btn = QPushButton("←")
        self.prev_btn.clicked.connect(self.show_prev_page)
        self.next_btn = QPushButton("→")
        self.next_btn.clicked.connect(self.show_next_page)
        self.page_label = QLabel("Страница: 0/0")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.page_label)
        nav_layout.addWidget(self.next_btn)
        layout.addLayout(nav_layout)

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

        self.pages_content = {}
        self.current_page = 1
        self.total_pages = 0
        self.page_label.setText("Страница: 0/0")

        self.thread = PDFConverterThread(self.pdf_input.text(), temp_dir, max_pages)
        self.thread.progress.connect(self.update_logs)
        self.thread.page_ready.connect(self.add_page)
        self.thread.finished_conversion.connect(self.on_conversion_finished)
        self.thread.start()
        self.run_btn.setEnabled(False)
        self.results_tab.setText("Конвертация в процессе...")

    def update_logs(self, message):
        self.logs_tab.append(message)

    def add_page(self, page_number, content):
        self.pages_content[page_number] = content
        self.total_pages = max(self.pages_content.keys())
        if page_number == 1:
            self.display_page(1)

    def display_page(self, page_number):
        if page_number in self.pages_content:
            self.results_tab.clear()
            for line in self.pages_content[page_number]:
                self.results_tab.append(line)
            self.current_page = page_number
            self.page_label.setText(f"Страница: {self.current_page}/{self.total_pages}")

    def show_prev_page(self):
        if self.current_page > 1:
            self.display_page(self.current_page - 1)

    def show_next_page(self):
        if self.current_page < self.total_pages:
            self.display_page(self.current_page + 1)

    def on_conversion_finished(self, text_per_page):
        self.run_btn.setEnabled(True)
        if text_per_page:
            self.logs_tab.append("\nКонвертация завершена.")
        else:
            self.results_tab.setText("Произошла ошибка при конвертации")

if __name__ == "__main__":
    app = QApplication([])
    window = PDFConverterUI()
    window.show()
    app.exec()
