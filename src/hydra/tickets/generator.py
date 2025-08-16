"""Ticket generation in YAML format."""

import os
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from hydra.tickets.yaml_handler import TicketYAMLHandler
from hydra.tickets.validator import TicketValidator


class TicketGenerator:
    """Generates tickets in YAML format from project descriptions."""
    
    def __init__(self):
        self.yaml_handler = TicketYAMLHandler()
        self.validator = TicketValidator()
        
    def _analyze_complexity(self, description: str) -> Dict[str, Any]:
        """Analyze project description to determine complexity and ticket recommendations.
        
        Args:
            description: Project description
            
        Returns:
            Dict with complexity analysis
        """
        desc_lower = description.lower()
        
        # Simple single-feature projects (1 ticket)
        simple_keywords = [
            'calculator', 'todo list', 'timer', 'counter', 'converter',
            'clock', 'stopwatch', 'form', 'landing page', 'portfolio',
            'simple', 'basic', 'minimal', 'single page'
        ]
        
        # Complex multi-component projects (2-4 tickets)
        complex_keywords = [
            'dashboard', 'e-commerce', 'platform', 'system', 'api',
            'database', 'authentication', 'payment', 'admin', 'cms',
            'social', 'marketplace', 'saas', 'enterprise'
        ]
        
        # Backend/frontend split indicators
        split_indicators = [
            'with backend', 'and api', 'rest api', 'graphql',
            'full stack', 'frontend and backend', 'client server'
        ]
        
        is_simple = any(kw in desc_lower for kw in simple_keywords)
        is_complex = any(kw in desc_lower for kw in complex_keywords)
        needs_split = any(ind in desc_lower for ind in split_indicators)
        
        # Determine recommended ticket count
        if is_simple and not is_complex:
            recommended_tickets = 1
            rationale = "Simple single-feature project"
        elif needs_split:
            recommended_tickets = 2
            rationale = "Separate frontend and backend work"
        elif is_complex:
            recommended_tickets = 3
            rationale = "Complex multi-component system"
        else:
            # Default to 1 for unknown projects
            recommended_tickets = 1
            rationale = "Default to minimal tickets"
            
        return {
            'recommended_tickets': recommended_tickets,
            'rationale': rationale,
            'is_simple': is_simple,
            'is_complex': is_complex,
            'needs_split': needs_split
        }
        
    def generate_tickets_yaml(self, project_description: str, output_path: str = "tickets.yaml",
                             project_type: Optional[str] = None) -> bool:
        """Generate tickets.yaml from project description.
        
        Args:
            project_description: Description of the project
            output_path: Path to save tickets file
            project_type: Optional project type for templates
            
        Returns:
            True if successful
        """
        print(f"Generating tickets: {output_path}")
        print("=" * 40)
        
        # REMOVED: Template bypass - always use Claude to generate tickets
        
        project_dir = Path(output_path).parent
        
        from hydra.analysis.codebase_analyzer import CodebaseAnalyzer
        analyzer = CodebaseAnalyzer(str(project_dir))
        codebase_analysis = analyzer.analyze()
        
        context = self._build_context(codebase_analysis, analyzer)
        
        from hydra.providers.provider_factory import create_provider_from_environment
        provider = create_provider_from_environment()
        
        # Analyze complexity to guide ticket generation
        complexity = self._analyze_complexity(project_description)
        print(f"📊 Complexity analysis: {complexity['recommended_tickets']} ticket(s) - {complexity['rationale']}")
        
        prompt = self._build_prompt(project_description, context, project_type, complexity)
        
        try:
            if os.environ.get('DEBUG'):
                print(f"Prompt: {prompt[:200]}...")
            # Pass mode="ticket_generation" to ensure opus is used for claude_tmux
            response = provider.generate(prompt, mode="ticket_generation")
            if os.environ.get('DEBUG'):
                print(f"Response: {response[:200]}...")
            
            # Always save debug output for claude_tmux to diagnose issues
            if 'claude_tmux' in str(type(provider)):
                debug_path = Path(output_path).parent / '.hydra' / 'last_claude_response.txt'
                debug_path.parent.mkdir(exist_ok=True, parents=True) 
                debug_path.write_text(response)
                print(f"Debug: Saved Claude's response to {debug_path}")
            
            # Check if Claude created the file directly
            if Path(output_path).exists():
                print(f"✅ Claude created {output_path} directly")
                # Load and validate the file
                try:
                    with open(output_path, 'r') as f:
                        data = yaml.safe_load(f)
                    if data and 'tickets' in data:
                        tickets_data = data['tickets']
                        final_data = data
                        # Validate and fix the tickets Claude created
                        self._validate_and_fix_tickets(final_data, project_description)
                        # Save the fixed version
                        self.yaml_handler.save_tickets(final_data, output_path)
                    else:
                        print("Error: Invalid YAML structure")
                        return False
                except Exception as e:
                    print(f"Error reading created file: {e}")
                    return False
            else:
                # Claude didn't create the file, try to parse response
                if not response:
                    print("Error: No response from provider and no file created")
                    return False
                    
                parsed_data = self._parse_response(response)
                
                # Check if we got the full structure or just tickets
                if isinstance(parsed_data, dict) and 'tickets' in parsed_data:
                    # We have the full structure from Claude
                    final_data = parsed_data
                    tickets_data = final_data['tickets']
                elif isinstance(parsed_data, list):
                    # We have just tickets, build the full structure
                    tickets_data = parsed_data
                    project_name = Path(project_dir).name or "Project"
                    final_data = {
                        'version': '1.0',
                        'project': {
                            'name': project_name,
                            'description': project_description[:500],
                            'created_at': datetime.now().isoformat(),
                            'path': str(project_dir.absolute())
                        },
                        'tickets': tickets_data
                    }
                else:
                    # We have the full structure but without 'project' key
                    if isinstance(parsed_data, dict):
                        final_data = parsed_data
                        if 'project' not in final_data:
                            final_data['project'] = {
                                'name': Path(project_dir).name or "Project",
                                'description': project_description[:500],
                                'created_at': datetime.now().isoformat(),
                                'path': str(project_dir.absolute())
                            }
                        tickets_data = final_data.get('tickets', [])
                    else:
                        raise ValueError(f"Unexpected parsed data type: {type(parsed_data)}")
                
                # Validate and fix tickets before saving
                self._validate_and_fix_tickets(final_data, project_description)
                
                self.yaml_handler.save_tickets(final_data, output_path)
            
            # Sync with dashboard database if it exists
            self._sync_to_dashboard(final_data, str(project_dir))
            
            print(f"\nGenerated {len(tickets_data)} tickets")
            print(f"Saved to: {output_path}")
            
            return True
            
        except Exception as e:
            import traceback
            print(f"Error generating tickets: {e}")
            if os.environ.get('DEBUG'):
                traceback.print_exc()
            return False
            
    def _validate_and_fix_tickets(self, data: Dict[str, Any], project_description: str) -> None:
        """Validate and fix tickets to ensure they are actionable.
        
        Args:
            data: Complete ticket data
            project_description: Original project description
        """
        desc_lower = project_description.lower()
        if 'calculator' in desc_lower:
            project_type = 'calculator'
        elif 'web' in desc_lower:
            project_type = 'web'
        else:
            project_type = None
        
        tickets = data.get('tickets', [])
        
        for ticket in tickets:
            # Validate the ticket
            is_valid, issues = self.validator.validate_ticket(ticket)
            
            if not is_valid:
                print(f"⚠️  Fixing ticket {ticket.get('id', 'unknown')}: {', '.join(issues)}")
                
                # Fix acceptance criteria to be actionable
                if 'acceptance_criteria' in ticket:
                    original_criteria = ticket['acceptance_criteria']
                    fixed_criteria = self.validator.transform_criteria_to_actionable(
                        original_criteria, project_type
                    )
                    
                    # Only update if we made improvements
                    if fixed_criteria != original_criteria:
                        ticket['acceptance_criteria'] = fixed_criteria
                        print(f"   ✅ Fixed {len(fixed_criteria)} acceptance criteria")
                        
                # Ensure model is valid
                if ticket.get('model') not in ['fast', 'balanced', 'smart']:
                    ticket['model'] = 'fast' if 'simple' in project_description.lower() else 'balanced'
                    
                # Ensure status is valid
                if not ticket.get('status'):
                    ticket['status'] = 'TODO'
    
    
    def _sync_to_dashboard(self, data: Dict[str, Any], project_dir: str) -> None:
        """Sync generated tickets to dashboard database.
        
        Args:
            data: Complete ticket data including project info
            project_dir: Project directory path
        """
        try:
            import os
            from hydra.dashboard.database import get_db_manager, Project, Ticket
            from datetime import datetime
            
            # Set database URL to project-specific location if in project directory
            if os.path.exists(os.path.join(project_dir, 'tickets.yaml')) or \
               os.path.exists(os.path.join(project_dir, 'tickets.md')):
                os.environ['DATABASE_URL'] = f"sqlite:///{project_dir}/.hydra/dashboard/hydra.db"
            
            db_manager = get_db_manager()
            with db_manager.get_session() as db:
                # Create or update project
                project_name = data['project']['name']
                project = db.query(Project).filter_by(name=project_name).first()
                
                if not project:
                    project = Project(
                        name=project_name,
                        description=data['project']['description'],
                        repository_url=project_dir,
                        created_at=datetime.now()
                    )
                    db.add(project)
                    db.commit()
                
                # Add tickets
                tickets_added = 0
                for ticket_data in data['tickets']:
                    # Ensure ticket_id is always a string
                    ticket_id = str(ticket_data['id'])
                    existing = db.query(Ticket).filter_by(
                        ticket_number=ticket_id,
                        project_id=project.id
                    ).first()
                    
                    if not existing:
                        ticket = Ticket(
                            ticket_number=ticket_id,
                            title=ticket_data['title'],
                            description=ticket_data.get('description', ''),
                            status=ticket_data.get('status', 'TODO'),
                            priority=str(ticket_data.get('priority', 'medium')),
                            model=ticket_data.get('model', 'balanced'),
                            project_id=project.id,
                            created_at=datetime.now()
                        )
                        db.add(ticket)
                        tickets_added += 1
                
                db.commit()
                print(f"📊 Synced {tickets_added} new tickets to dashboard (total: {len(data['tickets'])} in file)")
                
        except Exception as e:
            # Don't fail ticket generation if dashboard sync fails
            if os.environ.get('DEBUG'):
                print(f"Warning: Could not sync to dashboard: {e}")
    
    def _build_context(self, analysis: Dict[str, Any], analyzer: Any) -> str:
        """Build codebase context string.
        
        Args:
            analysis: Codebase analysis results
            analyzer: CodebaseAnalyzer instance
            
        Returns:
            Context string
        """
        lines = [
            "CODEBASE CONTEXT:",
            f"Type: {analysis.get('project_type', 'Unknown')}",
            f"Framework: {analysis.get('framework', 'None')}",
            f"Stack: {', '.join(analysis.get('tech_stack', []))}",
            f"Size: {analysis.get('size_metrics', {}).get('total_loc', 0)} lines",
            f"Tests: {analysis.get('existing_tests', {}).get('test_count', 0)} test files",
            "",
            "STRUCTURE:",
        ]
        
        dirs = analysis.get('structure', {}).get('directories', [])[:5]
        lines.extend(f"  {d}" for d in dirs)
        
        return '\n'.join(lines)
        
    def _build_prompt(self, description: str, context: str, project_type: Optional[str], 
                      complexity: Dict[str, Any]) -> str:
        """Build prompt for ticket generation.
        
        Args:
            description: Project description
            context: Codebase context
            project_type: Optional project type
            complexity: Complexity analysis results
            
        Returns:
            Prompt string
        """
        # Simple, clear prompt for Claude
        return f"""Create tickets.yaml for: {description}

Generate {complexity['recommended_tickets']} ticket(s).

Use this YAML format and write to tickets.yaml:
```yaml
version: '1.0'
project:
  name: Project Name
  description: {description}
  created_at: '2025-08-15T00:00:00'
  path: .
tickets:
- id: '001'
  title: Build the application
  status: TODO
  priority: 1
  model: fast
  description: Implementation details
  acceptance_criteria:
  - Create index.html with UI elements
  - Create styles.css with styling
  - Create script.js with logic
  dependencies: []
```"""
        
    def _parse_response(self, content: str) -> List[Dict[str, Any]]:
        """Parse LLM response to extract tickets.
        
        Args:
            content: LLM response content
            
        Returns:
            List of ticket dictionaries
        """
        import yaml
        
        # Extract just the YAML content from Claude's output
        # Look for YAML content starting with "version:" or in code blocks
        lines = content.split('\n')
        yaml_lines = []
        in_yaml = False
        in_code_block = False
        
        # Check if this is already clean YAML (starts with - or version:)
        first_meaningful_line = next((l for l in lines if l.strip() and not l.strip().startswith('#')), '')
        if first_meaningful_line.strip().startswith(('-', 'version:', 'tickets:')):
            # This is already clean YAML, don't process it
            yaml_lines = lines
        else:
            # Process to extract YAML from Claude's output
            for line in lines:
                # Check for code block markers
                if line.strip().startswith('```yaml'):
                    in_code_block = True
                    in_yaml = True
                    continue
                elif line.strip() == '```' and in_code_block:
                    break  # End of YAML block
                    
                # Start capturing when we see "version:"
                if line.strip().startswith('version:') or line.strip().startswith("version: '"):
                    in_yaml = True
                    yaml_lines = [line]
                elif in_yaml:
                    # Stop at UI elements or prompts
                    if any(x in line for x in ['╭', '╰', '│', '>', 'Human:', 'Assistant:', '✻', '✽']):
                        break
                    yaml_lines.append(line)
        
        content = '\n'.join(yaml_lines).strip()
        
        if content.startswith('```yaml'):
            content = content[7:]
        elif content.startswith('```'):
            content = content[3:]
            
        if content.endswith('```'):
            content = content[:-3]
            
        content = content.strip()
        
        # Handle empty content
        if not content:
            return []
        
        try:
            data = yaml.safe_load(content)
            
            # Handle None result from YAML (empty document)
            if data is None:
                return []
            
            if os.environ.get('DEBUG'):
                print(f"Parsed YAML type: {type(data)}")
                if isinstance(data, dict):
                    print(f"Dict keys: {list(data.keys())}")
            
            # Handle full YAML structure with project info
            if isinstance(data, dict):
                if 'tickets' in data:
                    # We have the full structure, return it as-is for later processing
                    return data  # Return full data, not just tickets
                else:
                    # Old format - single ticket dict
                    tickets = [data] if 'id' in data else []
            elif isinstance(data, list):
                tickets = data
            else:
                raise ValueError(f"Expected dict with 'tickets' key or list of tickets, got {type(data)}")
                
            # Only process tickets if we don't have the full structure
            for i, ticket in enumerate(tickets):
                if 'id' not in ticket:
                    ticket['id'] = f"{i+1:03d}"
                if 'status' not in ticket:
                    ticket['status'] = 'TODO'
                if 'priority' not in ticket:
                    ticket['priority'] = i + 1
                if 'model' not in ticket:
                    ticket['model'] = 'balanced'
                if 'dependencies' not in ticket:
                    ticket['dependencies'] = []
                if 'acceptance_criteria' not in ticket:
                    ticket['acceptance_criteria'] = []
                    
            return tickets
            
        except yaml.YAMLError as e:
            print(f"Warning: Failed to parse YAML, attempting fallback: {e}")
            return self._fallback_parse(content)
            
    def _fallback_parse(self, content: str) -> List[Dict[str, Any]]:
        """Fallback parser for non-YAML responses.
        
        Args:
            content: Response content
            
        Returns:
            List of ticket dictionaries
        """
        tickets = []
        current_ticket = None
        current_field = None
        current_value = []
        in_acceptance_criteria = False
        
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            original_line = line
            line = line.strip()
            
            # New ticket starts
            if line.startswith('- id:') or (line.startswith('id:') and i == 0):
                # Save previous ticket
                if current_ticket:
                    if current_field == 'description' and current_value:
                        current_ticket['description'] = ' '.join(current_value)
                    tickets.append(current_ticket)
                
                # Start new ticket
                current_ticket = {
                    'id': line.split(':', 1)[1].strip().strip('"\''),
                    'status': 'TODO',
                    'model': 'balanced',
                    'dependencies': [],
                    'acceptance_criteria': [],
                    'priority': 5
                }
                current_field = None
                current_value = []
                in_acceptance_criteria = False
                
            elif current_ticket:
                # Check if this is a new field
                if line.startswith('title:'):
                    if current_field == 'description' and current_value:
                        current_ticket['description'] = ' '.join(current_value)
                    current_ticket['title'] = line.split(':', 1)[1].strip().strip('"\'')
                    current_field = 'title'
                    current_value = []
                    in_acceptance_criteria = False
                    
                elif line.startswith('description:'):
                    desc_part = line.split(':', 1)[1].strip().strip('"\'')
                    current_field = 'description'
                    current_value = [desc_part] if desc_part else []
                    in_acceptance_criteria = False
                    
                elif line.startswith('priority:'):
                    if current_field == 'description' and current_value:
                        current_ticket['description'] = ' '.join(current_value)
                    try:
                        current_ticket['priority'] = int(line.split(':', 1)[1].strip())
                    except:
                        current_ticket['priority'] = 5
                    current_field = 'priority'
                    current_value = []
                    in_acceptance_criteria = False
                    
                elif line.startswith('model:'):
                    if current_field == 'description' and current_value:
                        current_ticket['description'] = ' '.join(current_value)
                    current_ticket['model'] = line.split(':', 1)[1].strip().strip('"\'')
                    current_field = 'model'
                    current_value = []
                    in_acceptance_criteria = False
                    
                elif line.startswith('status:'):
                    if current_field == 'description' and current_value:
                        current_ticket['description'] = ' '.join(current_value)
                    current_ticket['status'] = line.split(':', 1)[1].strip().strip('"\'')
                    current_field = 'status'
                    current_value = []
                    in_acceptance_criteria = False
                    
                elif line.startswith('dependencies:'):
                    if current_field == 'description' and current_value:
                        current_ticket['description'] = ' '.join(current_value)
                    deps = line.split(':', 1)[1].strip()
                    if deps and deps != '[]':
                        import re
                        deps_list = re.findall(r'"([^"]+)"', deps)
                        current_ticket['dependencies'] = deps_list
                    current_field = 'dependencies'
                    current_value = []
                    in_acceptance_criteria = False
                    
                elif line.startswith('acceptance_criteria:'):
                    if current_field == 'description' and current_value:
                        current_ticket['description'] = ' '.join(current_value)
                    in_acceptance_criteria = True
                    current_field = 'acceptance_criteria'
                    current_value = []
                    
                elif in_acceptance_criteria and line.startswith('- '):
                    current_ticket['acceptance_criteria'].append(line[2:].strip())
                    
                elif current_field == 'description' and line and not line.startswith('-'):
                    # Continuation of description
                    current_value.append(line)
                    
        # Save last ticket
        if current_ticket:
            if current_field == 'description' and current_value:
                current_ticket['description'] = ' '.join(current_value)
            tickets.append(current_ticket)
            
        return tickets