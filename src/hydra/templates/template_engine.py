import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader


@dataclass
class TemplateParameter:
    name: str
    type: str
    description: str
    default: Optional[Any] = None
    required: bool = True
    choices: Optional[List[str]] = None


@dataclass
class Template:
    name: str
    description: str
    parameters: List[TemplateParameter]
    files: Dict[str, str]
    post_generation_commands: List[str]
    tags: List[str]


class TemplateEngine:
    def __init__(self, templates_dir: Optional[Path] = None):
        if templates_dir is None:
            templates_dir = Path(__file__).parent / 'templates'

        self.templates_dir = Path(templates_dir)
        self.jinja_env = Environment(loader=FileSystemLoader(str(self.templates_dir)))
        self._templates_cache = {}

    def load_template(self, template_name: str) -> Template:
        if template_name in self._templates_cache:
            return self._templates_cache[template_name]

        template_dir = self.templates_dir / template_name
        if not template_dir.exists():
            raise ValueError(f"Template '{template_name}' not found")

        config_path = template_dir / 'template.json'
        if not config_path.exists():
            raise ValueError(f"Template config not found: {config_path}")

        with open(config_path) as f:
            config = json.load(f)

        parameters = [
            TemplateParameter(**param) for param in config.get('parameters', [])
        ]

        files = {}
        files_dir = template_dir / 'files'
        if files_dir.exists():
            for file_path in files_dir.rglob('*'):
                if file_path.is_file():
                    rel_path = file_path.relative_to(files_dir)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        files[str(rel_path)] = f.read()

        template = Template(
            name=config['name'],
            description=config['description'],
            parameters=parameters,
            files=files,
            post_generation_commands=config.get('post_generation_commands', []),
            tags=config.get('tags', [])
        )

        self._templates_cache[template_name] = template
        return template

    def list_templates(self) -> List[str]:
        if not self.templates_dir.exists():
            return []

        templates = []
        for item in self.templates_dir.iterdir():
            if item.is_dir() and (item / 'template.json').exists():
                templates.append(item.name)

        return sorted(templates)

    def generate_project(self, template_name: str, output_dir: Path,
                        parameters: Dict[str, Any]) -> Dict[str, Any]:
        template = self.load_template(template_name)

        resolved_params = self._resolve_parameters(template.parameters, parameters)

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        generated_files = []
        for file_path, content in template.files.items():
            rendered_path = self._render_string(file_path, resolved_params)
            rendered_content = self._render_string(content, resolved_params)

            full_path = output_dir / rendered_path
            full_path.parent.mkdir(parents=True, exist_ok=True)

            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(rendered_content)

            generated_files.append(str(full_path))

        return {
            'template': template_name,
            'output_dir': str(output_dir),
            'parameters': resolved_params,
            'generated_files': generated_files,
            'post_generation_commands': template.post_generation_commands
        }

    def _resolve_parameters(self, template_params: List[TemplateParameter],
                           user_params: Dict[str, Any]) -> Dict[str, Any]:
        resolved = {}

        for param in template_params:
            if param.name in user_params:
                value = user_params[param.name]
                if param.choices and value not in param.choices:
                    raise ValueError(f"Invalid choice for {param.name}: {value}")
                resolved[param.name] = value
            elif param.default is not None:
                resolved[param.name] = param.default
            elif param.required:
                raise ValueError(f"Required parameter missing: {param.name}")

        return resolved

    def _render_string(self, template_str: str, context: Dict[str, Any]) -> str:
        template = self.jinja_env.from_string(template_str)
        return template.render(**context)

