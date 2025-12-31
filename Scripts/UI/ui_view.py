from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QSpinBox, QTextEdit,
    QTabWidget, QComboBox, QCheckBox, QGroupBox, QTreeWidget,
    QTreeWidgetItem, QSplitter, QMenu
)
from PySide6.QtGui import QFont, QTextCharFormat, QColor, QTextCursor, QAction
from PySide6.QtCore import Qt, QTimer, QDateTime

from Scripts.PDFProcessor.pdf_converter import PDFConverterWithStructureThread

import os
import json
import sys


class PDFConverterUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Converter")
        self.setMinimumSize(900, 600)
        self.setFont(QFont("Segoe UI", 10))
        self.pdf_path = ""
        self.pages_content = {}
        self.structured_data = {}
        self.current_page = 1
        self.total_pages = 0
        self.monochrome_mode = False  # Флаг для однотонного режима
        self.setup_ui()

        # Настройка цветов для разных типов текста (для темного фона)
        self.type_colors = {
            "header": QColor("#ff6b6b"),  # Светло-красный
            "subheader": QColor("#ffd166"),  # Светло-желтый
            "task_number": QColor("#06d6a0"),  # Светло-зеленый
            "answer_option": QColor("#118ab2"),  # Светло-синий
            "bold_text": QColor("#ef476f"),  # Ярко-розовый
            "paragraph": QColor("#ffffff"),  # Белый
            "table": QColor("#ffd166"),  # Светло-желтый
            "image_text": QColor("#83c5be"),  # Светло-бирюзовый
            "regular": QColor("#e0e0e0")  # Светло-серый
        }

    def setup_ui(self):
        main_layout = QVBoxLayout()

        # Верхняя панель: выбор файла и настройки
        top_group = QGroupBox("Параметры конвертации")
        top_layout = QVBoxLayout()

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
        settings_layout.addWidget(QLabel("Макс. страниц:"))
        self.pages_spin = QSpinBox()
        self.pages_spin.setMinimum(1)
        self.pages_spin.setMaximum(1000)
        self.pages_spin.setValue(10)
        settings_layout.addWidget(self.pages_spin)

        settings_layout.addWidget(QLabel("Формат вывода:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Текст с разметкой", "Сырой текст", "JSON"])
        settings_layout.addWidget(self.format_combo)

        # Переключатель однотонного режима
        self.monochrome_checkbox = QCheckBox("Однотонный вывод")
        self.monochrome_checkbox.toggled.connect(self.toggle_monochrome_mode)
        settings_layout.addWidget(self.monochrome_checkbox)

        settings_layout.addStretch()
        top_layout.addLayout(settings_layout)
        top_group.setLayout(top_layout)
        main_layout.addWidget(top_group)

        # Кнопка сохранения
        self.save_btn = QPushButton("💾 Сохранить результаты")
        self.save_btn.clicked.connect(self.save_results)
        self.save_btn.setEnabled(False)
        settings_layout.addWidget(self.save_btn)

        top_layout.addLayout(settings_layout)
        top_group.setLayout(top_layout)
        main_layout.addWidget(top_group)

        # Кнопка запуска
        self.run_btn = QPushButton("🔍 Начать конвертацию и анализ")
        self.run_btn.clicked.connect(self.run_conversion)
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        main_layout.addWidget(self.run_btn)

        # Основная область с разделителем
        splitter = QSplitter(Qt.Horizontal)

        # Левая панель: дерево структуры
        self.structure_tree = QTreeWidget()
        self.structure_tree.setHeaderLabel("Структура документа")
        self.structure_tree.setMinimumWidth(250)
        self.structure_tree.itemClicked.connect(self.on_tree_item_clicked)

        # Контекстное меню для дерева
        self.structure_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.structure_tree.customContextMenuRequested.connect(self.show_tree_context_menu)

        splitter.addWidget(self.structure_tree)

        # Правая панель: вкладки с результатами
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # Вкладки
        self.tabs = QTabWidget()

        # Вкладка с форматированным текстом
        self.results_tab = QTextEdit()
        self.results_tab.setReadOnly(True)
        self.results_tab.setFont(QFont("Consolas", 10))

        # Вкладка с сырыми данными
        self.raw_tab = QTextEdit()
        self.raw_tab.setReadOnly(True)
        self.raw_tab.setFont(QFont("Consolas", 10))

        # Вкладка с логами
        self.logs_tab = QTextEdit()
        self.logs_tab.setReadOnly(True)
        self.logs_tab.setFont(QFont("Consolas", 9))

        self.tabs.addTab(self.results_tab, "📄 Форматированный текст")
        self.tabs.addTab(self.raw_tab, "📝 Сырые данные")
        self.tabs.addTab(self.logs_tab, "📊 Логи")

        right_layout.addWidget(self.tabs)

        # Панель навигации по страницам
        nav_group = QGroupBox("Навигация")
        nav_layout = QHBoxLayout()

        self.prev_btn = QPushButton("◀ Предыдущая")
        self.prev_btn.clicked.connect(self.show_prev_page)
        self.prev_btn.setEnabled(False)

        self.page_label = QLabel("Страница: 0/0")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setStyleSheet("font-weight: bold;")

        self.next_btn = QPushButton("Следующая ▶")
        self.next_btn.clicked.connect(self.show_next_page)
        self.next_btn.setEnabled(False)

        # Выбор страницы
        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.page_label)
        nav_layout.addWidget(self.next_btn)

        nav_layout.addStretch()

        nav_layout.addWidget(QLabel("Перейти:"))
        self.page_combo = QComboBox()
        self.page_combo.setMaximumWidth(80)
        self.page_combo.currentIndexChanged.connect(self.on_page_combo_changed)
        nav_layout.addWidget(self.page_combo)

        nav_group.setLayout(nav_layout)
        right_layout.addWidget(nav_group)

        splitter.addWidget(right_widget)
        splitter.setSizes([300, 600])

        main_layout.addWidget(splitter)

        # Статусная строка
        self.status_label = QLabel("Готово")
        self.status_label.setStyleSheet("color: #7f8c8d; padding: 5px; border-top: 1px solid #ddd;")
        main_layout.addWidget(self.status_label)

        self.setLayout(main_layout)

    def toggle_monochrome_mode(self, checked):
        """Переключение однотонного режима"""
        self.monochrome_mode = checked
        # Если есть текущая страница, перерисовываем ее
        if self.current_page in self.pages_content:
            self.display_page(self.current_page)

    def browse_pdf(self):
        file_dialog = QFileDialog(self, "Выберите PDF файл", "", "PDF Files (*.pdf)")
        if file_dialog.exec():
            self.pdf_path = file_dialog.selectedFiles()[0]
            self.pdf_input.setText(self.pdf_path)
            try:
                from pdfminer.high_level import extract_pages
                pages = list(extract_pages(self.pdf_path))
                self.pages_spin.setMaximum(len(pages))
                self.pages_spin.setValue(min(len(pages), 10))
                self.status_label.setText(f"Файл загружен: {os.path.basename(self.pdf_path)} ({len(pages)} стр.)")
            except Exception as e:
                self.status_label.setText(f"Ошибка чтения PDF: {str(e)}")

    def run_conversion(self):
        if not self.pdf_input.text() or not os.path.exists(self.pdf_input.text()):
            self.results_tab.setText("❌ Ошибка: PDF файл не выбран или не существует.")
            return

        # Создаем временную директорию
        script_dir = os.path.dirname(os.path.abspath(__file__))
        temp_dir = os.path.join(script_dir, "Temp")
        os.makedirs(temp_dir, exist_ok=True)

        max_pages = self.pages_spin.value()

        # Сброс данных
        self.pages_content = {}
        self.structured_data = {}
        self.structure_tree.clear()
        self.current_page = 1
        self.total_pages = 0
        self.page_combo.clear()

        # Очистка логов
        self.logs_tab.clear()

        # Блокировка интерфейса
        self.run_btn.setEnabled(False)
        self.run_btn.setText("⏳ Обработка...")
        self.status_label.setText("Начата конвертация...")
        self.save_btn.setEnabled(False)

        # Добавляем начальный лог с временем
        current_time = QDateTime.currentDateTime().toString("HH:mm:ss")
        self.logs_tab.append(f"[{current_time}] Начата обработка PDF файла...")
        self.logs_tab.append(f"[{current_time}] Файл: {os.path.basename(self.pdf_path)}")
        self.logs_tab.append(f"[{current_time}] Максимальное количество страниц: {max_pages}")
        self.logs_tab.append("-" * 50)

        # Создание и запуск потока
        self.thread = PDFConverterWithStructureThread(
            self.pdf_input.text(),
            temp_dir,
            max_pages
        )
        self.thread.progress.connect(self.update_logs)
        self.thread.page_ready.connect(self.process_page_data)
        self.thread.finished_conversion.connect(self.on_conversion_finished)
        self.thread.start()

    def update_logs(self, message: str):
        """Обновление логов с временной меткой"""
        current_time = QDateTime.currentDateTime().toString("HH:mm:ss")
        self.logs_tab.append(f"[{current_time}] {message}")

        # Автопрокрутка к последнему сообщению
        cursor = self.logs_tab.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.logs_tab.setTextCursor(cursor)

    def process_page_data(self, page_num: int, page_json: str):
        """Обработка данных страницы, полученных из потока"""
        try:
            page_data = json.loads(page_json)
            self.pages_content[page_num] = page_data

            # Обновляем дерево структуры
            self.update_structure_tree(page_num, page_data)

            # Обновляем комбобокс страниц
            if page_num not in [self.page_combo.itemText(i) for i in range(self.page_combo.count())]:
                self.page_combo.addItem(f"{page_num}")

            # Если это первая страница, отображаем ее
            if page_num == 1:
                self.display_page(1)
                self.page_combo.setCurrentIndex(0)

            # Обновляем навигацию
            self.total_pages = max(self.pages_content.keys())
            self.page_label.setText(f"Страница: {self.current_page}/{self.total_pages}")
            self.update_navigation_buttons()

            # Обновляем статус
            processed = len(self.pages_content)
            self.status_label.setText(f"Обработано: {processed}/{self.total_pages} страниц")

            # Логируем успешную обработку страницы
            current_time = QDateTime.currentDateTime().toString("HH:mm:ss")
            elements_count = len(page_data.get("elements", []))
            self.logs_tab.append(f"[{current_time}] Страница {page_num} обработана ({elements_count} элементов)")

        except Exception as e:
            current_time = QDateTime.currentDateTime().toString("HH:mm:ss")
            self.logs_tab.append(f"[{current_time}] ❌ Ошибка обработки страницы {page_num}: {str(e)}")

    def update_structure_tree(self, page_num: int, page_data: dict):
        """Обновление дерева структуры документа"""
        # Создаем элемент для страницы
        page_item = QTreeWidgetItem(self.structure_tree)
        elements_count = len(page_data.get("elements", []))
        page_item.setText(0, f"📄 Страница {page_num} ({elements_count} эл.)")
        page_item.setData(0, Qt.UserRole, {"type": "page", "number": page_num})

        # Группируем элементы по типам
        elements_by_type = {}
        for elem in page_data.get("elements", []):
            elem_type = elem.get("type", "regular")
            if elem_type not in elements_by_type:
                elements_by_type[elem_type] = []
            elements_by_type[elem_type].append(elem)

        # Добавляем элементы в дерево
        type_icons = {
            "header": "🔴",
            "subheader": "🟡",
            "task_number": "🔢",
            "answer_option": "🅰️",
            "bold_text": "🔷",
            "paragraph": "📝",
            "table": "📊",
            "image_text": "🖼️",
            "regular": "📄"
        }

        for elem_type, elements in elements_by_type.items():
            type_item = QTreeWidgetItem(page_item)
            icon = type_icons.get(elem_type, "📄")
            type_item.setText(0, f"{icon} {self.get_type_label(elem_type)} ({len(elements)})")
            type_item.setData(0, Qt.UserRole, {"type": "category", "page": page_num, "elem_type": elem_type})

            # Добавляем элементы (ограничиваем для производительности)
            max_elements_to_show = 20
            for i, elem in enumerate(elements[:max_elements_to_show]):
                elem_item = QTreeWidgetItem(type_item)
                text_preview = elem.get("text", "").strip()
                if len(text_preview) > 50:
                    text_preview = text_preview[:50] + "..."

                # Добавляем информацию о шрифте если есть
                font_info = ""
                if elem.get("font_size"):
                    font_info = f" [{elem['font_size']}pt"
                    if elem.get("is_bold"):
                        font_info += ",B"
                    if elem.get("is_italic"):
                        font_info += ",I"
                    font_info += "]"

                elem_item.setText(0, f"{text_preview}{font_info}")
                elem_item.setData(0, Qt.UserRole, {
                    "type": "element",
                    "page": page_num,
                    "index": i,
                    "elem_data": elem
                })

            # Если элементов больше, чем показываем, добавляем информационный элемент
            if len(elements) > max_elements_to_show:
                info_item = QTreeWidgetItem(type_item)
                info_item.setText(0, f"... и ещё {len(elements) - max_elements_to_show} элементов")
                info_item.setForeground(0, QColor("#7f8c8d"))

        # Разворачиваем первую страницу
        if page_num == 1:
            page_item.setExpanded(True)

    def get_type_label(self, elem_type: str) -> str:
        """Получение читаемого названия типа элемента"""
        labels = {
            "header": "Заголовки",
            "subheader": "Подзаголовки",
            "task_number": "Номера задач",
            "answer_option": "Варианты ответов",
            "bold_text": "Жирный текст",
            "paragraph": "Абзацы",
            "table": "Таблицы",
            "image_text": "Текст из изображений",
            "regular": "Обычный текст"
        }
        return labels.get(elem_type, elem_type)

    def on_tree_item_clicked(self, item):
        """Обработка клика по элементу дерева"""
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        if data.get("type") == "page":
            page_num = data.get("number")
            self.display_page(page_num)
            # Устанавливаем комбобокс на нужную страницу
            index = self.page_combo.findText(f"{page_num}")
            if index >= 0:
                self.page_combo.setCurrentIndex(index)

        elif data.get("type") == "element":
            page_num = data.get("page")
            elem_data = data.get("elem_data")
            self.display_page(page_num)

            # Прокручиваем к нужному элементу (упрощенно)
            text_to_find = elem_data.get("text", "")[:30]
            if text_to_find:
                self.highlight_text_in_display(text_to_find)

    def highlight_text_in_display(self, text: str):
        """Подсветка текста в отображении"""
        cursor = self.results_tab.textCursor()
        self.results_tab.moveCursor(QTextCursor.Start)

        # Ищем текст
        while self.results_tab.find(text):
            # Подсвечиваем найденный текст
            fmt = QTextCharFormat()
            fmt.setBackground(QColor("#FFFACD"))  # Лимонный цвет
            cursor = self.results_tab.textCursor()
            cursor.mergeCharFormat(fmt)

            # Прокручиваем к найденному тексту
            self.results_tab.setTextCursor(cursor)
            break

    def show_tree_context_menu(self, position):
        """Показ контекстного меню для дерева"""
        item = self.structure_tree.itemAt(position)
        if not item:
            return

        data = item.data(0, Qt.UserRole)
        if not data:
            return

        menu = QMenu()

        if data.get("type") == "page":
            page_num = data.get("number")
            goto_action = QAction(f"Перейти к странице {page_num}", self)
            goto_action.triggered.connect(lambda: self.display_page(page_num))
            menu.addAction(goto_action)

            export_action = QAction(f"Экспортировать страницу {page_num}", self)
            export_action.triggered.connect(lambda: self.export_page(page_num))
            menu.addAction(export_action)

        elif data.get("type") == "category":
            page_num = data.get("page")
            elem_type = data.get("elem_type")

            filter_action = QAction(f"Показать только '{self.get_type_label(elem_type)}'", self)
            filter_action.triggered.connect(lambda: self.filter_by_type(page_num, elem_type))
            menu.addAction(filter_action)

        elif data.get("type") == "element":
            elem_data = data.get("elem_data")
            copy_action = QAction("Копировать текст", self)
            copy_action.triggered.connect(lambda: self.copy_element_text(elem_data))
            menu.addAction(copy_action)

            info_action = QAction("Показать информацию", self)
            info_action.triggered.connect(lambda: self.show_element_info(elem_data))
            menu.addAction(info_action)

        menu.addSeparator()
        expand_all_action = QAction("Развернуть всё", self)
        expand_all_action.triggered.connect(self.structure_tree.expandAll)
        menu.addAction(expand_all_action)

        collapse_all_action = QAction("Свернуть всё", self)
        collapse_all_action.triggered.connect(self.structure_tree.collapseAll)
        menu.addAction(collapse_all_action)

        menu.exec(self.structure_tree.mapToGlobal(position))

    def filter_by_type(self, page_num: int, elem_type: str):
        """Фильтрация отображения по типу элемента"""
        if page_num not in self.pages_content:
            return

        page_data = self.pages_content[page_num]
        filtered_elements = [e for e in page_data.get("elements", [])
                             if e.get("type") == elem_type]

        # Временное отображение только отфильтрованных элементов
        self.display_filtered_page(page_num, filtered_elements, elem_type)

    def display_filtered_page(self, page_num: int, elements: list, filter_type: str):
        """Отображение отфильтрованной страницы"""
        self.results_tab.clear()
        cursor = self.results_tab.textCursor()

        # Заголовок
        header_format = QTextCharFormat()
        header_format.setFontWeight(QFont.Bold)
        header_format.setFontPointSize(12)
        header_format.setForeground(QColor("#2c3e50"))

        cursor.insertText(f"\n{'=' * 60}\n", header_format)
        cursor.insertText(f"СТРАНИЦА {page_num} - Только '{self.get_type_label(filter_type)}'\n", header_format)
        cursor.insertText(f"{'=' * 60}\n\n", header_format)

        # Отображаем отфильтрованные элементы
        for elem in elements:
            self.insert_formatted_element(cursor, elem)

        self.results_tab.moveCursor(QTextCursor.Start)

    def copy_element_text(self, elem_data: dict):
        """Копирование текста элемента в буфер обмена"""
        text = elem_data.get("text", "")
        if text:
            QApplication.clipboard().setText(text)
            self.status_label.setText(f"Текст скопирован в буфер обмена")

    def show_element_info(self, elem_data: dict):
        """Показ информации об элементе"""
        info = f"""
Тип: {self.get_type_label(elem_data.get('type', 'unknown'))}
Длина текста: {len(elem_data.get('text', ''))} символов
"""
        if elem_data.get('font_name'):
            info += f"Шрифт: {elem_data['font_name']}\n"
        if elem_data.get('font_size'):
            info += f"Размер: {elem_data['font_size']}pt\n"
        if elem_data.get('is_bold'):
            info += "Жирный: Да\n"
        if elem_data.get('is_italic'):
            info += "Курсив: Да\n"

        self.status_label.setText(info.strip())

    def on_page_combo_changed(self, index):
        """Обработка изменения выбора страницы в комбобоксе"""
        if index >= 0:
            page_text = self.page_combo.currentText()
            if page_text.isdigit():
                page_num = int(page_text)
                self.display_page(page_num)

    def display_page(self, page_num: int):
        """Отображение страницы с форматированием"""
        if page_num not in self.pages_content:
            return

        page_data = self.pages_content[page_num]
        self.current_page = page_num

        # Обновляем навигацию
        self.page_label.setText(f"Страница: {self.current_page}/{self.total_pages}")
        self.update_navigation_buttons()

        # Обновляем комбобокс
        index = self.page_combo.findText(f"{page_num}")
        if index >= 0 and index != self.page_combo.currentIndex():
            self.page_combo.setCurrentIndex(index)

        # Отображаем в выбранном формате
        format_type = self.format_combo.currentText()

        if format_type == "Текст с разметкой":
            self.display_formatted_text(page_data)
        elif format_type == "Сырой текст":
            self.display_raw_text(page_data)
        elif format_type == "JSON":
            self.display_json(page_data)

    def update_navigation_buttons(self):
        """Обновление состояния кнопок навигации"""
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < self.total_pages)

    def display_formatted_text(self, page_data: dict):
        """Отображение форматированного текста с цветами"""
        self.results_tab.clear()

        # Устанавливаем стиль ТОЛЬКО для results_tab (форматированный текст)
        self.results_tab.setStyleSheet("""
            QTextEdit {
                background-color: #2c3e50;
                color: #ffffff;
                font-family: Consolas;
                font-size: 10pt;
            }
        """)

        # Для raw_tab (сырой текст) устанавливаем светлый стиль
        self.raw_tab.setStyleSheet("""
            QTextEdit {
                background-color: #ffffff;
                color: #000000;
                font-family: Consolas;
                font-size: 10pt;
            }
        """)

        # Для logs_tab тоже свой стиль
        self.logs_tab.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                color: #212529;
                font-family: Consolas;
                font-size: 9pt;
            }
        """)

        cursor = self.results_tab.textCursor()

        # Заголовок страницы
        header_format = QTextCharFormat()
        header_format.setFontWeight(QFont.Bold)
        header_format.setFontPointSize(12)
        header_format.setForeground(QColor("#ffffff"))  # Белый цвет

        cursor.insertText(f"\n{'=' * 60}\n", header_format)
        cursor.insertText(f"СТРАНИЦА {page_data.get('page_number', 1)}\n", header_format)
        cursor.insertText(f"{'=' * 60}\n\n", header_format)

        # Отображаем все элементы
        for elem in page_data.get("elements", []):
            self.insert_formatted_element(cursor, elem)

        # Прокручиваем к началу
        self.results_tab.moveCursor(QTextCursor.Start)
        self.tabs.setCurrentWidget(self.results_tab)

    def display_raw_text(self, page_data: dict):
        """Отображение сырого текста"""
        # Устанавливаем светлый стиль для сырого текста
        self.raw_tab.setStyleSheet("""
            QTextEdit {
                background-color: #ffffff;
                color: #000000;
                font-family: Consolas;
                font-size: 10pt;
            }
        """)

        text_lines = []
        for elem in page_data.get("elements", []):
            elem_type = elem.get("type", "unknown")
            text = elem.get("text", "")
            font_info = ""

            if elem.get("font_name") or elem.get("font_size"):
                font_parts = []
                if elem.get("font_name"):
                    font_parts.append(elem['font_name'])
                if elem.get("font_size"):
                    font_parts.append(f"{elem['font_size']}pt")
                if elem.get("is_bold"):
                    font_parts.append("B")
                if elem.get("is_italic"):
                    font_parts.append("I")

                font_info = f" [{' '.join(font_parts)}]"

            text_lines.append(f"[{elem_type}{font_info}] {text}")

        self.raw_tab.setText("\n".join(text_lines))
        self.tabs.setCurrentWidget(self.raw_tab)

    def display_json(self, page_data: dict):
        """Отображение данных в формате JSON"""
        import json
        json_text = json.dumps(page_data, ensure_ascii=False, indent=2)

        # Устанавливаем светлый стиль для JSON
        self.raw_tab.setStyleSheet("""
            QTextEdit {
                background-color: #ffffff;
                color: #000000;
                font-family: Consolas;
                font-size: 10pt;
            }
        """)

        self.raw_tab.setText(json_text)
        self.tabs.setCurrentWidget(self.raw_tab)

    def insert_formatted_element(self, cursor, elem: dict):
        """Вставка форматированного элемента в текст"""
        elem_type = elem.get("type", "regular")
        text = elem.get("text", "")

        if not text.strip():
            return

        # Создаем формат для элемента
        fmt = QTextCharFormat()

        # Устанавливаем белый цвет по умолчанию для всех элементов
        fmt.setForeground(QColor("#ffffff"))  # Белый цвет

        # Настройка шрифта
        if elem_type in ["header", "subheader"]:
            fmt.setFontWeight(QFont.Bold)
            if elem_type == "header":
                fmt.setFontPointSize(12)
            else:
                fmt.setFontPointSize(11)
        elif elem_type == "bold_text" or elem.get("is_bold"):
            fmt.setFontWeight(QFont.Bold)
        elif elem.get("is_italic"):
            fmt.setFontItalic(True)

        # Сохраняем исходные переносы строк - разбиваем текст на строки
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if line.strip():  # Пропускаем пустые строки
                # Добавляем префиксы для некоторых типов (только для первой строки)
                if i == 0:
                    prefixes = {
                        "header": f"\n# ",
                        "subheader": f"\n## ",
                        "task_number": f"\n▶ ",
                        "answer_option": "   ○ ",
                        "table": f"\n[ТАБЛИЦА]\n",
                        "image_text": f"\n[ИЗОБРАЖЕНИЕ]\n"
                    }

                    prefix = prefixes.get(elem_type, "")
                    if prefix:
                        cursor.insertText(prefix, fmt)

                # Вставляем строку текста
                cursor.insertText(line, fmt)

                # Добавляем перенос строки после каждой строки (кроме последней)
                if i < len(lines) - 1:
                    cursor.insertText("\n", fmt)

        # Добавляем дополнительные переносы строк в зависимости от типа элемента
        if elem_type in ["header", "subheader", "paragraph", "table", "image_text"]:
            cursor.insertText("\n", fmt)
        elif elem_type == "task_number":
            cursor.insertText("\n", fmt)

    def insert_formatted_element(self, cursor, elem: dict):
        """Вставка форматированного элемента в текст"""
        elem_type = elem.get("type", "regular")
        text = elem.get("text", "")

        if not text.strip():
            return

        # Создаем формат для элемента
        fmt = QTextCharFormat()

        # Устанавливаем цвет в зависимости от типа
        if elem_type in self.type_colors:
            fmt.setForeground(self.type_colors[elem_type])

        # Настройка шрифта
        if elem_type in ["header", "subheader"]:
            fmt.setFontWeight(QFont.Bold)
            if elem_type == "header":
                fmt.setFontPointSize(12)
            else:
                fmt.setFontPointSize(11)
        elif elem_type == "bold_text" or elem.get("is_bold"):
            fmt.setFontWeight(QFont.Bold)
        elif elem.get("is_italic"):
            fmt.setFontItalic(True)

        # Информация о шрифте (для отладки)
        font_info = ""
        if elem.get("font_size"):
            font_info = f" [{elem['font_size']:.1f}pt]"

        # Добавляем префиксы для некоторых типов
        prefixes = {
            "header": f"\n# ",
            "subheader": f"\n## ",
            "task_number": f"\n▶ ",
            "answer_option": "   ○ ",
            "table": f"\n[ТАБЛИЦА]{font_info}\n",
            "image_text": f"\n[ИЗОБРАЖЕНИЕ]{font_info}\n"
        }

        prefix = prefixes.get(elem_type, "")
        if prefix:
            cursor.insertText(prefix, fmt)

        # Вставляем текст
        cursor.insertText(text, fmt)

        # Добавляем перенос строки
        if elem_type in ["header", "subheader", "paragraph", "table", "image_text"]:
            cursor.insertText("\n", fmt)
        elif elem_type == "task_number":
            cursor.insertText("\n", fmt)



    def show_prev_page(self):
        if self.current_page > 1:
            self.display_page(self.current_page - 1)

    def show_next_page(self):
        if self.current_page < self.total_pages:
            self.display_page(self.current_page + 1)

    def on_conversion_finished(self, all_data_json: str):
        """Обработка завершения конвертации"""
        current_time = QDateTime.currentDateTime().toString("HH:mm:ss")

        try:
            # Сохраняем полные данные
            self.structured_data = json.loads(all_data_json) if all_data_json.strip() else {}

            # Разблокируем интерфейс
            self.run_btn.setEnabled(True)
            self.run_btn.setText("🔍 Начать конвертацию и анализ")
            self.save_btn.setEnabled(len(self.pages_content) > 0)

            # Подсчитываем статистику
            total_pages = len(self.pages_content)
            total_elements = 0
            element_types = {}

            for page_num, page_data in self.pages_content.items():
                elements = page_data.get("elements", [])
                total_elements += len(elements)

                for elem in elements:
                    elem_type = elem.get("type", "unknown")
                    element_types[elem_type] = element_types.get(elem_type, 0) + 1

            # Обновляем статус
            stats_text = f"✅ Конвертация завершена. Страниц: {total_pages}, Элементов: {total_elements}"

            # Добавляем статистику по типам
            if element_types:
                type_stats = ", ".join([f"{self.get_type_label(k)}: {v}"
                                        for k, v in element_types.items()])
                stats_text += f" ({type_stats})"

            self.status_label.setText(stats_text)

            # Логируем завершение
            self.logs_tab.append(f"[{current_time}] ✅ Конвертация успешно завершена!")
            self.logs_tab.append(
                f"[{current_time}] Всего обработано: {total_pages} страниц, {total_elements} элементов")

            if element_types:
                self.logs_tab.append(f"[{current_time}] Распределение по типам:")
                for elem_type, count in element_types.items():
                    self.logs_tab.append(f"[{current_time}]   • {self.get_type_label(elem_type)}: {count}")

            # Показываем первую страницу
            if total_pages > 0 and 1 in self.pages_content:
                self.display_page(1)

        except Exception as e:
            error_msg = f"Ошибка при завершении конвертации: {str(e)}"
            self.logs_tab.append(f"[{current_time}] ❌ {error_msg}")
            self.status_label.setText(f"❌ {error_msg}")
            self.run_btn.setEnabled(True)
            self.run_btn.setText("🔍 Начать конвертацию и анализ")

    def save_results(self):
        """Сохранение результатов по запросу пользователя"""
        if not self.pages_content:
            self.status_label.setText("❌ Нет данных для сохранения")
            return

        # Диалог выбора файла
        file_dialog = QFileDialog(self)
        file_dialog.setAcceptMode(QFileDialog.AcceptSave)
        file_dialog.setNameFilters([
            "Текстовый файл (*.txt)",
            "JSON файл (*.json)",
            "Все файлы (*.*)"
        ])
        file_dialog.setDefaultSuffix("txt")

        if file_dialog.exec():
            file_path = file_dialog.selectedFiles()[0]
            file_ext = os.path.splitext(file_path)[1].lower()

            try:
                if file_ext == '.json':
                    self.save_as_json(file_path)
                else:
                    self.save_as_text(file_path)

                self.status_label.setText(f"✅ Результаты сохранены в {os.path.basename(file_path)}")

            except Exception as e:
                self.status_label.setText(f"❌ Ошибка сохранения: {str(e)}")

    def save_as_text(self, file_path: str):
        """Сохранение в текстовом формате"""
        with open(file_path, "w", encoding="utf-8") as f:
            # Заголовок
            f.write(f"PDF Конвертация результатов\n")
            f.write(f"Файл: {os.path.basename(self.pdf_path)}\n")
            f.write(f"Дата: {QDateTime.currentDateTime().toString('dd.MM.yyyy HH:mm:ss')}\n")
            f.write("=" * 60 + "\n\n")

            # Данные по страницам
            for page_num in sorted(self.pages_content.keys()):
                page_data = self.pages_content[page_num]
                f.write(f"\n{'=' * 60}\n")
                f.write(f"СТРАНИЦА {page_data.get('page_number', page_num)}\n")
                f.write(f"{'=' * 60}\n\n")

                for elem in page_data.get("elements", []):
                    elem_type = elem.get("type", "regular")
                    text = elem.get("text", "")

                    if elem_type == "header":
                        f.write(f"# {text}\n\n")
                    elif elem_type == "subheader":
                        f.write(f"## {text}\n\n")
                    elif elem_type == "task_number":
                        f.write(f"▶ {text}\n")
                    elif elem_type == "answer_option":
                        f.write(f"   ○ {text}\n")
                    elif elem_type == "table":
                        f.write(f"[ТАБЛИЦА]\n{text}\n\n")
                    elif elem_type == "image_text":
                        f.write(f"[ИЗОБРАЖЕНИЕ]\n{text}\n\n")
                    elif elem_type == "paragraph":
                        f.write(f"{text}\n\n")
                    else:
                        f.write(f"{text}\n")

    def save_as_json(self, file_path: str):
        """Сохранение в формате JSON"""
        with open(file_path, "w", encoding="utf-8") as f:
            result_data = {
                "source_file": os.path.basename(self.pdf_path),
                "conversion_date": QDateTime.currentDateTime().toString('dd.MM.yyyy HH:mm:ss'),
                "total_pages": len(self.pages_content),
                "pages": {}
            }

            for page_num, page_data in self.pages_content.items():
                result_data["pages"][f"page_{page_num}"] = page_data

            json.dump(result_data, f, ensure_ascii=False, indent=2)

    def export_page(self, page_num: int):
        """Экспорт отдельной страницы"""
        if page_num not in self.pages_content:
            return

        file_dialog = QFileDialog(self)
        file_dialog.setAcceptMode(QFileDialog.AcceptSave)
        file_dialog.setDefaultSuffix("txt")
        file_dialog.selectFile(f"страница_{page_num}.txt")

        if file_dialog.exec():
            file_path = file_dialog.selectedFiles()[0]
            self.save_as_text(file_path)
            self.status_label.setText(f"✅ Страница {page_num} экспортирована")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PDFConverterUI()
    window.show()
    sys.exit(app.exec())