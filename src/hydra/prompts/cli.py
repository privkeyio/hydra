"""CLI interface for prompt versioning and management."""

import json
import sys
from datetime import timedelta
from typing import List, Optional

import click

from .versioning import get_version_manager


@click.group()
def prompt_cli():
    """Prompt versioning and management CLI."""
    pass


@prompt_cli.command()
@click.option('--content', '-c', help='JSON content for the version')
@click.option('--file', '-f', help='Path to JSON file with content')
@click.option('--version-id', '-v', help='Custom version ID')
def create_version(content: Optional[str], file: Optional[str], version_id: Optional[str]):
    """Create a new prompt version."""
    if not content and not file:
        click.echo("Error: Must provide either --content or --file", err=True)
        sys.exit(1)

    if content and file:
        click.echo("Error: Cannot provide both --content and --file", err=True)
        sys.exit(1)

    try:
        if file:
            with open(file, 'r') as f:
                content_data = json.load(f)
        else:
            content_data = json.loads(content)

        manager = get_version_manager()
        created_version_id = manager.create_version(content_data, version_id)

        click.echo(f"Created version: {created_version_id}")

    except (json.JSONDecodeError, FileNotFoundError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@prompt_cli.command()
@click.option('--limit', '-l', default=10, help='Maximum number of versions to list')
@click.option('--format', '-f', type=click.Choice(['table', 'json']), default='table')
def list_versions(limit: int, format: str):
    """List prompt versions."""
    manager = get_version_manager()
    versions = manager.list_versions(limit=limit)

    if format == 'json':
        version_data = []
        for v in versions:
            version_data.append({
                'version_id': v.version_id,
                'timestamp': v.timestamp.isoformat(),
                'performance_score': v.performance_score,
                'usage_count': v.usage_count,
                'success_rate': v.success_rate
            })
        click.echo(json.dumps(version_data, indent=2))
    else:
        if not versions:
            click.echo("No versions found.")
            return

        click.echo(f"{'Version ID':<20} {'Timestamp':<20} {'Score':<8} {'Usage':<8} {'Success':<8}")
        click.echo("-" * 72)

        for v in versions:
            timestamp_str = v.timestamp.strftime('%Y-%m-%d %H:%M')
            click.echo(f"{v.version_id:<20} {timestamp_str:<20} {v.performance_score:<8.2f} "
                      f"{v.usage_count:<8} {v.success_rate:<8.2f}")


@prompt_cli.command()
@click.argument('version_id')
@click.option('--format', '-f', type=click.Choice(['json', 'yaml']), default='json')
def show_version(version_id: str, format: str):
    """Show details of a specific version."""
    manager = get_version_manager()
    version = manager.get_version(version_id)

    if not version:
        click.echo(f"Version '{version_id}' not found.", err=True)
        sys.exit(1)

    if format == 'json':
        version_data = {
            'version_id': version.version_id,
            'content_hash': version.content_hash,
            'timestamp': version.timestamp.isoformat(),
            'content': version.content,
            'performance_score': version.performance_score,
            'usage_count': version.usage_count,
            'success_rate': version.success_rate,
            'avg_execution_time': version.avg_execution_time,
            'metadata': version.metadata
        }
        click.echo(json.dumps(version_data, indent=2))
    else:
        import yaml
        version_data = {
            'version_id': version.version_id,
            'content_hash': version.content_hash,
            'timestamp': version.timestamp.isoformat(),
            'content': version.content,
            'performance': {
                'score': version.performance_score,
                'usage_count': version.usage_count,
                'success_rate': version.success_rate,
                'avg_execution_time': version.avg_execution_time
            },
            'metadata': version.metadata
        }
        click.echo(yaml.dump(version_data, default_flow_style=False))


@prompt_cli.command()
@click.argument('version_id')
def rollback(version_id: str):
    """Rollback to a specific version."""
    manager = get_version_manager()

    if not manager.get_version(version_id):
        click.echo(f"Version '{version_id}' not found.", err=True)
        sys.exit(1)

    if manager.rollback_to_version(version_id):
        click.echo(f"Successfully rolled back to version: {version_id}")
    else:
        click.echo("Rollback failed.", err=True)
        sys.exit(1)


@prompt_cli.command()
@click.argument('version_id')
@click.option('--force', '-f', is_flag=True, help='Force deletion without confirmation')
def delete_version(version_id: str, force: bool):
    """Delete a version."""
    manager = get_version_manager()

    if not manager.get_version(version_id):
        click.echo(f"Version '{version_id}' not found.", err=True)
        sys.exit(1)

    if not force:
        if not click.confirm(f"Are you sure you want to delete version '{version_id}'?"):
            click.echo("Deletion cancelled.")
            return

    if manager.delete_version(version_id):
        click.echo(f"Successfully deleted version: {version_id}")
    else:
        click.echo("Deletion failed.", err=True)
        sys.exit(1)


@prompt_cli.command()
@click.argument('test_id')
@click.option('--variants', '-v', help='JSON string with variants: {"control": "...", "test": "..."}')
@click.option('--split', '-s', help='JSON string with traffic split: {"control": 0.5, "test": 0.5}')
def create_ab_test(test_id: str, variants: str, split: Optional[str]):
    """Create A/B test configuration."""
    try:
        variants_data = json.loads(variants)
        split_data = json.loads(split) if split else None

        manager = get_version_manager()
        ab_test = manager.create_ab_test(test_id, variants_data, split_data)

        click.echo(f"Created A/B test: {test_id}")
        click.echo(f"Variants: {list(ab_test.variants.keys())}")
        click.echo(f"Traffic split: {ab_test.traffic_split}")

    except json.JSONDecodeError as e:
        click.echo(f"Error parsing JSON: {e}", err=True)
        sys.exit(1)


@prompt_cli.command()
@click.argument('test_id')
@click.argument('user_id')
def get_variant(test_id: str, user_id: str):
    """Get A/B test variant for a user."""
    manager = get_version_manager()
    variant = manager.get_ab_test_variant(test_id, user_id)

    if variant:
        click.echo(f"User '{user_id}' assigned to variant: {variant}")
    else:
        click.echo(f"No active A/B test found for: {test_id}")


@prompt_cli.command()
@click.argument('prompt_name')
@click.option('--variant', '-v', default='default', help='Prompt variant')
@click.option('--days', '-d', default=7, help='Number of days to analyze')
@click.option('--format', '-f', type=click.Choice(['table', 'json']), default='table')
def performance(prompt_name: str, variant: str, days: int, format: str):
    """Show prompt performance metrics."""
    manager = get_version_manager()

    time_window = timedelta(days=days) if days > 0 else None
    perf = manager.get_prompt_performance(prompt_name, variant, time_window)

    if format == 'json':
        click.echo(json.dumps(perf, indent=2))
    else:
        if perf['total_count'] == 0:
            click.echo(f"No performance data found for '{prompt_name}' (variant: {variant})")
            return

        click.echo(f"Performance for '{prompt_name}' (variant: {variant})")
        click.echo(f"Time window: {days} days" if days > 0 else "All time")
        click.echo("-" * 50)
        click.echo(f"Total usage: {perf['total_count']}")
        click.echo(f"Success rate: {perf['success_rate']:.1%}")
        click.echo(f"Avg execution time: {perf['avg_execution_time']:.2f}s")
        click.echo(f"Successful executions: {perf['success_count']}")


@prompt_cli.command()
@click.argument('prompt_name')
@click.option('--format', '-f', type=click.Choice(['table', 'json']), default='table')
def suggestions(prompt_name: str, format: str):
    """Get optimization suggestions for a prompt."""
    manager = get_version_manager()
    suggestions = manager.get_optimization_suggestions(prompt_name)

    if format == 'json':
        click.echo(json.dumps(suggestions, indent=2))
    else:
        if not suggestions:
            click.echo(f"No optimization suggestions for '{prompt_name}'")
            return

        click.echo(f"Optimization suggestions for '{prompt_name}':")
        click.echo("-" * 50)

        for i, suggestion in enumerate(suggestions, 1):
            severity_color = {
                'high': 'red',
                'medium': 'yellow',
                'low': 'green'
            }.get(suggestion['severity'], 'white')

            click.echo(f"{i}. [{click.style(suggestion['severity'].upper(), fg=severity_color)}] "
                      f"{suggestion['type'].title()}")
            click.echo(f"   {suggestion['message']}")
            if 'metric_value' in suggestion:
                click.echo(f"   Current value: {suggestion['metric_value']}")
            click.echo()


@prompt_cli.command()
@click.option('--enable/--disable', default=True, help='Enable or disable hot reload')
@click.option('--directories', '-d', multiple=True, help='Directories to watch')
def watch(enable: bool, directories: List[str]):
    """Start file watcher for hot reload."""
    if not enable:
        click.echo("Hot reload disabled")
        return

    watch_dirs = list(directories) if directories else None
    manager = get_version_manager(enable_hot_reload=True, watch_directories=watch_dirs)

    def reload_callback(file_path: str):
        click.echo(f"File changed: {file_path}")

    manager.add_reload_callback(reload_callback)

    click.echo("Hot reload enabled. Watching for changes...")
    click.echo("Press Ctrl+C to stop")

    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo("\nStopping file watcher...")
        manager.cleanup()


@prompt_cli.command()
@click.argument('prompt_name')
@click.argument('execution_time', type=float)
@click.argument('success', type=bool)
@click.option('--variant', '-v', default='default', help='Prompt variant')
@click.option('--metadata', '-m', help='JSON metadata')
def record_usage(prompt_name: str, execution_time: float, success: bool,
                variant: str, metadata: Optional[str]):
    """Record prompt usage metrics."""
    try:
        metadata_data = json.loads(metadata) if metadata else {}

        from .versioning import record_prompt_usage
        record_prompt_usage(
            prompt_name=prompt_name,
            execution_time=execution_time,
            success=success,
            variant=variant,
            metadata=metadata_data
        )

        click.echo(f"Recorded usage for '{prompt_name}' (variant: {variant})")
        click.echo(f"Execution time: {execution_time}s, Success: {success}")

    except json.JSONDecodeError as e:
        click.echo(f"Error parsing metadata JSON: {e}", err=True)
        sys.exit(1)


@prompt_cli.command()
def status():
    """Show prompt system status."""
    manager = get_version_manager()

    # Count versions
    versions = manager.list_versions(limit=1000)  # Get all versions
    version_count = len(versions)

    # Get recent performance data
    manager.flush_metrics()

    # Show status
    click.echo("Prompt Versioning System Status")
    click.echo("=" * 35)
    click.echo(f"Total versions: {version_count}")
    click.echo(f"Database path: {manager.db_path}")
    click.echo(f"Hot reload: {'Enabled' if manager.enable_hot_reload else 'Disabled'}")
    click.echo(f"Watch directories: {manager.watch_directories}")
    click.echo(f"Metrics buffer: {len(manager._metrics_buffer)} pending")

    if versions:
        latest = versions[0]
        click.echo(f"Latest version: {latest.version_id}")
        click.echo(f"Latest timestamp: {latest.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    prompt_cli()
