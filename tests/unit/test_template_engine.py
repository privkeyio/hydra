import json
import tempfile
from pathlib import Path

import pytest

from hydra.templates.template_engine import Template, TemplateEngine, TemplateParameter
from hydra.templates.validator import TemplateValidator


class TestTemplateEngine:

    def test_template_parameter_creation(self):
        param = TemplateParameter(
            name="test_param",
            type="string",
            description="Test parameter",
            default="default_value",
            required=True,
            choices=["option1", "option2"],
        )

        assert param.name == "test_param"
        assert param.type == "string"
        assert param.description == "Test parameter"
        assert param.default == "default_value"
        assert param.required is True
        assert param.choices == ["option1", "option2"]

    def test_template_creation(self):
        param = TemplateParameter("name", "string", "Test param")
        template = Template(
            name="test_template",
            description="Test template",
            parameters=[param],
            files={"test.txt": "Hello {{name}}"},
            post_generation_commands=["echo 'done'"],
            tags=["test"],
        )

        assert template.name == "test_template"
        assert template.description == "Test template"
        assert len(template.parameters) == 1
        assert template.files == {"test.txt": "Hello {{name}}"}
        assert template.post_generation_commands == ["echo 'done'"]
        assert template.tags == ["test"]

    def test_template_engine_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = TemplateEngine(Path(tmpdir))
            assert engine.templates_dir == Path(tmpdir)

    def test_list_templates_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = TemplateEngine(Path(tmpdir))
            templates = engine.list_templates()
            assert templates == []

    def test_list_templates_with_valid_template(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            templates_dir = Path(tmpdir)

            # Create a valid template
            template_dir = templates_dir / "test_template"
            template_dir.mkdir()

            config = {
                "name": "test_template",
                "description": "Test template",
                "parameters": [],
                "tags": ["test"],
            }

            with open(template_dir / "template.json", "w") as f:
                json.dump(config, f)

            engine = TemplateEngine(templates_dir)
            templates = engine.list_templates()
            assert templates == ["test_template"]

    def test_load_template_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = TemplateEngine(Path(tmpdir))

            with pytest.raises(ValueError, match="Template 'nonexistent' not found"):
                engine.load_template("nonexistent")

    def test_load_template_no_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            templates_dir = Path(tmpdir)
            template_dir = templates_dir / "test_template"
            template_dir.mkdir()

            engine = TemplateEngine(templates_dir)

            with pytest.raises(ValueError, match="Template config not found"):
                engine.load_template("test_template")

    def test_load_template_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            templates_dir = Path(tmpdir)
            template_dir = templates_dir / "test_template"
            template_dir.mkdir()

            # Create config
            config = {
                "name": "test_template",
                "description": "Test template",
                "parameters": [
                    {
                        "name": "project_name",
                        "type": "string",
                        "description": "Project name",
                        "required": True,
                    }
                ],
                "post_generation_commands": ["echo 'done'"],
                "tags": ["test"],
            }

            with open(template_dir / "template.json", "w") as f:
                json.dump(config, f)

            # Create files
            files_dir = template_dir / "files"
            files_dir.mkdir()
            with open(files_dir / "README.md", "w") as f:
                f.write("# {{project_name}}")

            engine = TemplateEngine(templates_dir)
            template = engine.load_template("test_template")

            assert template.name == "test_template"
            assert template.description == "Test template"
            assert len(template.parameters) == 1
            assert template.parameters[0].name == "project_name"
            assert template.files == {"README.md": "# {{project_name}}"}
            assert template.post_generation_commands == ["echo 'done'"]
            assert template.tags == ["test"]

    def test_resolve_parameters_success(self):
        engine = TemplateEngine()
        template_params = [
            TemplateParameter("required_param", "string", "Required", required=True),
            TemplateParameter(
                "optional_param",
                "string",
                "Optional",
                default="default",
                required=False,
            ),
            TemplateParameter(
                "choice_param",
                "string",
                "Choice",
                choices=["opt1", "opt2"],
                default="opt1",
            ),
        ]

        user_params = {"required_param": "test_value", "choice_param": "opt2"}

        resolved = engine._resolve_parameters(template_params, user_params)

        assert resolved["required_param"] == "test_value"
        assert resolved["optional_param"] == "default"
        assert resolved["choice_param"] == "opt2"

    def test_resolve_parameters_missing_required(self):
        engine = TemplateEngine()
        template_params = [
            TemplateParameter("required_param", "string", "Required", required=True)
        ]

        user_params = {}

        with pytest.raises(
            ValueError, match="Required parameter missing: required_param"
        ):
            engine._resolve_parameters(template_params, user_params)

    def test_resolve_parameters_invalid_choice(self):
        engine = TemplateEngine()
        template_params = [
            TemplateParameter(
                "choice_param", "string", "Choice", choices=["opt1", "opt2"]
            )
        ]

        user_params = {"choice_param": "invalid"}

        with pytest.raises(
            ValueError, match="Invalid choice for choice_param: invalid"
        ):
            engine._resolve_parameters(template_params, user_params)

    def test_render_string(self):
        engine = TemplateEngine()
        template_str = "Hello {{name}}, you are {{age}} years old!"
        context = {"name": "Alice", "age": 30}

        result = engine._render_string(template_str, context)
        assert result == "Hello Alice, you are 30 years old!"

    def test_generate_project_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            templates_dir = Path(tmpdir)
            template_dir = templates_dir / "test_template"
            template_dir.mkdir()

            # Create config
            config = {
                "name": "test_template",
                "description": "Test template",
                "parameters": [
                    {
                        "name": "project_name",
                        "type": "string",
                        "description": "Project name",
                        "required": True,
                    }
                ],
                "post_generation_commands": ["echo 'Project {{project_name}} created'"],
                "tags": ["test"],
            }

            with open(template_dir / "template.json", "w") as f:
                json.dump(config, f)

            # Create template files
            files_dir = template_dir / "files"
            files_dir.mkdir()
            with open(files_dir / "README.md", "w") as f:
                f.write("# {{project_name}}\n\nThis is the {{project_name}} project.")

            subdir = files_dir / "src"
            subdir.mkdir()
            with open(subdir / "main.py", "w") as f:
                f.write('print("{{project_name}}")')

            # Generate project
            engine = TemplateEngine(templates_dir)
            output_dir = Path(tmpdir) / "output"

            result = engine.generate_project(
                "test_template", output_dir, {"project_name": "MyProject"}
            )

            assert result["template"] == "test_template"
            assert result["output_dir"] == str(output_dir)
            assert result["parameters"]["project_name"] == "MyProject"
            assert len(result["generated_files"]) == 2
            assert result["post_generation_commands"] == [
                "echo 'Project {{project_name}} created'"
            ]

            # Check generated files
            assert (output_dir / "README.md").exists()
            assert (output_dir / "src" / "main.py").exists()

            readme_content = (output_dir / "README.md").read_text()
            assert "# MyProject" in readme_content
            assert "This is the MyProject project." in readme_content

            main_content = (output_dir / "src" / "main.py").read_text()
            assert 'print("MyProject")' in main_content


class TestTemplateValidator:

    def test_validate_template_structure_missing_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent_dir = Path(tmpdir) / "nonexistent"

            is_valid, errors = TemplateValidator.validate_template_structure(
                nonexistent_dir
            )

            assert not is_valid
            assert len(errors) == 1
            assert "does not exist" in errors[0]

    def test_validate_template_structure_missing_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            template_dir = Path(tmpdir)

            is_valid, errors = TemplateValidator.validate_template_structure(
                template_dir
            )

            assert not is_valid
            assert "Missing template.json configuration file" in errors

    def test_validate_template_structure_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            template_dir = Path(tmpdir)

            with open(template_dir / "template.json", "w") as f:
                f.write("invalid json {")

            is_valid, errors = TemplateValidator.validate_template_structure(
                template_dir
            )

            assert not is_valid
            assert any("Invalid JSON" in error for error in errors)

    def test_validate_template_structure_missing_required_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            template_dir = Path(tmpdir)

            config = {"invalid": "config"}
            with open(template_dir / "template.json", "w") as f:
                json.dump(config, f)

            is_valid, errors = TemplateValidator.validate_template_structure(
                template_dir
            )

            assert not is_valid
            assert any(
                "Missing required field" in error and "name" in error
                for error in errors
            )
            assert any(
                "Missing required field" in error and "description" in error
                for error in errors
            )

    def test_validate_template_structure_missing_files_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            template_dir = Path(tmpdir)

            config = {"name": "test", "description": "test template"}
            with open(template_dir / "template.json", "w") as f:
                json.dump(config, f)

            is_valid, errors = TemplateValidator.validate_template_structure(
                template_dir
            )

            assert not is_valid
            assert "Missing 'files' directory" in errors

    def test_validate_template_structure_empty_files_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            template_dir = Path(tmpdir)

            config = {"name": "test", "description": "test template"}
            with open(template_dir / "template.json", "w") as f:
                json.dump(config, f)

            files_dir = template_dir / "files"
            files_dir.mkdir()

            is_valid, errors = TemplateValidator.validate_template_structure(
                template_dir
            )

            assert not is_valid
            assert "Files directory is empty" in errors

    def test_validate_template_structure_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            template_dir = Path(tmpdir)

            config = {"name": "test", "description": "test template"}
            with open(template_dir / "template.json", "w") as f:
                json.dump(config, f)

            files_dir = template_dir / "files"
            files_dir.mkdir()
            with open(files_dir / "test.txt", "w") as f:
                f.write("test content")

            is_valid, errors = TemplateValidator.validate_template_structure(
                template_dir
            )

            assert is_valid
            assert errors == []

    def test_validate_parameters_invalid_structure(self):
        parameters = ["not_a_dict", {"name": "valid"}]

        errors = TemplateValidator._validate_parameters(parameters)

        assert len(errors) >= 1
        assert any("must be a dictionary" in error for error in errors)

    def test_validate_parameters_missing_required_fields(self):
        parameters = [{"name": "test"}]  # Missing type and description

        errors = TemplateValidator._validate_parameters(parameters)

        assert len(errors) >= 2
        assert any("missing required field: type" in error for error in errors)
        assert any("missing required field: description" in error for error in errors)

    def test_validate_parameters_duplicate_names(self):
        parameters = [
            {"name": "test", "type": "string", "description": "First"},
            {"name": "test", "type": "string", "description": "Second"},
        ]

        errors = TemplateValidator._validate_parameters(parameters)

        assert len(errors) >= 1
        assert any("Duplicate parameter name: test" in error for error in errors)

    def test_validate_parameters_invalid_type(self):
        parameters = [{"name": "test", "type": "invalid_type", "description": "Test"}]

        errors = TemplateValidator._validate_parameters(parameters)

        assert len(errors) >= 1
        assert any("Invalid parameter type 'invalid_type'" in error for error in errors)

    def test_generate_test_parameters(self):
        parameters = [
            TemplateParameter("string_param", "string", "String param"),
            TemplateParameter("int_param", "integer", "Int param"),
            TemplateParameter("bool_param", "boolean", "Bool param"),
            TemplateParameter("array_param", "array", "Array param"),
            TemplateParameter(
                "choice_param", "string", "Choice param", choices=["opt1", "opt2"]
            ),
            TemplateParameter(
                "default_param", "string", "Default param", default="default_value"
            ),
        ]

        test_params = TemplateValidator._generate_test_parameters(parameters)

        assert test_params["string_param"] == "test_value"
        assert test_params["int_param"] == 1
        assert test_params["bool_param"] is True
        assert test_params["array_param"] == ["test"]
        assert test_params["choice_param"] == "opt1"
        assert test_params["default_param"] == "default_value"
