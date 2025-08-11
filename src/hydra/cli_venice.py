"""Venice CLI commands for Hydra."""

import os
import sys
from pathlib import Path

import click
import requests


@click.group()
def venice():
    """Venice AI provider commands."""
    pass


@venice.command()
def list_models():
    """List all available Venice models."""
    api_key = os.getenv("VENICE_API_KEY")
    if not api_key:
        click.echo("❌ VENICE_API_KEY not found in environment")
        click.echo("   Get your key at: https://venice.ai")
        sys.exit(1)
    
    url = "https://api.venice.ai/api/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        models = response.json()
        click.echo("Available Venice Models:")
        click.echo("=" * 60)
        
        # Categorize models
        coding_models = []
        general_models = []
        
        for model in models.get("data", []):
            model_id = model.get("id", "unknown")
            if "coder" in model_id or "code" in model_id:
                coding_models.append(model_id)
            else:
                general_models.append(model_id)
        
        if coding_models:
            click.echo("\n🔧 Coding Models (Recommended for Hydra):")
            for model in sorted(coding_models):
                click.echo(f"  - {model}")
        
        if general_models:
            click.echo("\n📚 General Purpose Models:")
            for model in sorted(general_models):
                click.echo(f"  - {model}")
        
    except requests.exceptions.RequestException as e:
        click.echo(f"❌ Error fetching models: {e}")
        sys.exit(1)


@venice.command()
def test():
    """Test Venice API connection."""
    api_key = os.getenv("VENICE_API_KEY")
    if not api_key:
        click.echo("❌ VENICE_API_KEY not found")
        sys.exit(1)
    
    click.echo("Testing Venice API connection...")
    
    # Add src to path if needed
    src_path = Path(__file__).parent.parent
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    
    try:
        from hydra.providers.venice import VeniceProvider
        from hydra.providers.base import LLMConfig
        
        config = LLMConfig(
            provider_type="venice",
            model="llama-3.2-3b",  # Use small model for test
            api_key=api_key,
            base_url="https://api.venice.ai/api/v1",
            max_tokens=100
        )
        
        provider = VeniceProvider(config)
        
        # Simple test generation
        response = provider.generate("Say 'Venice API is working!' and nothing else.")
        
        click.echo("✅ Venice API connection successful!")
        click.echo(f"Response: {response[:100]}")
        
    except Exception as e:
        click.echo(f"❌ Connection failed: {e}")
        sys.exit(1)


@venice.command()
@click.option('--model', default='qwen-2.5-coder-32b', help='Model to use')
@click.option('--output', '-o', type=click.Path(), help='Output directory')
@click.argument('prompt')
def generate(model, output, prompt):
    """Generate code using Venice AI."""
    api_key = os.getenv("VENICE_API_KEY")
    if not api_key:
        click.echo("❌ VENICE_API_KEY not found")
        sys.exit(1)
    
    # Add src to path if needed
    src_path = Path(__file__).parent.parent
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    
    try:
        from hydra.providers.venice import VeniceProvider
        from hydra.providers.base import LLMConfig
        
        click.echo(f"🚀 Generating with {model}...")
        
        config = LLMConfig(
            provider_type="venice",
            model=model,
            api_key=api_key,
            base_url="https://api.venice.ai/api/v1",
            temperature=0.3,
            max_tokens=2000
        )
        
        provider = VeniceProvider(config)
        
        if output:
            # Execute as ticket to create files
            output_dir = Path(output)
            output_dir.mkdir(exist_ok=True, parents=True)
            
            result = provider.execute_ticket(
                ticket_content=prompt,
                working_directory=output_dir
            )
            
            if result['success']:
                click.echo(f"✅ Generated {result['actions_executed']} files in {output}")
            else:
                click.echo(f"⚠️  Generation completed with issues: {result['errors']}")
        else:
            # Simple generation to stdout
            response = provider.generate(prompt)
            click.echo("\n" + response)
        
    except Exception as e:
        click.echo(f"❌ Generation failed: {e}")
        sys.exit(1)


@venice.command()
def setup():
    """Interactive setup wizard for Venice provider."""
    click.echo("Venice AI Setup Wizard")
    click.echo("=" * 40)
    
    # Check for existing key
    existing_key = os.getenv("VENICE_API_KEY")
    if existing_key:
        click.echo(f"✅ Existing API key found: {existing_key[:10]}...")
        if not click.confirm("Do you want to update it?"):
            return
    
    # Get API key
    click.echo("\n1. Get your API key from: https://venice.ai")
    api_key = click.prompt("2. Enter your Venice API key", hide_input=True)
    
    # Test the key
    click.echo("\n3. Testing API key...")
    url = "https://api.venice.ai/api/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        click.echo("   ✅ API key is valid!")
    except:
        click.echo("   ❌ Invalid API key")
        sys.exit(1)
    
    # Save to .env
    env_file = Path.cwd() / ".env"
    
    if env_file.exists():
        click.echo(f"\n4. Updating {env_file}")
        # Read existing content
        content = env_file.read_text()
        lines = content.split('\n')
        
        # Update or add Venice config
        updated = False
        new_lines = []
        for line in lines:
            if line.startswith("VENICE_API_KEY="):
                new_lines.append(f"VENICE_API_KEY={api_key}")
                updated = True
            elif line.startswith("LLM_PROVIDER="):
                new_lines.append("LLM_PROVIDER=venice")
            else:
                new_lines.append(line)
        
        if not updated:
            # Add Venice config if not present
            new_lines.insert(0, f"VENICE_API_KEY={api_key}")
            new_lines.insert(0, "LLM_PROVIDER=venice")
        
        env_file.write_text('\n'.join(new_lines))
    else:
        click.echo(f"\n4. Creating {env_file}")
        env_file.write_text(f"LLM_PROVIDER=venice\nVENICE_API_KEY={api_key}\n")
    
    click.echo("\n✅ Venice setup complete!")
    click.echo("\nYou can now use Venice with Hydra:")
    click.echo("  hydra ticket create 'your project description'")
    click.echo("  hydra ticket parallel --workers 4")


if __name__ == "__main__":
    venice()