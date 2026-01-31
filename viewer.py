import sys
import json
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTreeWidget,
    QTreeWidgetItem,
    QFileDialog,
    QSplitter,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class JsonStructureViewer(QMainWindow):
    def __init__(self, json_path: str):
        super().__init__()

        self.setWindowTitle("Document Structure Viewer")
        self.resize(1000, 700)

        # Создаем главный виджет
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)  # Убираем отступы

        # Создаем сплиттер для дерева и текста
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        # Левая панель с деревом
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Структура документа"])
        self.tree.setColumnWidth(0, 350)
        splitter.addWidget(self.tree)

        # Правая панель с текстом
        text_container = QWidget()
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)

        self.text_view = QPlainTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setFont(QFont("Consolas", 10))
        text_layout.addWidget(self.text_view)

        splitter.addWidget(text_container)

        splitter.setSizes([350, 650])

        # Подключаем сигнал двойного клика
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)

        self.load_json(json_path)

    def load_json(self, path: str):
        """Загружает и отображает JSON структуру документа"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self.show_error(f"Ошибка загрузки JSON: {str(e)}")
            return

        self.tree.clear()

        chapters = data.get("chapters", [])

        if not chapters:
            no_data_item = QTreeWidgetItem(["Документ не содержит глав"])
            self.tree.addTopLevelItem(no_data_item)
            return

        for chapter_idx, chapter in enumerate(chapters, 1):
            chapter_title = chapter.get("chapter", f"Глава {chapter_idx}")

            # Создаем элемент главы
            chapter_item = QTreeWidgetItem([
                f"Глава {chapter_idx}: {chapter_title}"
            ])
            chapter_item.setData(0, Qt.UserRole, {
                "type": "chapter",
                "title": chapter_title,
                "full_text": None
            })
            self.tree.addTopLevelItem(chapter_item)

            # Добавляем разделы
            sections = chapter.get("sections", [])

            if not sections:
                no_sections_item = QTreeWidgetItem(["  [Нет разделов]"])
                chapter_item.addChild(no_sections_item)
                continue

            for section_idx, section in enumerate(sections, 1):
                section_title = section.get("section")

                # Формируем отображаемое название раздела
                if section_title:
                    display_title = f"Раздел {section_idx}: {section_title}"
                else:
                    display_title = f"Раздел {section_idx}: [Без названия]"

                # Создаем элемент раздела
                section_item = QTreeWidgetItem([display_title])
                section_item.setData(0, Qt.UserRole, {
                    "type": "section",
                    "title": section_title,
                    "full_text": section.get("text", "")
                })
                chapter_item.addChild(section_item)

        # Разворачиваем все элементы
        self.tree.expandAll()

    def on_item_double_clicked(self, item: QTreeWidgetItem):
        """Обрабатывает двойной клик по элементу дерева"""
        data = item.data(0, Qt.UserRole)

        if not data:
            self.text_view.clear()
            return

        if data["type"] == "section":
            # Для раздела показываем текст
            text = data.get("full_text", "")

            # Добавляем заголовок к тексту
            title = data.get("title")
            if title:
                header = f"РАЗДЕЛ: {title}\n{'=' * 60}\n\n"
            else:
                header = "РАЗДЕЛ: [Без названия]\n{'='*60}\n\n"

            self.text_view.setPlainText(header + text)
        elif data["type"] == "chapter":
            # Для главы собираем все тексты разделов
            chapter_text = []

            # Проходим по всем дочерним элементам (разделам)
            for i in range(item.childCount()):
                child = item.child(i)
                child_data = child.data(0, Qt.UserRole)
                if child_data and child_data["type"] == "section":
                    title = child_data.get("title", "[Без названия]")
                    text = child_data.get("full_text", "")

                    chapter_text.append(f"РАЗДЕЛ: {title}")
                    chapter_text.append("=" * 50)
                    chapter_text.append(text)
                    chapter_text.append("\n" + "-" * 70 + "\n")

            if chapter_text:
                header = f"ГЛАВА: {data.get('title', '')}\n{'=' * 60}\n\n"
                self.text_view.setPlainText(header + "\n".join(chapter_text))
            else:
                self.text_view.setPlainText(f"ГЛАВА: {data.get('title', '')}\n\n[Нет текста в разделах]")

    def show_error(self, message: str):
        """Показывает сообщение об ошибке"""
        error_item = QTreeWidgetItem([f"Ошибка: {message}"])
        self.tree.addTopLevelItem(error_item)


def main():
    app = QApplication(sys.argv)

    # Если путь передан как аргумент командной строки
    if len(sys.argv) > 1:
        json_path = sys.argv[1]
    else:
        # Иначе открываем диалог выбора файла
        json_path, _ = QFileDialog.getOpenFileName(
            None,
            "Выберите JSON файл с семантической структурой",
            "",
            "JSON файлы (*.json);;Все файлы (*)"
        )

    if not json_path:
        print("Файл не выбран. Выход.")
        sys.exit(0)

    viewer = JsonStructureViewer(json_path)
    viewer.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()