import json
from jsonschema import Draft202012Validator


class JSONStructureValidator:
    def __init__(self, schema_path: str):
        with open(schema_path, "r", encoding="utf-8") as f:
            self.schema = json.load(f)
        self.validator = Draft202012Validator(self.schema)

    def validate(self, data: dict) -> list[str]:
        """
        Возвращает список ошибок.
        Если список пуст — JSON валиден.
        """
        errors = []
        for error in self.validator.iter_errors(data):
            path = " → ".join(map(str, error.path))
            errors.append(f"{path}: {error.message}")
        return errors
