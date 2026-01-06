from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QSpinBox, QTextEdit,
    QTabWidget, QComboBox, QCheckBox, QGroupBox, QTreeWidget,
    QTreeWidgetItem, QSplitter, QMenu, QMessageBox
)
from PySide6.QtGui import QFont, QTextCharFormat, QColor, QTextCursor, QAction
from PySide6.QtCore import Qt, QDateTime

from Scripts.PDFProcessor.pdf_converter import PdfParseThread
from PyPDF2 import PdfReader

import os
import json
import sys


class PDFConverterUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Converter")
        self.setMinimumSize(1000, 650)
        self.setFont(QFont("Segoe UI", 10))

        self.pdf_path = ""
        self.monochrome_mode = False

        # Новая модель: документ -> chapters[]
        self.structured_data = {}
        self.current_chapter_idx = None
        self.current_paragraph_idx = None

        # Цвета (для тёмной вкладки форматированного вывода)
        self.type_colors = {
            "title": QColor("#ffffff"),
            "header": QColor("#ffd166"),
            "text": QColor("#e0e0e0"),
            "muted": QColor("#95a5a6"),
        }

        self.setup_ui()

    # -----------------------------
    # UI setup
    # -----------------------------
    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Верхняя панель: выбор файла и настройки
        top_group = QGroupBox("Параметры конвертации")
        top_layout = QVBoxLayout()
        top_layout.setSpacing(8)

        # Выбор файла
        file_layout = QHBoxLayout()
        self.pdf_input = QLineEdit()
        self.pdf_input.setPlaceholderText("Выберите PDF файл...")
        browse_btn = QPushButton("Обзор")
        browse_btn.clicked.connect(self.browse_pdf)

        file_layout.addWidget(self.pdf_input)
        file_layout.addWidget(browse_btn)
        top_layout.addLayout(file_layout)

        # Настройки
        settings_layout = QHBoxLayout()
        settings_layout.setSpacing(8)

        settings_layout.addWidget(QLabel("Макс. страниц:"))
        self.pages_spin = QSpinBox()
        self.pages_spin.setMinimum(1)
        self.pages_spin.setMaximum(1000)
        self.pages_spin.setValue(10)
        settings_layout.addWidget(self.pages_spin)

        settings_layout.addWidget(QLabel("Формат вывода:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Текст с разметкой", "Сырой текст", "JSON"])
        self.format_combo.currentIndexChanged.connect(self.on_format_changed)
        settings_layout.addWidget(self.format_combo)

        self.monochrome_checkbox = QCheckBox("Однотонный вывод")
        self.monochrome_checkbox.toggled.connect(self.toggle_monochrome_mode)
        settings_layout.addWidget(self.monochrome_checkbox)

        settings_layout.addStretch()

        self.save_btn = QPushButton("💾 Сохранить результаты")
        self.save_btn.clicked.connect(self.save_results)
        self.save_btn.setEnabled(False)
        settings_layout.addWidget(self.save_btn)

        top_layout.addLayout(settings_layout)
        top_group.setLayout(top_layout)
        main_layout.addWidget(top_group)

        # Кнопка запуска
        self.run_btn = QPushButton("🔍 Начать конвертацию и анализ")
        self.run_btn.clicked.connect(self.on_run_button_clicked)
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #2980b9; }
            QPushButton:disabled { background-color: #bdc3c7; }
        """)
        main_layout.addWidget(self.run_btn)

        # Основная область с разделителем
        splitter = QSplitter(Qt.Horizontal)

        # Левая панель: дерево структуры
        self.structure_tree = QTreeWidget()
        self.structure_tree.setHeaderLabel("Структура документа")
        self.structure_tree.setMinimumWidth(300)
        self.structure_tree.itemClicked.connect(self.on_tree_item_clicked)

        self.structure_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.structure_tree.customContextMenuRequested.connect(self.show_tree_context_menu)

        splitter.addWidget(self.structure_tree)

        # Правая панель: вкладки
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        self.tabs = QTabWidget()

        self.results_tab = QTextEdit()
        self.results_tab.setReadOnly(True)
        self.results_tab.setFont(QFont("Consolas", 10))

        self.raw_tab = QTextEdit()
        self.raw_tab.setReadOnly(True)
        self.raw_tab.setFont(QFont("Consolas", 10))

        self.logs_tab = QTextEdit()
        self.logs_tab.setReadOnly(True)
        self.logs_tab.setFont(QFont("Consolas", 9))

        self.tabs.addTab(self.results_tab, "📄 Форматированный текст")
        self.tabs.addTab(self.raw_tab, "📝 Сырые данные")
        self.tabs.addTab(self.logs_tab, "📊 Логи")

        self.is_running = False

        right_layout.addWidget(self.tabs)

        splitter.addWidget(right_widget)
        splitter.setSizes([330, 670])
        main_layout.addWidget(splitter)

        # Статусная строка
        self.status_label = QLabel("Готово")
        self.status_label.setStyleSheet("color: #7f8c8d; padding: 5px; border-top: 1px solid #ddd;")
        main_layout.addWidget(self.status_label)

        self.setLayout(main_layout)

        # Стили вкладок по умолчанию
        self.apply_default_styles()

    def apply_default_styles(self):
        self.results_tab.setStyleSheet("""
            QTextEdit {
                background-color: #2c3e50;
                color: #ffffff;
                font-family: Consolas;
                font-size: 10pt;
            }
        """)
        self.raw_tab.setStyleSheet("""
            QTextEdit {
                background-color: #ffffff;
                color: #000000;
                font-family: Consolas;
                font-size: 10pt;
            }
        """)
        self.logs_tab.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                color: #212529;
                font-family: Consolas;
                font-size: 9pt;
            }
        """)

    # -----------------------------
    # Toggles / events
    # -----------------------------
    def toggle_monochrome_mode(self, checked: bool):
        self.monochrome_mode = checked
        self.redraw_current_paragraph()

    def on_format_changed(self):
        self.redraw_current_paragraph()

    def redraw_current_paragraph(self):
        if self.current_chapter_idx is None or self.current_paragraph_idx is None:
            return
        self.display_paragraph(self.current_chapter_idx, self.current_paragraph_idx)

    def on_run_button_clicked(self):
        if self.is_running:
            self.cancel_conversion()
        else:
            self.run_conversion()

    def cancel_conversion(self):
        if hasattr(self, "thread") and self.thread is not None and self.thread.isRunning():
            current_time = QDateTime.currentDateTime().toString("HH:mm:ss")
            self.logs_tab.append(f"[{current_time}] ⛔ Пользователь прервал конвертацию.")
            self.status_label.setText("⛔ Конвертация прервана пользователем")

            # QThread: requestInterruption + terminate fallback
            try:
                self.thread.requestInterruption()
            except Exception:
                pass

            # Если твой PdfParseThread не проверяет isInterruptionRequested(),
            # то requestInterruption ничего не даст. Тогда terminate.
            try:
                self.thread.terminate()
                self.thread.wait(2000)
            except Exception:
                pass

        self.save_btn.setEnabled(bool((self.structured_data or {}).get("chapters")))
        self.set_running_state(False)

    # -----------------------------
    # File selection / run
    # -----------------------------
    def browse_pdf(self):
        file_dialog = QFileDialog(self, "Выберите PDF файл", "", "PDF Files (*.pdf)")
        if file_dialog.exec():
            self.pdf_path = file_dialog.selectedFiles()[0]
            self.pdf_input.setText(self.pdf_path)

            try:
                reader = PdfReader(self.pdf_path)
                page_count = len(reader.pages)

                self.pages_spin.setMaximum(page_count)
                self.pages_spin.setValue(page_count)

                self.status_label.setText(
                    f"Файл загружен: {os.path.basename(self.pdf_path)} ({page_count} стр.)"
                )
            except Exception as e:
                self.status_label.setText(f"Ошибка чтения PDF: {str(e)}")

    def run_conversion(self):
        if not self.pdf_input.text() or not os.path.exists(self.pdf_input.text()):
            self.results_tab.setText("❌ Ошибка: PDF файл не выбран или не существует.")
            return

        # Temp dir
        script_dir = os.path.dirname(os.path.abspath(__file__))
        temp_dir = os.path.join(script_dir, "Temp")
        os.makedirs(temp_dir, exist_ok=True)

        max_pages = self.pages_spin.value()

        # Reset UI state
        self.structured_data = {}
        self.current_chapter_idx = None
        self.current_paragraph_idx = None
        self.structure_tree.clear()
        self.results_tab.clear()
        self.raw_tab.clear()
        self.logs_tab.clear()
        self.save_btn.setEnabled(False)

        # Lock UI
        self.status_label.setText("Начата конвертация...")

        # Logs
        current_time = QDateTime.currentDateTime().toString("HH:mm:ss")
        self.logs_tab.append(f"[{current_time}] Запуск анализа PDF -> главы/параграфы")
        self.logs_tab.append(f"[{current_time}] Файл: {os.path.basename(self.pdf_path)}")
        self.logs_tab.append(f"[{current_time}] Макс. страниц: {max_pages}")
        self.logs_tab.append("-" * 50)

        # Thread
        self.thread = PdfParseThread(self.pdf_input.text(), temp_dir, max_pages)
        self.thread.progress.connect(self.update_logs)
        self.thread.page_ready.connect(self.process_page_data)        # теперь только прогресс/совместимость
        self.thread.finished.connect(self.on_conversion_finished)
        self.thread.start()

        self.set_running_state(True)

    def update_logs(self, message: str):
        current_time = QDateTime.currentDateTime().toString("HH:mm:ss")
        self.logs_tab.append(f"[{current_time}] {message}")

        cursor = self.logs_tab.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.logs_tab.setTextCursor(cursor)

    def process_page_data(self, page_num: int, page_json: str):
        """
        В новой модели структура строится по finished (chapters),
        page_ready используем только для логов/прогресса.
        """
        try:
            # иногда поток может прислать что угодно; UI не должен падать
            _ = page_json  # оставим на будущее, если захочешь показывать статистику страниц
            current_time = QDateTime.currentDateTime().toString("HH:mm:ss")
            self.logs_tab.append(f"[{current_time}] Страница {page_num} обработана")
        except Exception as e:
            current_time = QDateTime.currentDateTime().toString("HH:mm:ss")
            self.logs_tab.append(f"[{current_time}] ❌ Ошибка progress страницы {page_num}: {str(e)}")

    # -----------------------------
    # Tree building (chapters -> paragraphs -> headers/text)
    # -----------------------------
    def build_structure_tree_from_chapters(self):
        self.structure_tree.clear()

        chapters = (self.structured_data or {}).get("chapters", [])
        if not chapters:
            root = QTreeWidgetItem(self.structure_tree)
            root.setText(0, "❌ Структура пуста (chapters=0)")
            root.setForeground(0, QColor("#e74c3c"))
            return

        for c_idx, ch in enumerate(chapters):
            title = (ch.get("title") or f"Глава {c_idx + 1}").strip()
            paragraphs = ch.get("paragraphs") or []

            ch_item = QTreeWidgetItem(self.structure_tree)
            ch_item.setText(0, f"📘 {title}  ({len(paragraphs)})")
            ch_item.setData(0, Qt.UserRole, {"type": "chapter", "chapter_idx": c_idx})

            # Параграфы как дети главы
            for p_idx, p in enumerate(paragraphs):
                p_headers = p.get("headers") or []
                p_text = (p.get("text") or "").strip()

                # Имя параграфа: первый заголовок, иначе превью текста
                if p_headers:
                    name = str(p_headers[0]).strip()
                else:
                    name = p_text[:70].replace("\n", " ").strip() if p_text else f"Параграф {p_idx + 1}"

                if len(name) > 100:
                    name = name[:100] + "..."

                p_item = QTreeWidgetItem(ch_item)
                p_item.setText(0, f"📄 {p_idx + 1}. {name}")
                p_item.setData(0, Qt.UserRole, {
                    "type": "paragraph",
                    "chapter_idx": c_idx,
                    "paragraph_idx": p_idx
                })

            # по клику глава будет раскрыта, но пусть первая сразу раскрыта
            if c_idx == 0:
                ch_item.setExpanded(True)

    def on_tree_item_clicked(self, item):
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        t = data.get("type")
        if t == "chapter":
            item.setExpanded(not item.isExpanded())
            return

        if t == "paragraph":
            self.display_paragraph(data["chapter_idx"], data["paragraph_idx"])
            return

    # -----------------------------
    # Context menu
    # -----------------------------
    def show_tree_context_menu(self, position):
        item = self.structure_tree.itemAt(position)
        if not item:
            return

        data = item.data(0, Qt.UserRole)
        if not data:
            return

        menu = QMenu()

        if data.get("type") == "paragraph":
            c_idx = data["chapter_idx"]
            p_idx = data["paragraph_idx"]

            open_action = QAction("Открыть параграф", self)
            open_action.triggered.connect(lambda: self.display_paragraph(c_idx, p_idx))
            menu.addAction(open_action)

            copy_action = QAction("Копировать текст параграфа", self)
            copy_action.triggered.connect(lambda: self.copy_paragraph_text(c_idx, p_idx))
            menu.addAction(copy_action)

            export_action = QAction("Экспортировать параграф…", self)
            export_action.triggered.connect(lambda: self.export_paragraph(c_idx, p_idx))
            menu.addAction(export_action)

        menu.addSeparator()

        expand_all_action = QAction("Развернуть всё", self)
        expand_all_action.triggered.connect(self.structure_tree.expandAll)
        menu.addAction(expand_all_action)

        collapse_all_action = QAction("Свернуть всё", self)
        collapse_all_action.triggered.connect(self.structure_tree.collapseAll)
        menu.addAction(collapse_all_action)

        menu.exec(self.structure_tree.mapToGlobal(position))

    def copy_paragraph_text(self, chapter_idx: int, paragraph_idx: int):
        p = self.get_paragraph(chapter_idx, paragraph_idx)
        if not p:
            return
        text = (p.get("text") or "").strip()
        if text:
            QApplication.clipboard().setText(text)
            self.status_label.setText("Текст параграфа скопирован в буфер обмена")

    # -----------------------------
    # Display paragraph
    # -----------------------------
    def get_chapter(self, chapter_idx: int):
        chapters = (self.structured_data or {}).get("chapters", [])
        if 0 <= chapter_idx < len(chapters):
            return chapters[chapter_idx]
        return None

    def get_paragraph(self, chapter_idx: int, paragraph_idx: int):
        ch = self.get_chapter(chapter_idx)
        if not ch:
            return None
        paras = ch.get("paragraphs") or []
        if 0 <= paragraph_idx < len(paras):
            return paras[paragraph_idx]
        return None

    def display_paragraph(self, chapter_idx: int, paragraph_idx: int):
        ch = self.get_chapter(chapter_idx)
        p = self.get_paragraph(chapter_idx, paragraph_idx)
        if not ch or not p:
            return

        self.current_chapter_idx = chapter_idx
        self.current_paragraph_idx = paragraph_idx

        fmt = self.format_combo.currentText()
        if fmt == "Текст с разметкой":
            self.display_formatted_paragraph(ch, p, chapter_idx, paragraph_idx)
        elif fmt == "Сырой текст":
            self.display_raw_paragraph(ch, p, chapter_idx, paragraph_idx)
        else:
            self.display_json_paragraph(ch, p, chapter_idx, paragraph_idx)

    def display_formatted_paragraph(self, ch: dict, p: dict, chapter_idx: int, paragraph_idx: int):
        self.apply_default_styles()
        self.results_tab.clear()

        cursor = self.results_tab.textCursor()

        title_fmt = QTextCharFormat()
        title_fmt.setFontWeight(QFont.Bold)
        title_fmt.setFontPointSize(12)
        title_fmt.setForeground(QColor("#ffffff"))

        hdr_fmt = QTextCharFormat()
        hdr_fmt.setFontWeight(QFont.Bold)
        hdr_fmt.setFontPointSize(11)
        hdr_fmt.setForeground(QColor("#ffd166") if not self.monochrome_mode else QColor("#ffffff"))

        text_fmt = QTextCharFormat()
        text_fmt.setForeground(QColor("#e0e0e0") if not self.monochrome_mode else QColor("#ffffff"))

        muted_fmt = QTextCharFormat()
        muted_fmt.setForeground(QColor("#95a5a6") if not self.monochrome_mode else QColor("#ffffff"))

        ch_title = (ch.get("title") or f"Глава {chapter_idx + 1}").strip()
        cursor.insertText(f"{ch_title}\n", title_fmt)
        cursor.insertText(f"Параграф {paragraph_idx + 1}\n", muted_fmt)
        cursor.insertText(f"{'=' * 60}\n\n", muted_fmt)

        # Заголовки: как часть текста, просто форматированием
        headers = p.get("headers") or []
        for h in headers:
            ht = str(h).strip()
            if ht:
                cursor.insertText(ht + "\n", hdr_fmt)
        if headers:
            cursor.insertText("\n", hdr_fmt)

        # Текст
        text = (p.get("text") or "").strip()
        if text:
            cursor.insertText(text + "\n", text_fmt)
        else:
            cursor.insertText("(пусто)\n", muted_fmt)

        self.results_tab.moveCursor(QTextCursor.Start)
        self.tabs.setCurrentWidget(self.results_tab)

    def display_raw_paragraph(self, ch: dict, p: dict, chapter_idx: int, paragraph_idx: int):
        self.apply_default_styles()

        ch_title = (ch.get("title") or f"Глава {chapter_idx + 1}").strip()
        headers = p.get("headers") or []
        text = (p.get("text") or "").strip()

        out = []
        out.append(f"[CHAPTER] {ch_title}")
        out.append(f"[PARAGRAPH] {paragraph_idx + 1}")
        out.append("")
        if headers:
            out.append("[HEADERS]")
            out.extend([f"- {str(h).strip()}" for h in headers])
            out.append("")
        out.append("[TEXT]")
        out.append(text if text else "(пусто)")

        self.raw_tab.setText("\n".join(out))
        self.tabs.setCurrentWidget(self.raw_tab)

    def display_json_paragraph(self, ch: dict, p: dict, chapter_idx: int, paragraph_idx: int):
        self.apply_default_styles()

        payload = {
            "chapter_index": chapter_idx,
            "paragraph_index": paragraph_idx,
            "chapter": ch,
            "paragraph": p,
        }
        self.raw_tab.setText(json.dumps(payload, ensure_ascii=False, indent=2))
        self.tabs.setCurrentWidget(self.raw_tab)

    # -----------------------------
    # Finished
    # -----------------------------
    def on_conversion_finished(self, all_data_json: str):
        self.set_running_state(False)

        current_time = QDateTime.currentDateTime().toString("HH:mm:ss")

        try:
            self.structured_data = json.loads(all_data_json) if all_data_json.strip() else {}

            # Unlock UI
            self.run_btn.setEnabled(True)
            self.run_btn.setText("🔍 Начать конвертацию и анализ")

            chapters = (self.structured_data or {}).get("chapters", [])
            ch_count = len(chapters)
            p_count = sum(len(ch.get("paragraphs") or []) for ch in chapters)

            self.save_btn.setEnabled(bool(chapters))

            self.status_label.setText(f"✅ Готово. Глав: {ch_count}, параграфов: {p_count}")

            self.logs_tab.append(f"[{current_time}] ✅ Анализ завершён.")
            self.logs_tab.append(f"[{current_time}] Глав: {ch_count}, параграфов: {p_count}")

            # Build tree
            self.build_structure_tree_from_chapters()

            # Auto-open first paragraph
            if chapters and (chapters[0].get("paragraphs") or []):
                self.display_paragraph(0, 0)

        except Exception as e:
            error_msg = f"Ошибка при завершении конвертации: {str(e)}"
            self.logs_tab.append(f"[{current_time}] ❌ {error_msg}")
            self.status_label.setText(f"❌ {error_msg}")

            self.run_btn.setEnabled(True)
            self.run_btn.setText("🔍 Начать конвертацию и анализ")
            self.save_btn.setEnabled(False)

            self.set_running_state(False)

    def set_running_state(self, running: bool):
        self.is_running = running

        if running:
            self.run_btn.setText("⛔ Прервать конвертацию")
            self.run_btn.setEnabled(True)
            self.run_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    font-weight: bold;
                    padding: 8px;
                    border-radius: 4px;
                }
                QPushButton:hover { background-color: #c0392b; }
                QPushButton:disabled { background-color: #bdc3c7; }
            """)
        else:
            self.run_btn.setText("🔍 Начать конвертацию и анализ")
            self.run_btn.setEnabled(True)
            self.run_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    font-weight: bold;
                    padding: 8px;
                    border-radius: 4px;
                }
                QPushButton:hover { background-color: #2980b9; }
                QPushButton:disabled { background-color: #bdc3c7; }
            """)

    # -----------------------------
    # Save / export
    # -----------------------------
    def save_results(self):
        if not (self.structured_data or {}).get("chapters"):
            self.status_label.setText("❌ Нет данных для сохранения")
            return

        file_dialog = QFileDialog(self)
        file_dialog.setAcceptMode(QFileDialog.AcceptSave)
        file_dialog.setNameFilters([
            "Текстовый файл (*.txt)",
            "JSON файл (*.json)",
            "Все файлы (*.*)"
        ])
        file_dialog.setDefaultSuffix("json")

        if file_dialog.exec():
            file_path = file_dialog.selectedFiles()[0]
            file_ext = os.path.splitext(file_path)[1].lower()

            try:
                if file_ext == ".txt":
                    self.save_as_text(file_path)
                else:
                    # default json
                    if not file_path.lower().endswith(".json"):
                        file_path += ".json"
                    self.save_as_json(file_path)

                self.status_label.setText(f"✅ Результаты сохранены в {os.path.basename(file_path)}")
            except Exception as e:
                self.status_label.setText(f"❌ Ошибка сохранения: {str(e)}")

    def save_as_json(self, file_path: str):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.structured_data, f, ensure_ascii=False, indent=2)

    def save_as_text(self, file_path: str):
        source_file = (self.structured_data or {}).get("source_file") or os.path.basename(self.pdf_path)
        chapters = (self.structured_data or {}).get("chapters", [])

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("PDF Конвертация результатов (структура: главы -> параграфы)\n")
            f.write(f"Файл: {source_file}\n")
            f.write(f"Дата: {QDateTime.currentDateTime().toString('dd.MM.yyyy HH:mm:ss')}\n")
            f.write("=" * 80 + "\n\n")

            for c_idx, ch in enumerate(chapters, start=1):
                title = (ch.get("title") or f"Глава {c_idx}").strip()
                f.write(f"\n{'=' * 80}\n")
                f.write(f"ГЛАВА {c_idx}: {title}\n")
                f.write(f"{'=' * 80}\n\n")

                ch_headers = ch.get("headers") or []
                if ch_headers:
                    f.write("Заголовки главы:\n")
                    for h in ch_headers:
                        f.write(f"  - {str(h).strip()}\n")
                    f.write("\n")

                paragraphs = ch.get("paragraphs") or []
                for p_idx, p in enumerate(paragraphs, start=1):
                    f.write(f"\n--- Параграф {p_idx} ---\n")
                    p_headers = p.get("headers") or []
                    if p_headers:
                        f.write("Заголовки:\n")
                        for h in p_headers:
                            f.write(f"  • {str(h).strip()}\n")
                        f.write("\n")

                    text = (p.get("text") or "").strip()
                    f.write(text + "\n")

    def export_paragraph(self, chapter_idx: int, paragraph_idx: int):
        ch = self.get_chapter(chapter_idx)
        p = self.get_paragraph(chapter_idx, paragraph_idx)
        if not ch or not p:
            return

        title = (ch.get("title") or f"Глава {chapter_idx + 1}").strip()
        suggested = f"параграф_{chapter_idx+1}_{paragraph_idx+1}.txt"

        file_dialog = QFileDialog(self)
        file_dialog.setAcceptMode(QFileDialog.AcceptSave)
        file_dialog.setNameFilters(["Текстовый файл (*.txt)", "JSON файл (*.json)"])
        file_dialog.setDefaultSuffix("txt")
        file_dialog.selectFile(suggested)

        if file_dialog.exec():
            file_path = file_dialog.selectedFiles()[0]
            ext = os.path.splitext(file_path)[1].lower()

            try:
                if ext == ".json":
                    payload = {
                        "chapter_index": chapter_idx,
                        "paragraph_index": paragraph_idx,
                        "chapter_title": title,
                        "paragraph": p,
                    }
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(payload, f, ensure_ascii=False, indent=2)
                else:
                    if not file_path.lower().endswith(".txt"):
                        file_path += ".txt"
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(f"{title}\n")
                        f.write(f"Параграф {paragraph_idx + 1}\n")
                        f.write("=" * 80 + "\n\n")
                        headers = p.get("headers") or []
                        if headers:
                            f.write("Заголовки:\n")
                            for h in headers:
                                f.write(f"• {str(h).strip()}\n")
                            f.write("\n")
                        f.write((p.get("text") or "").strip() + "\n")

                self.status_label.setText(f"✅ Параграф экспортирован: {os.path.basename(file_path)}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка экспорта", str(e))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PDFConverterUI()
    window.show()
    sys.exit(app.exec())
