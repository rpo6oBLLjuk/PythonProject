import json
from jsonschema import Draft7Validator


class JsonValidator:
    def __init__(self, schema_path: str):
        with open(schema_path, "r", encoding="utf-8") as f:
            self.schema = json.load(f)
        self.validator = Draft7Validator(self.schema)

    def validate(self, data: dict) -> list:
        return [e.message for e in self.validator.iter_errors(data)]
