import sys
import json
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTreeWidget,
    QTreeWidgetItem,
    QFileDialog,
    QSplitter,
    QPlainTextEdit
)
from PySide6.QtCore import Qt


class JsonStructureViewer(QMainWindow):
    def __init__(self, json_path: str):
        super().__init__()

        self.setWindowTitle("Document Structure Viewer")
        self.resize(1000, 700)

        splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(splitter)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Structure"])
        splitter.addWidget(self.tree)

        self.text_view = QPlainTextEdit()
        self.text_view.setReadOnly(True)
        splitter.addWidget(self.text_view)

        splitter.setSizes([350, 650])

        self.tree.itemClicked.connect(self.on_item_clicked)

        self.load_json(json_path)

    def load_json(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.tree.clear()

        for chapter in data.get("chapters", []):
            chapter_item = QTreeWidgetItem([
                f"CHAPTER: {chapter.get('chapter')}"
            ])
            chapter_item.setData(0, Qt.UserRole, None)
            self.tree.addTopLevelItem(chapter_item)

            for part in chapter.get("content", []):
                part_name = part.get("part") or "<no part title>"
                part_item = QTreeWidgetItem([
                    f"PART: {part_name}"
                ])
                part_item.setData(0, Qt.UserRole, None)
                chapter_item.addChild(part_item)

                for block in part.get("content", []):
                    block_name = block.get("block") or "<no block title>"
                    block_item = QTreeWidgetItem([
                        f"BLOCK: {block_name}"
                    ])

                    # сохраняем ТЕКСТ БЛОКА целиком
                    full_text = "\n\n".join(block.get("content", []))
                    block_item.setData(0, Qt.UserRole, full_text)

                    part_item.addChild(block_item)

        self.tree.expandAll()

    def on_item_clicked(self, item: QTreeWidgetItem):
        text = item.data(0, Qt.UserRole)
        if isinstance(text, str):
            self.text_view.setPlainText(text)
        else:
            self.text_view.clear()


def main():
    app = QApplication(sys.argv)

    json_path, _ = QFileDialog.getOpenFileName(
        None,
        "Select semantic JSON",
        "",
        "JSON files (*.json)"
    )

    if not json_path:
        sys.exit(0)

    viewer = JsonStructureViewer(json_path)
    viewer.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
