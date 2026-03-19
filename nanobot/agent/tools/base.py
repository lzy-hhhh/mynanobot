"""Base class for agent tools."""

from abc import ABC, abstractmethod#提供一个抽象基类，定义了工具的基本接口和功能，包括名称、描述、参数定义、执行方法以及参数验证和转换等。所有具体工具都应该继承这个基类，并实现相应的方法，以确保它们能够被代理正确识别和调用。
from typing import Any


class Tool(ABC):
    """
    Abstract base class for agent tools.

    Tools are capabilities that the agent can use to interact with
    the environment, such as reading files, executing commands, etc.
    """

    _TYPE_MAP = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }#定义了一个类型映射字典，将JSON Schema中的基本类型（string、integer、number、boolean、array、object）映射到Python的内置类型（str、int、float、bool、list、dict）。这个映射用于在参数验证和转换过程中，根据工具定义的参数类型来检查和转换传入的参数值，确保它们符合预期的类型要求。

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name used in function calls."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what the tool does."""
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for tool parameters."""
        pass

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """
        Execute the tool with given parameters.

        Args:
            **kwargs: Tool-specific parameters.

        Returns:
            String result of the tool execution.
        """
        pass

    def cast_params(self, params: dict[str, Any]) -> dict[str, Any]:#把 AI 传来的字符串 / 弱类型参数，安全转换成代码需要的类型
        """Apply safe schema-driven casts before validation."""
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            return params

        return self._cast_object(params, schema)

    def _cast_object(self, obj: Any, schema: dict[str, Any]) -> dict[str, Any]:
        """Cast an object (dict) according to schema."""
        if not isinstance(obj, dict):
            return obj

        props = schema.get("properties", {})
        result = {}

        for key, value in obj.items():
            if key in props:
                result[key] = self._cast_value(value, props[key])
            else:
                result[key] = value

        return result

    def _cast_value(self, val: Any, schema: dict[str, Any]) -> Any:
        """Cast a single value according to schema."""
        target_type = schema.get("type")

        if target_type == "boolean" and isinstance(val, bool):
            return val
        if target_type == "integer" and isinstance(val, int) and not isinstance(val, bool):
            return val
        if target_type in self._TYPE_MAP and target_type not in ("boolean", "integer", "array", "object"):
            expected = self._TYPE_MAP[target_type]
            if isinstance(val, expected):
                return val

        if target_type == "integer" and isinstance(val, str):
            try:
                return int(val)
            except ValueError:
                return val

        if target_type == "number" and isinstance(val, str):
            try:
                return float(val)
            except ValueError:
                return val

        if target_type == "string":
            return val if val is None else str(val)

        if target_type == "boolean" and isinstance(val, str):
            val_lower = val.lower()
            if val_lower in ("true", "1", "yes"):
                return True
            if val_lower in ("false", "0", "no"):
                return False
            return val

        if target_type == "array" and isinstance(val, list):
            item_schema = schema.get("items")
            return [self._cast_value(item, item_schema) for item in val] if item_schema else val

        if target_type == "object" and isinstance(val, dict):
            return self._cast_object(val, schema)

        return val

    def validate_params(self, params: dict[str, Any]) -> list[str]:#按照 JSON Schema 严格校验参数，返回错误列表
        """Validate tool parameters against JSON schema. Returns error list (empty if valid)."""
        if not isinstance(params, dict):
            return [f"parameters must be an object, got {type(params).__name__}"]
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            raise ValueError(f"Schema must be object type, got {schema.get('type')!r}")
        return self._validate(params, {**schema, "type": "object"}, "")

    def _validate(self, val: Any, schema: dict[str, Any], path: str) -> list[str]:
        t, label = schema.get("type"), path or "parameter"
        if t == "integer" and (not isinstance(val, int) or isinstance(val, bool)):
            return [f"{label} should be integer"]
        if t == "number" and (
            not isinstance(val, self._TYPE_MAP[t]) or isinstance(val, bool)
        ):
            return [f"{label} should be number"]
        if t in self._TYPE_MAP and t not in ("integer", "number") and not isinstance(val, self._TYPE_MAP[t]):
            return [f"{label} should be {t}"]

        errors = []
        if "enum" in schema and val not in schema["enum"]:
            errors.append(f"{label} must be one of {schema['enum']}")
        if t in ("integer", "number"):
            if "minimum" in schema and val < schema["minimum"]:
                errors.append(f"{label} must be >= {schema['minimum']}")
            if "maximum" in schema and val > schema["maximum"]:
                errors.append(f"{label} must be <= {schema['maximum']}")
        if t == "string":
            if "minLength" in schema and len(val) < schema["minLength"]:
                errors.append(f"{label} must be at least {schema['minLength']} chars")
            if "maxLength" in schema and len(val) > schema["maxLength"]:
                errors.append(f"{label} must be at most {schema['maxLength']} chars")
        if t == "object":
            props = schema.get("properties", {})
            for k in schema.get("required", []):
                if k not in val:
                    errors.append(f"missing required {path + '.' + k if path else k}")
            for k, v in val.items():
                if k in props:
                    errors.extend(self._validate(v, props[k], path + "." + k if path else k))
        if t == "array" and "items" in schema:
            for i, item in enumerate(val):
                errors.extend(
                    self._validate(item, schema["items"], f"{path}[{i}]" if path else f"[{i}]")
                )
        return errors

    def to_schema(self) -> dict[str, Any]:#把工具转换成 OpenAI 函数调用标准格式的字典表示，包含工具的名称、描述和参数定义等信息，以便代理能够正确识别和调用这个工具。这个方法返回一个符合 OpenAI 函数调用规范的字典结构，其中 "type" 字段指定了这是一个函数类型的工具，"function" 字段包含了工具的具体定义，包括名称、描述和参数等。
        """Convert tool to OpenAI function schema format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
