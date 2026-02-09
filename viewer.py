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
)
from PySide6.QtCore import Qt


# ======================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ======================================================

def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def node_label(node: dict) -> str:
    t = node.get("type")

    if t in ("chapter", "section"):
        return f"{t.upper()}: {node.get('title', '')}"

    if t == "paragraph":
        return "PARAGRAPH"

    if t == "text":
        return node.get("text", "")[:60]

    if t == "list":
        return "LIST"

    if t == "qa":
        return f"Q&A: {node.get('title', '')}"

    return t or "NODE"


def node_content(node: dict) -> str:
    t = node.get("type")

    if t == "text":
        return node.get("text", "")

    if t == "list":
        return "\n".join(f"- {x}" for x in node.get("items", []))

    if t == "qa":
        lines = []
        for item in node.get("items", []):
            q = item.get("question", "")
            a = item.get("answer")
            lines.append(f"Q: {q}")
            if a:
                lines.append(f"A: {a}")
            lines.append("")
        return "\n".join(lines)

    return ""


# ======================================================
# ОСНОВНОЙ VIEWER
# ======================================================

class DocumentViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Document Viewer")
        self.resize(1200, 800)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.text)
        splitter.setSizes([400, 800])

        self.setCentralWidget(splitter)

        self.tree.itemClicked.connect(self.on_item_clicked)

        self.node_by_item = {}

        self.open_file()

    # --------------------------------------------------

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open JSON",
            "",
            "JSON files (*.json)"
        )
        if not path:
            return

        data = load_json(path)
        self.tree.clear()
        self.node_by_item.clear()

        root_item = QTreeWidgetItem([node_label(data)])
        self.tree.addTopLevelItem(root_item)
        self.node_by_item[root_item] = data

        self.build_tree(root_item, data)

        self.tree.expandAll()

    # --------------------------------------------------

    def build_tree(self, parent_item: QTreeWidgetItem, node: dict):
        # children для chapter / section / paragraph
        for child in node.get("children", []):
            item = QTreeWidgetItem([node_label(child)])
            parent_item.addChild(item)
            self.node_by_item[item] = child
            self.build_tree(item, child)

        # blocks для paragraph
        for block in node.get("blocks", []):
            item = QTreeWidgetItem([node_label(block)])
            parent_item.addChild(item)
            self.node_by_item[item] = block

    # --------------------------------------------------

    def on_item_clicked(self, item: QTreeWidgetItem, _column: int):
        node = self.node_by_item.get(item)
        if not node:
            return

        content = node_content(node)
        self.text.setPlainText(content)


# ======================================================
# ENTRY POINT
# ======================================================

def main():
    app = QApplication(sys.argv)
    viewer = DocumentViewer()
    viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
