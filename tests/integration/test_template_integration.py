import pytest
import json
import tempfile
from pathlib import Path

from hydra.templates import TemplateEngine, TemplateValidator


class TestTemplateIntegration:
    """Integration tests for template functionality using real template structures."""
    
    def setup_method(self):
        """Set up a temporary directory with sample templates for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.templates_dir = Path(self.temp_dir) / "templates"
        self.templates_dir.mkdir()
        
        # Create a comprehensive test template
        self._create_web_app_template()
        self._create_cli_tool_template()
        self._create_invalid_template()
        
        self.engine = TemplateEngine(self.templates_dir)
    
    def teardown_method(self):
        """Clean up temporary directory after each test."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def _create_web_app_template(self):
        """Create a realistic web application template."""
        template_dir = self.templates_dir / "web_app"
        template_dir.mkdir()
        
        config = {
            "name": "web_app",
            "description": "A complete web application with frontend and backend",
            "parameters": [
                {
                    "name": "app_name",
                    "type": "string",
                    "description": "Application name",
                    "required": True
                },
                {
                    "name": "database",
                    "type": "string",
                    "description": "Database type",
                    "choices": ["postgresql", "mysql", "sqlite"],
                    "default": "postgresql"
                },
                {
                    "name": "include_auth",
                    "type": "boolean",
                    "description": "Include authentication system",
                    "default": True
                },
                {
                    "name": "port",
                    "type": "integer",
                    "description": "Server port",
                    "default": 8000
                }
            ],
            "post_generation_commands": [
                "npm install",
                "pip install -r requirements.txt",
                "python manage.py migrate"
            ],
            "tags": ["web", "full-stack", "python", "javascript"]
        }
        
        with open(template_dir / "template.json", "w") as f:
            json.dump(config, f, indent=2)
        
        # Create template files
        files_dir = template_dir / "files"
        files_dir.mkdir()
        
        # Main application file
        with open(files_dir / "app.py", "w") as f:
            f.write('''from flask import Flask
{% if include_auth %}from flask_login import LoginManager{% endif %}

app = Flask("{{app_name}}")
{% if database == 'postgresql' %}
app.config['DATABASE_URL'] = 'postgresql://localhost/{{app_name}}'
{% elif database == 'mysql' %}
app.config['DATABASE_URL'] = 'mysql://localhost/{{app_name}}'
{% else %}
app.config['DATABASE_URL'] = 'sqlite:///{{app_name}}.db'
{% endif %}

{% if include_auth %}
login_manager = LoginManager()
login_manager.init_app(app)
{% endif %}

if __name__ == '__main__':
    app.run(port={{port}})
''')
        
        # Package.json for frontend
        with open(files_dir / "package.json", "w") as f:
            f.write('''{
  "name": "{{app_name}}-frontend",
  "version": "1.0.0",
  "scripts": {
    "start": "npm run dev",
    "dev": "vite",
    "build": "vite build"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  }
}
''')
        
        # Requirements file
        with open(files_dir / "requirements.txt", "w") as f:
            f.write('''Flask>=2.0.0
{% if include_auth %}Flask-Login>=0.6.0{% endif %}
{% if database == 'postgresql' %}psycopg2>=2.9.0{% endif %}
{% if database == 'mysql' %}PyMySQL>=1.0.0{% endif %}
''')
        
        # Create nested directories
        static_dir = files_dir / "static" / "css"
        static_dir.mkdir(parents=True)
        with open(static_dir / "style.css", "w") as f:
            f.write('''/* {{app_name}} Styles */
body {
    font-family: Arial, sans-serif;
    margin: 0;
    padding: 20px;
}
''')
        
        # Config with variable in path
        config_dir = files_dir / "config"
        config_dir.mkdir()
        with open(config_dir / "{{app_name}}_config.py", "w") as f:
            f.write('''# Configuration for {{app_name}}
DEBUG = True
PORT = {{port}}
DATABASE = "{{database}}"
AUTH_ENABLED = {{include_auth}}
''')
    
    def _create_cli_tool_template(self):
        """Create a simple CLI tool template."""
        template_dir = self.templates_dir / "cli_tool"
        template_dir.mkdir()
        
        config = {
            "name": "cli_tool",
            "description": "A command-line tool with argument parsing",
            "parameters": [
                {
                    "name": "tool_name",
                    "type": "string",
                    "description": "Name of the CLI tool",
                    "required": True
                },
                {
                    "name": "language",
                    "type": "string",
                    "description": "Programming language",
                    "choices": ["python", "javascript", "rust"],
                    "default": "python"
                }
            ],
            "post_generation_commands": [
                "chmod +x {{tool_name}}"
            ],
            "tags": ["cli", "tool"]
        }
        
        with open(template_dir / "template.json", "w") as f:
            json.dump(config, f, indent=2)
        
        files_dir = template_dir / "files"
        files_dir.mkdir()
        
        with open(files_dir / "{{tool_name}}.py", "w") as f:
            f.write('''#!/usr/bin/env python3
import argparse

def main():
    parser = argparse.ArgumentParser(description="{{tool_name}} - A CLI tool")
    parser.add_argument("--version", action="version", version="{{tool_name}} 1.0.0")
    args = parser.parse_args()
    print("Welcome to {{tool_name}}!")

if __name__ == "__main__":
    main()
''')
    
    def _create_invalid_template(self):
        """Create an invalid template for testing validation."""
        template_dir = self.templates_dir / "invalid_template"
        template_dir.mkdir()
        
        # Missing required fields in config
        config = {
            "name": "invalid_template"
            # Missing description
        }
        
        with open(template_dir / "template.json", "w") as f:
            json.dump(config, f, indent=2)
        
        # Create files directory but leave it empty
        files_dir = template_dir / "files"
        files_dir.mkdir()
    
    def test_list_templates_returns_all_valid(self):
        """Test that list_templates returns only valid templates."""
        templates = self.engine.list_templates()
        
        # Should include valid templates
        assert "web_app" in templates
        assert "cli_tool" in templates
        # Should include invalid template (list doesn't validate)
        assert "invalid_template" in templates
        assert len(templates) == 3
    
    def test_load_valid_web_app_template(self):
        """Test loading a complex web application template."""
        template = self.engine.load_template("web_app")
        
        assert template.name == "web_app"
        assert template.description == "A complete web application with frontend and backend"
        assert len(template.parameters) == 4
        assert len(template.files) == 5  # app.py, package.json, requirements.txt, style.css, config file
        assert len(template.post_generation_commands) == 3
        assert "web" in template.tags
        assert "full-stack" in template.tags
        
        # Check parameter details
        param_names = [p.name for p in template.parameters]
        assert "app_name" in param_names
        assert "database" in param_names
        assert "include_auth" in param_names
        assert "port" in param_names
        
        # Check that files were loaded correctly
        assert "app.py" in template.files
        assert "package.json" in template.files
        assert "requirements.txt" in template.files
        assert "static/css/style.css" in template.files
        assert "config/{{app_name}}_config.py" in template.files
    
    def test_load_simple_cli_template(self):
        """Test loading a simple CLI tool template."""
        template = self.engine.load_template("cli_tool")
        
        assert template.name == "cli_tool"
        assert len(template.parameters) == 2
        assert len(template.files) == 1
        assert "{{tool_name}}.py" in template.files
        assert template.post_generation_commands == ["chmod +x {{tool_name}}"]
    
    def test_generate_web_app_project(self):
        """Test generating a complete web application project."""
        output_dir = Path(self.temp_dir) / "generated_web_app"
        
        parameters = {
            "app_name": "MyWebApp",
            "database": "postgresql",
            "include_auth": True,
            "port": 5000
        }
        
        result = self.engine.generate_project("web_app", output_dir, parameters)
        
        assert result["template"] == "web_app"
        assert result["parameters"]["app_name"] == "MyWebApp"
        assert result["parameters"]["database"] == "postgresql"
        assert result["parameters"]["include_auth"] is True
        assert result["parameters"]["port"] == 5000
        assert len(result["generated_files"]) == 5
        
        # Check that files were generated correctly
        assert (output_dir / "app.py").exists()
        assert (output_dir / "package.json").exists()
        assert (output_dir / "requirements.txt").exists()
        assert (output_dir / "static" / "css" / "style.css").exists()
        assert (output_dir / "config" / "MyWebApp_config.py").exists()
        
        # Verify content rendering
        app_content = (output_dir / "app.py").read_text()
        assert 'Flask("MyWebApp")' in app_content
        assert "postgresql://localhost/MyWebApp" in app_content
        assert "from flask_login import LoginManager" in app_content
        assert "app.run(port=5000)" in app_content
        
        package_content = (output_dir / "package.json").read_text()
        assert '"name": "MyWebApp-frontend"' in package_content
        
        config_content = (output_dir / "config" / "MyWebApp_config.py").read_text()
        assert "PORT = 5000" in config_content
        assert 'DATABASE = "postgresql"' in config_content
        assert "AUTH_ENABLED = True" in config_content
    
    def test_generate_cli_tool_project(self):
        """Test generating a CLI tool project."""
        output_dir = Path(self.temp_dir) / "generated_cli"
        
        parameters = {
            "tool_name": "mytool",
            "language": "python"
        }
        
        result = self.engine.generate_project("cli_tool", output_dir, parameters)
        
        assert (output_dir / "mytool.py").exists()
        
        tool_content = (output_dir / "mytool.py").read_text()
        assert "mytool - A CLI tool" in tool_content
        assert 'version="mytool 1.0.0"' in tool_content
        assert "Welcome to mytool!" in tool_content
    
    def test_generate_with_different_database_choices(self):
        """Test generating projects with different parameter choices."""
        output_dir = Path(self.temp_dir) / "generated_mysql"
        
        parameters = {
            "app_name": "MySQLApp",
            "database": "mysql",
            "include_auth": False,
            "port": 3000
        }
        
        self.engine.generate_project("web_app", output_dir, parameters)
        
        app_content = (output_dir / "app.py").read_text()
        assert "mysql://localhost/MySQLApp" in app_content
        assert "from flask_login import LoginManager" not in app_content
        assert "app.run(port=3000)" in app_content
        
        requirements_content = (output_dir / "requirements.txt").read_text()
        assert "PyMySQL" in requirements_content
        assert "Flask-Login" not in requirements_content
    
    def test_validate_all_templates(self):
        """Test validation of all templates in the directory."""
        results = TemplateValidator.validate_all_templates(self.templates_dir)
        
        assert len(results) == 3
        assert "web_app" in results
        assert "cli_tool" in results
        assert "invalid_template" in results
        
        # Valid templates should pass
        assert results["web_app"][0] is True
        assert results["cli_tool"][0] is True
        
        # Invalid template should fail
        assert results["invalid_template"][0] is False
        assert len(results["invalid_template"][1]) > 0  # Should have errors
    
    def test_template_caching(self):
        """Test that templates are cached after first load."""
        # Load template twice
        template1 = self.engine.load_template("web_app")
        template2 = self.engine.load_template("web_app")
        
        # Should return the same cached instance
        assert template1 is template2
    
    def test_parameter_validation_edge_cases(self):
        """Test parameter validation with edge cases."""
        output_dir = Path(self.temp_dir) / "validation_test"
        
        # Test missing required parameter
        with pytest.raises(ValueError, match="Required parameter missing: app_name"):
            self.engine.generate_project("web_app", output_dir, {"database": "postgresql"})
        
        # Test invalid choice
        with pytest.raises(ValueError, match="Invalid choice for database: oracle"):
            self.engine.generate_project("web_app", output_dir, {
                "app_name": "TestApp",
                "database": "oracle"
            })
    
    def test_complex_template_rendering(self):
        """Test complex template rendering with nested conditionals."""
        output_dir = Path(self.temp_dir) / "complex_render"
        
        # Test with SQLite database and no auth
        parameters = {
            "app_name": "SimpleApp",
            "database": "sqlite",
            "include_auth": False,
            "port": 8080
        }
        
        self.engine.generate_project("web_app", output_dir, parameters)
        
        app_content = (output_dir / "app.py").read_text()
        assert "sqlite:///SimpleApp.db" in app_content
        assert 'Flask("SimpleApp")' in app_content
        assert "LoginManager" not in app_content
        
        requirements_content = (output_dir / "requirements.txt").read_text()
        assert "psycopg2" not in requirements_content
        assert "PyMySQL" not in requirements_content
        assert "Flask-Login" not in requirements_content
    
    def test_template_file_path_rendering(self):
        """Test that file paths with template variables are rendered correctly."""
        output_dir = Path(self.temp_dir) / "path_render"
        
        parameters = {
            "app_name": "PathTestApp",
            "database": "postgresql",
            "include_auth": True,
            "port": 9000
        }
        
        self.engine.generate_project("web_app", output_dir, parameters)
        
        # Check that the config file path was rendered correctly
        config_file = output_dir / "config" / "PathTestApp_config.py"
        assert config_file.exists()
        
        config_content = config_file.read_text()
        assert "Configuration for PathTestApp" in config_content