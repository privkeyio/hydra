"""Validator module."""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .template_engine import Template, TemplateEngine, TemplateParameter


class TemplateValidator:

    @staticmethod
    def validate_template_structure(template_dir: Path) -> Tuple[bool, List[str]]:
        errors = []

        if not template_dir.exists():
            errors.append(f"Template directory does not exist: {template_dir}")
            return False, errors

        config_path = template_dir / "template.json"
        if not config_path.exists():
            errors.append("Missing template.json configuration file")
            return False, errors

        try:
            with open(config_path) as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON in template.json: {e}")
            return False, errors

        required_fields = ["name", "description"]
        for field in required_fields:
            if field not in config:
                errors.append(f"Missing required field in template.json: {field}")

        if "parameters" in config:
            param_errors = TemplateValidator._validate_parameters(config["parameters"])
            errors.extend(param_errors)

        files_dir = template_dir / "files"
        if not files_dir.exists():
            errors.append("Missing 'files' directory")
        elif not any(files_dir.rglob("*")):
            errors.append("Files directory is empty")

        return len(errors) == 0, errors

    @staticmethod
    def _validate_parameters(parameters: List[Dict[str, Any]]) -> List[str]:
        errors = []
        param_names = set()

        for i, param in enumerate(parameters):
            if not isinstance(param, dict):
                errors.append(f"Parameter {i} must be a dictionary")
                continue

            required_fields = ["name", "type", "description"]
            for field in required_fields:
                if field not in param:
                    errors.append(f"Parameter {i} missing required field: {field}")

            name = param.get("name")
            if name:
                if name in param_names:
                    errors.append(f"Duplicate parameter name: {name}")
                param_names.add(name)

            param_type = param.get("type")
            valid_types = ["string", "integer", "boolean", "array"]
            if param_type and param_type not in valid_types:
                errors.append(f"Invalid parameter type '{param_type}' for {name}")

        return errors

    @staticmethod
    def validate_template_generation(
        template: Template, parameters: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        errors = []

        try:
            engine = TemplateEngine()
            resolved_params = engine._resolve_parameters(
                template.parameters, parameters
            )

            for file_path, content in template.files.items():
                try:
                    engine._render_string(file_path, resolved_params)
                    engine._render_string(content, resolved_params)
                except Exception as e:
                    errors.append(f"Template rendering error in {file_path}: {e}")

        except Exception as e:
            errors.append(f"Parameter validation error: {e}")

        return len(errors) == 0, errors

    @staticmethod
    def validate_all_templates(
        templates_dir: Path,
    ) -> Dict[str, Tuple[bool, List[str]]]:
        results = {}
        engine = TemplateEngine(templates_dir)

        for template_name in engine.list_templates():
            template_dir = templates_dir / template_name
            is_valid, errors = TemplateValidator.validate_template_structure(
                template_dir
            )

            if is_valid:
                try:
                    template = engine.load_template(template_name)
                    test_params = TemplateValidator._generate_test_parameters(
                        template.parameters
                    )
                    gen_valid, gen_errors = (
                        TemplateValidator.validate_template_generation(
                            template, test_params
                        )
                    )

                    if not gen_valid:
                        is_valid = False
                        errors.extend(gen_errors)

                except Exception as e:
                    is_valid = False
                    errors.append(f"Template loading error: {e}")

            results[template_name] = (is_valid, errors)

        return results

    @staticmethod
    def _generate_test_parameters(
        parameters: List[TemplateParameter],
    ) -> Dict[str, Any]:
        test_params = {}

        for param in parameters:
            if param.default is not None:
                test_params[param.name] = param.default
            elif param.choices:
                test_params[param.name] = param.choices[0]
            elif param.type == "string":
                test_params[param.name] = "test_value"
            elif param.type == "integer":
                test_params[param.name] = 1
            elif param.type == "boolean":
                test_params[param.name] = True
            elif param.type == "array":
                test_params[param.name] = ["test"]
            else:
                test_params[param.name] = "test_value"

        return test_params
