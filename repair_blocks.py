from typing import List, Dict


def repair_blocks(blocks: List[Dict]) -> List[Dict]:
    """
    Приводит блоки к канонической модели:
    - text + list_item* → list_start + list_item*
    - list_item без list_start → text
    - list / questions → удаляются
    """

    repaired: List[Dict] = []
    i = 0

    while i < len(blocks):
        block = blocks[i]
        kind = block.get("kind")

        # normalize block shape from LLM (type/content → kind/text)
        if "type" in block and "content" in block:
            block = {
                "kind": block["type"],
                "text": block["content"]
            }

        # text + list_item → list_start
        if (
            kind == "text"
            and i + 1 < len(blocks)
            and blocks[i + 1].get("kind") == "list_item"
        ):
            repaired.append({
                "kind": "list_start",
                "text": block["text"]
            })
            i += 1
            continue

        # list_item без list_start → text
        if kind == "list_item":
            if not repaired or repaired[-1]["kind"] not in ("list_start", "list_item"):
                repaired.append({
                    "kind": "text",
                    "text": block["text"]
                })
            else:
                repaired.append(block)
            i += 1
            continue

        # запрещённые типы
        if kind in ("list", "questions"):
            i += 1
            continue

        repaired.append(block)
        i += 1

    return repaired
