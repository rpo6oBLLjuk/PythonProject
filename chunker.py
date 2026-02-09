from typing import List, Dict, Any


class TextChunker:
    def __init__(
        self,
        max_chars: int = 4500,
        soft_limit: int = 3500,
    ):
        """
        max_chars  — жёсткий предел (никогда не превышаем)
        soft_limit — желаемый размер чанка
        """
        self.max_chars = max_chars
        self.soft_limit = soft_limit

    def chunk(self, blocks: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """
        Принимает список текстовых блоков и возвращает список чанков,
        каждый чанк — список блоков.
        """
        chunks: List[List[Dict[str, Any]]] = []

        current_chunk: List[Dict[str, Any]] = []
        current_size = 0

        for block in blocks:
            block_text = self._block_to_text(block)
            block_len = len(block_text)

            # если блок сам по себе огромный — режем отдельно
            if block_len > self.max_chars:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = []
                    current_size = 0

                chunks.extend(self._split_large_block(block))
                continue

            # если добавление блока переполнит чанк
            if current_size + block_len > self.max_chars:
                chunks.append(current_chunk)
                current_chunk = [block]
                current_size = block_len
                continue

            # soft limit: если превышаем — закрываем чанк
            if current_size >= self.soft_limit:
                chunks.append(current_chunk)
                current_chunk = [block]
                current_size = block_len
                continue

            # обычное добавление
            current_chunk.append(block)
            current_size += block_len

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    # ------------------------------------------------------------

    def _block_to_text(self, block: Dict[str, Any]) -> str:
        """
        Превращает блок в текст для оценки длины.
        """
        if block["type"] == "heading":
            return block["text"] + "\n\n"
        if block["type"] == "paragraph":
            return block["text"] + "\n\n"
        if block["type"] == "list":
            return "\n".join(block["items"]) + "\n\n"

        return str(block)

    # ------------------------------------------------------------

    def _split_large_block(self, block: Dict[str, Any]) -> List[List[Dict[str, Any]]]:
        """
        Режет слишком большой paragraph на несколько псевдоблоков.
        """
        text = block["text"]
        parts = []

        start = 0
        while start < len(text):
            end = start + self.soft_limit
            parts.append([{
                "type": block["type"],
                "text": text[start:end]
            }])
            start = end

        return parts
