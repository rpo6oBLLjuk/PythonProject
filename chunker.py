from typing import List, Dict


class TextChunker:
    def __init__(self, max_chars: int = 100000):
        self.max_chars = max_chars

    def chunk(self, blocks: List[Dict]) -> List[Dict]:
        chunks = []
        current = []
        size = 0

        for block in blocks:
            text = block.get("text", "")
            if size + len(text) > self.max_chars and current:
                chunks.append({"text": "\n".join(current)})
                return chunks
                #current = []
                #size = 0
            current.append(text)
            size += len(text)

        if current:
            chunks.append({"text": "\n".join(current)})

        return chunks
