"""Ticket validation to ensure they are actionable and executable."""

import re
from typing import Dict, List, Any, Tuple


class TicketValidator:
    """Validates tickets to ensure they meet production standards."""
    
    def validate_ticket(self, ticket: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate a single ticket for actionability.
        
        Args:
            ticket: Ticket dictionary to validate
            
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []
        
        # Check required fields
        if not ticket.get('id'):
            issues.append("Missing ticket ID")
        if not ticket.get('title'):
            issues.append("Missing ticket title")
        if not ticket.get('acceptance_criteria'):
            issues.append("Missing acceptance criteria")
            
        # Validate acceptance criteria are actionable
        criteria = ticket.get('acceptance_criteria', [])
        if not criteria:
            issues.append("No acceptance criteria defined")
        else:
            file_creation_found = False
            for i, criterion in enumerate(criteria):
                if not isinstance(criterion, str):
                    issues.append(f"Criterion {i+1} is not a string")
                    continue
                    
                # Check if criterion mentions file creation
                if re.match(r'^Create\s+\S+\.\S+', criterion, re.IGNORECASE):
                    file_creation_found = True
                    
            if not file_creation_found and self._requires_file_creation(ticket):
                issues.append("No explicit file creation criteria (should start with 'Create [filename]')")
                
        # Check model is valid
        model = ticket.get('model', 'balanced')
        if model not in ['fast', 'balanced', 'smart']:
            issues.append(f"Invalid model: {model} (must be fast/balanced/smart)")
            
        return len(issues) == 0, issues
    
    def _requires_file_creation(self, ticket: Dict[str, Any]) -> bool:
        """Check if this ticket type requires file creation.
        
        Args:
            ticket: Ticket to check
            
        Returns:
            True if ticket should create files
        """
        # Most implementation tickets require file creation
        title = ticket.get('title', '').lower()
        description = ticket.get('description', '').lower()
        
        # Keywords that indicate file creation is needed
        creation_keywords = [
            'create', 'build', 'implement', 'develop',
            'add', 'write', 'generate', 'design'
        ]
        
        # Keywords that indicate no file creation needed
        no_creation_keywords = [
            'refactor', 'fix', 'update', 'modify',
            'review', 'test', 'document existing', 'analyze'
        ]
        
        # Check if this is a creation task
        for keyword in creation_keywords:
            if keyword in title or keyword in description:
                # Make sure it's not a non-creation task
                for no_keyword in no_creation_keywords:
                    if no_keyword in title:
                        return False
                return True
                
        return False
    
    def transform_criteria_to_actionable(self, criteria: List[str], 
                                        project_type: str = None) -> List[str]:
        """Transform vague criteria into actionable ones.
        
        Args:
            criteria: List of acceptance criteria
            project_type: Type of project (web, api, cli, etc.)
            
        Returns:
            List of transformed, actionable criteria
        """
        actionable = []
        
        for criterion in criteria:
            transformed = self._transform_single_criterion(criterion, project_type)
            actionable.append(transformed)
            
        return actionable
    
    def _transform_single_criterion(self, criterion: str, project_type: str = None) -> str:
        """Transform a single criterion to be actionable.
        
        Args:
            criterion: Single acceptance criterion
            project_type: Type of project
            
        Returns:
            Transformed criterion
        """
        criterion_lower = criterion.lower()
        
        # Web calculator specific transformations
        if 'calculator' in criterion_lower or project_type == 'calculator':
            if 'display' in criterion_lower and ('page' in criterion_lower or 'web' in criterion_lower):
                return "Create index.html with calculator display div and button grid layout"
            elif ('button' in criterion_lower and 'number' in criterion_lower) or \
                 ('has number' in criterion_lower):
                return "Create index.html with buttons for digits 0-9 and operators (+,-,*,/,=,C)"
            elif 'operator' in criterion_lower and 'button' not in criterion_lower:
                return "Create styles.css with button styling for operators"
            elif 'style' in criterion_lower or 'css' in criterion_lower:
                return "Create styles.css with calculator grid layout, button styling, and display styling"
            elif 'logic' in criterion_lower or 'javascript' in criterion_lower:
                return "Create script.js with calculate(), clear(), and appendNumber() functions"
            elif 'calculation' in criterion_lower or 'performs calc' in criterion_lower:
                return "Create script.js with arithmetic operation functions"
            elif 'clear' in criterion_lower and 'button' in criterion_lower:
                return "Implement clear() function in script.js to reset calculator"
                
        # Generic web app transformations
        if project_type == 'web' or 'web' in criterion_lower:
            if 'html' in criterion_lower or 'page' in criterion_lower:
                if not criterion_lower.startswith('create '):
                    return f"Create index.html with {criterion[20:] if len(criterion) > 20 else 'required elements'}"
            elif 'style' in criterion_lower or 'css' in criterion_lower:
                if not criterion_lower.startswith('create '):
                    return f"Create styles.css with {criterion[15:] if len(criterion) > 15 else 'required styling'}"
            elif 'javascript' in criterion_lower or 'script' in criterion_lower:
                if not criterion_lower.startswith('create '):
                    return f"Create script.js with {criterion[15:] if len(criterion) > 15 else 'required functionality'}"
                    
        # If already starts with "Create", keep as-is
        if criterion_lower.startswith('create '):
            return criterion
            
        # For other criteria that don't need file creation, keep as-is
        action_verbs = ['test', 'verify', 'ensure', 'validate', 'check']
        for verb in action_verbs:
            if criterion_lower.startswith(verb):
                return criterion
                
        # If we can't transform it, at least make it start with an action verb
        if not any(criterion_lower.startswith(v) for v in ['create', 'implement', 'add', 'test', 'verify']):
            return f"Implement {criterion}"
            
        return criterion