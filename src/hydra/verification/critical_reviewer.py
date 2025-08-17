"""Critical code reviewer for production quality assessment."""

import os
import re
import ast
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import subprocess


class CriticalCodeReviewer:
    """Performs critical analysis of code quality and completeness."""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.issues = []
        self.warnings = []
        self.metrics = {}
        
    def review_ticket_implementation(self, ticket_id: str, ticket: Dict) -> Dict[str, Any]:
        """Perform comprehensive review of ticket implementation."""
        review = {
            'ticket_id': ticket_id,
            'title': ticket.get('title', ''),
            'critical_issues': [],
            'warnings': [],
            'ai_patterns': [],
            'production_readiness': 'FAIL',
            'metrics': {},
            'recommendations': [],
            'value_assessment': 'NO_VALUE'
        }
        
        # 1. Check if ANY real implementation exists
        impl_check = self._check_real_implementation(ticket)
        if not impl_check['has_implementation']:
            review['critical_issues'].append({
                'severity': 'CRITICAL',
                'issue': 'No actual implementation found',
                'details': impl_check['details']
            })
            return review
            
        # 2. Analyze code quality
        quality_issues = self._analyze_code_quality(ticket)
        review['critical_issues'].extend(quality_issues['critical'])
        review['warnings'].extend(quality_issues['warnings'])
        
        # 3. Check for AI-generated patterns
        ai_patterns = self._detect_ai_code_patterns()
        review['ai_patterns'] = ai_patterns
        
        # 4. Assess production readiness
        prod_ready = self._assess_production_readiness()
        review['production_readiness'] = prod_ready['status']
        review['critical_issues'].extend(prod_ready['issues'])
        
        # 5. Calculate metrics
        review['metrics'] = self._calculate_metrics()
        
        # 6. Assess value added
        review['value_assessment'] = self._assess_value_added(ticket)
        
        # 7. Generate recommendations
        review['recommendations'] = self._generate_recommendations(review)
        
        return review
        
    def _check_real_implementation(self, ticket: Dict) -> Dict[str, Any]:
        """Check if there's actual implementation vs just empty files/folders."""
        result = {
            'has_implementation': False,
            'details': []
        }
        
        # Count actual code files with substance
        code_files = 0
        empty_files = 0
        total_loc = 0
        
        for ext in ['*.js', '*.py', '*.ts', '*.jsx', '*.tsx']:
            for file_path in self.project_root.rglob(ext):
                # Skip node_modules, venv, etc
                if any(skip in str(file_path) for skip in ['node_modules', 'venv', '.git', '__pycache__']):
                    continue
                    
                try:
                    content = file_path.read_text()
                    lines = [l.strip() for l in content.split('\n') if l.strip() and not l.strip().startswith(('#', '//'))]
                    
                    if len(lines) > 5:  # More than 5 actual code lines
                        code_files += 1
                        total_loc += len(lines)
                    else:
                        empty_files += 1
                except:
                    continue
                    
        if code_files < 3:
            result['details'].append(f"Only {code_files} files with actual code")
        if empty_files > code_files:
            result['details'].append(f"{empty_files} empty/stub files vs {code_files} with code")
        if total_loc < 50:
            result['details'].append(f"Only {total_loc} lines of actual code")
            
        result['has_implementation'] = code_files >= 3 and total_loc >= 50
        return result
        
    def _analyze_code_quality(self, ticket: Dict) -> Dict[str, List]:
        """Analyze code quality issues."""
        issues = {
            'critical': [],
            'warnings': []
        }
        
        # Check for common bad patterns
        bad_patterns = [
            (r'console\.log\(', 'Debug console.log left in code'),
            (r'TODO|FIXME|XXX', 'Unfinished TODO/FIXME markers'),
            (r'pass\s*$', 'Empty function implementations'),
            (r'return\s+None\s*$', 'Explicit return None (code smell)'),
            (r'except\s*:\s*$', 'Bare except clause'),
            (r'import\s+\*', 'Wildcard imports'),
            (r'eval\(|exec\(', 'Dangerous eval/exec usage'),
            (r'password\s*=\s*["\']', 'Hardcoded password'),
            (r'api_key\s*=\s*["\']', 'Hardcoded API key'),
        ]
        
        for pattern, description in bad_patterns:
            for file_path in self.project_root.rglob('*'):
                if file_path.suffix in ['.js', '.py', '.ts']:
                    try:
                        content = file_path.read_text()
                        if re.search(pattern, content, re.MULTILINE):
                            issues['critical' if 'password' in description or 'api_key' in description else 'warnings'].append({
                                'file': str(file_path.relative_to(self.project_root)),
                                'issue': description
                            })
                    except:
                        continue
                        
        return issues
        
    def _detect_ai_code_patterns(self) -> List[Dict]:
        """Detect patterns typical of AI-generated code."""
        ai_patterns = []
        
        # Patterns that strongly suggest AI generation
        ai_indicators = [
            # Overly verbose/formulaic comments
            (r'# This function (?:handles|processes|manages|performs)', 'Formulaic function comment'),
            (r'"""[\s\S]{0,50}(?:Brief|Short|Simple) (?:description|summary)', 'Template docstring'),
            (r'# Step \d+:', 'Numbered step comments'),
            
            # Placeholder implementations
            (r'# TODO: Implement', 'Unimplemented TODO'),
            (r'raise NotImplementedError', 'NotImplementedError placeholder'),
            (r'pass\s+# Placeholder', 'Placeholder pass statement'),
            
            # Over-explanation
            (r'# Note: This is a simplified', 'Simplified implementation disclaimer'),
            (r'# For demonstration purposes', 'Demo code disclaimer'),
            (r'# In a real application', 'Real application disclaimer'),
            
            # Generic variable names in patterns
            (r'(?:item|elem|obj|val|temp|data|result)\d+', 'Numbered generic variables'),
            (r'my_(?:function|class|variable)', 'Generic my_ prefix'),
            
            # Excessive defensive programming
            (r'if .+ is not None and .+ is not None and', 'Excessive None checks'),
            (r'try:[\s\S]{1,50}except:[\s\S]{1,20}pass', 'Try-except-pass pattern'),
        ]
        
        files_analyzed = 0
        total_ai_score = 0
        
        for file_path in self.project_root.rglob('*'):
            if file_path.suffix in ['.js', '.py', '.ts']:
                try:
                    content = file_path.read_text()
                    file_ai_score = 0
                    file_patterns = []
                    
                    for pattern, description in ai_indicators:
                        matches = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
                        if matches:
                            file_ai_score += len(matches)
                            file_patterns.append({
                                'pattern': description,
                                'count': len(matches)
                            })
                    
                    if file_ai_score > 3:  # Multiple AI patterns in one file
                        ai_patterns.append({
                            'file': str(file_path.relative_to(self.project_root)),
                            'ai_score': file_ai_score,
                            'patterns': file_patterns
                        })
                        
                    files_analyzed += 1
                    total_ai_score += file_ai_score
                except:
                    continue
                    
        # Add overall assessment
        if files_analyzed > 0:
            avg_score = total_ai_score / files_analyzed
            if avg_score > 2:
                ai_patterns.insert(0, {
                    'overall': f'High AI pattern density: {avg_score:.1f} patterns per file',
                    'confidence': 'HIGH' if avg_score > 4 else 'MEDIUM'
                })
                
        return ai_patterns
        
    def _assess_production_readiness(self) -> Dict[str, Any]:
        """Assess if code is production ready."""
        assessment = {
            'status': 'NOT_READY',
            'issues': []
        }
        
        # Check for critical production requirements
        checks = {
            'error_handling': self._check_error_handling(),
            'logging': self._check_logging(),
            'tests': self._check_tests(),
            'security': self._check_security(),
            'documentation': self._check_documentation(),
            'configuration': self._check_configuration()
        }
        
        critical_failures = []
        for check_name, check_result in checks.items():
            if not check_result['passed']:
                critical_failures.append(check_name)
                assessment['issues'].append({
                    'category': check_name,
                    'severity': 'CRITICAL' if check_result.get('critical') else 'HIGH',
                    'details': check_result.get('details', f'{check_name} check failed')
                })
                
        # Determine overall status
        if len(critical_failures) == 0:
            assessment['status'] = 'PRODUCTION_READY'
        elif len(critical_failures) <= 2:
            assessment['status'] = 'NEEDS_WORK'
        else:
            assessment['status'] = 'NOT_READY'
            
        return assessment
        
    def _check_error_handling(self) -> Dict[str, Any]:
        """Check if proper error handling exists."""
        result = {'passed': False, 'critical': True}
        
        try_blocks = 0
        bare_excepts = 0
        
        for file_path in self.project_root.rglob('*.py'):
            try:
                content = file_path.read_text()
                try_blocks += len(re.findall(r'try:', content))
                bare_excepts += len(re.findall(r'except\s*:', content))
            except:
                continue
                
        if try_blocks > 0:
            if bare_excepts / try_blocks < 0.2:  # Less than 20% bare excepts
                result['passed'] = True
            else:
                result['details'] = f'{bare_excepts} bare except clauses out of {try_blocks} try blocks'
        else:
            result['details'] = 'No error handling found'
            
        return result
        
    def _check_logging(self) -> Dict[str, Any]:
        """Check if proper logging is implemented."""
        result = {'passed': False, 'critical': False}
        
        logging_found = False
        console_logs = 0
        
        for file_path in self.project_root.rglob('*'):
            if file_path.suffix in ['.js', '.py', '.ts']:
                try:
                    content = file_path.read_text()
                    if 'logging' in content or 'logger' in content or 'winston' in content or 'morgan' in content:
                        logging_found = True
                    console_logs += len(re.findall(r'console\.log', content))
                except:
                    continue
                    
        result['passed'] = logging_found and console_logs < 5
        if not result['passed']:
            result['details'] = f'{"No logging framework found. " if not logging_found else ""}{console_logs} console.log statements found' if console_logs > 0 else ''
            
        return result
        
    def _check_tests(self) -> Dict[str, Any]:
        """Check if tests exist and are meaningful."""
        result = {'passed': False, 'critical': True}
        
        test_files = list(self.project_root.rglob('test_*.py')) + \
                    list(self.project_root.rglob('*.test.js')) + \
                    list(self.project_root.rglob('*.spec.js'))
                    
        if len(test_files) > 0:
            # Check if tests have actual assertions
            real_tests = 0
            for test_file in test_files:
                try:
                    content = test_file.read_text()
                    if 'assert' in content or 'expect(' in content or 'should' in content:
                        real_tests += 1
                except:
                    continue
                    
            result['passed'] = real_tests > 0
            if not result['passed']:
                result['details'] = f'Test files exist but contain no assertions'
        else:
            result['details'] = 'No test files found'
            
        return result
        
    def _check_security(self) -> Dict[str, Any]:
        """Check for security issues."""
        result = {'passed': True, 'critical': True}
        
        security_issues = []
        
        for file_path in self.project_root.rglob('*'):
            if file_path.suffix in ['.js', '.py', '.ts', '.env']:
                try:
                    content = file_path.read_text()
                    
                    # Check for hardcoded secrets
                    if re.search(r'(password|api_key|secret|token)\s*=\s*["\'][^"\']+["\']', content, re.IGNORECASE):
                        security_issues.append(f'Hardcoded secret in {file_path.name}')
                        
                    # Check for SQL injection vulnerabilities
                    if re.search(r'(query|execute)\([^)]*\+[^)]*\)', content):
                        security_issues.append(f'Possible SQL injection in {file_path.name}')
                        
                except:
                    continue
                    
        if security_issues:
            result['passed'] = False
            result['details'] = '; '.join(security_issues[:3])  # First 3 issues
            
        return result
        
    def _check_documentation(self) -> Dict[str, Any]:
        """Check if code is documented."""
        result = {'passed': False, 'critical': False}
        
        readme_exists = (self.project_root / 'README.md').exists()
        docstrings = 0
        functions = 0
        
        for file_path in self.project_root.rglob('*.py'):
            try:
                content = file_path.read_text()
                functions += len(re.findall(r'def \w+\(', content))
                docstrings += len(re.findall(r'def \w+\([^)]*\):\s*"""', content, re.MULTILINE))
            except:
                continue
                
        if readme_exists and functions > 0:
            doc_ratio = docstrings / functions if functions > 0 else 0
            result['passed'] = doc_ratio > 0.3  # At least 30% documented
            if not result['passed']:
                result['details'] = f'Only {int(doc_ratio * 100)}% of functions documented'
        else:
            result['details'] = 'No README or no functions to document'
            
        return result
        
    def _check_configuration(self) -> Dict[str, Any]:
        """Check if configuration is properly handled."""
        result = {'passed': False, 'critical': False}
        
        config_files = ['.env.example', 'config.js', 'config.py', 'settings.py', 'config.json']
        has_config = any((self.project_root / cf).exists() for cf in config_files)
        
        # Check if environment variables are used
        uses_env = False
        for file_path in self.project_root.rglob('*'):
            if file_path.suffix in ['.js', '.py', '.ts']:
                try:
                    content = file_path.read_text()
                    if 'process.env' in content or 'os.environ' in content or 'dotenv' in content:
                        uses_env = True
                        break
                except:
                    continue
                    
        result['passed'] = has_config or uses_env
        if not result['passed']:
            result['details'] = 'No configuration management found'
            
        return result
        
    def _calculate_metrics(self) -> Dict[str, Any]:
        """Calculate code metrics."""
        metrics = {
            'total_files': 0,
            'total_loc': 0,
            'avg_file_size': 0,
            'complexity': 'UNKNOWN',
            'test_coverage': 'UNKNOWN'
        }
        
        total_lines = 0
        file_count = 0
        
        for file_path in self.project_root.rglob('*'):
            if file_path.suffix in ['.js', '.py', '.ts']:
                try:
                    content = file_path.read_text()
                    lines = content.split('\n')
                    total_lines += len(lines)
                    file_count += 1
                except:
                    continue
                    
        metrics['total_files'] = file_count
        metrics['total_loc'] = total_lines
        metrics['avg_file_size'] = total_lines / file_count if file_count > 0 else 0
        
        # Estimate complexity based on file size
        if metrics['avg_file_size'] > 500:
            metrics['complexity'] = 'HIGH'
        elif metrics['avg_file_size'] > 200:
            metrics['complexity'] = 'MEDIUM'
        else:
            metrics['complexity'] = 'LOW'
            
        return metrics
        
    def _assess_value_added(self, ticket: Dict) -> str:
        """Assess if any real value was added."""
        # Check various indicators of value
        indicators = {
            'has_business_logic': self._has_business_logic(),
            'has_data_models': self._has_data_models(),
            'has_api_endpoints': self._has_api_endpoints(),
            'has_ui_components': self._has_ui_components(),
            'has_tests': self._has_meaningful_tests()
        }
        
        value_count = sum(1 for v in indicators.values() if v)
        
        if value_count >= 4:
            return 'HIGH_VALUE'
        elif value_count >= 2:
            return 'SOME_VALUE'
        elif value_count >= 1:
            return 'MINIMAL_VALUE'
        else:
            return 'NO_VALUE'
            
    def _has_business_logic(self) -> bool:
        """Check if there's actual business logic."""
        for file_path in self.project_root.rglob('*'):
            if file_path.suffix in ['.js', '.py', '.ts']:
                try:
                    content = file_path.read_text()
                    # Look for conditionals, loops, calculations
                    if re.search(r'if .+:|for .+ in |while .+:|switch\s*\(|\.map\(|\.filter\(|\.reduce\(', content):
                        return True
                except:
                    continue
        return False
        
    def _has_data_models(self) -> bool:
        """Check for data models."""
        model_indicators = ['class.*Model', 'Schema', 'mongoose', 'sequelize', 'sqlalchemy']
        for file_path in self.project_root.rglob('*'):
            if file_path.suffix in ['.js', '.py', '.ts']:
                try:
                    content = file_path.read_text()
                    for indicator in model_indicators:
                        if re.search(indicator, content, re.IGNORECASE):
                            return True
                except:
                    continue
        return False
        
    def _has_api_endpoints(self) -> bool:
        """Check for API endpoints."""
        endpoint_indicators = ['@app.route', '@router', 'router.get', 'router.post', 'app.get', 'app.post']
        for file_path in self.project_root.rglob('*'):
            if file_path.suffix in ['.js', '.py', '.ts']:
                try:
                    content = file_path.read_text()
                    for indicator in endpoint_indicators:
                        if indicator in content:
                            return True
                except:
                    continue
        return False
        
    def _has_ui_components(self) -> bool:
        """Check for UI components."""
        ui_indicators = ['<div', '<button', 'Component', 'render', 'return (', 'className=', 'getElementById']
        for file_path in self.project_root.rglob('*'):
            if file_path.suffix in ['.js', '.jsx', '.tsx', '.html']:
                try:
                    content = file_path.read_text()
                    for indicator in ui_indicators:
                        if indicator in content:
                            return True
                except:
                    continue
        return False
        
    def _has_meaningful_tests(self) -> bool:
        """Check if tests are meaningful."""
        test_files = list(self.project_root.rglob('test_*.py')) + \
                    list(self.project_root.rglob('*.test.js')) + \
                    list(self.project_root.rglob('*.spec.js'))
                    
        for test_file in test_files:
            try:
                content = test_file.read_text()
                # Check for actual test assertions
                if re.search(r'assert|expect\(|should\.|toBe\(|toEqual\(', content):
                    return True
            except:
                continue
        return False
        
    def _generate_recommendations(self, review: Dict) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []
        
        # Based on critical issues
        if len(review['critical_issues']) > 3:
            recommendations.append("REJECT: Too many critical issues. This needs complete reimplementation.")
        
        # Based on AI patterns
        if review['ai_patterns'] and len(review['ai_patterns']) > 2:
            recommendations.append("REWRITE: High AI pattern density suggests generated code. Needs human implementation.")
            
        # Based on production readiness
        if review['production_readiness'] == 'NOT_READY':
            recommendations.append("NOT DEPLOYABLE: Missing critical production requirements.")
            
        # Based on value assessment
        if review['value_assessment'] in ['NO_VALUE', 'MINIMAL_VALUE']:
            recommendations.append("NO VALUE: Implementation adds no real functionality.")
            
        # Specific improvements
        if not self._has_meaningful_tests():
            recommendations.append("Add comprehensive test coverage with real assertions.")
            
        if review['metrics'].get('avg_file_size', 0) < 50:
            recommendations.append("Files are too small - likely stubs. Add real implementation.")
            
        # Overall verdict
        if not recommendations:
            recommendations.append("ACCEPTABLE: Meets minimum standards but could be improved.")
            
        return recommendations