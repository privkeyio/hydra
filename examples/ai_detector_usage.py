#!/usr/bin/env python3
"""Example usage of the AI pattern detector."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hydra.verification_system import (
    AIDetector,
    AIPatternConfig,
    SensitivityLevel,
    create_detector,
    VerificationEngine
)


def example_basic_detection():
    """Basic example of detecting AI patterns in a single file."""
    print("=" * 60)
    print("Example 1: Basic AI Pattern Detection")
    print("=" * 60)
    
    # Create detector with default configuration
    detector = AIDetector()
    
    # Create a sample file with AI-like patterns
    sample_code = '''
# Initialize the system
# TODO: Replace with actual implementation
def process_user_input_data():
    """Comprehensive data processing utility for handling various inputs."""
    try:
        # Process the data
        pass  # Placeholder
    except Exception:
        pass
    print("🎉 Done!")
'''
    
    # Write to temporary file
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(sample_code)
        temp_file = Path(f.name)
    
    # Detect patterns
    result = detector.detect_file(temp_file)
    
    print(f"\nFile: {temp_file.name}")
    print(f"AI Score: {result.ai_score:.2f}")
    print(f"Passes: {result.passes}")
    print(f"\nDetected patterns ({len(result.detected_patterns)}):")
    
    for pattern in result.detected_patterns:
        print(f"  - {pattern['category']}: Line {pattern.get('line', '?')}")
        print(f"    Match: {pattern['match'][:50]}...")
        print(f"    Severity: {pattern['severity']}")
    
    # Clean up
    temp_file.unlink()
    print()


def example_sensitivity_levels():
    """Example showing different sensitivity levels."""
    print("=" * 60)
    print("Example 2: Sensitivity Levels")
    print("=" * 60)
    
    sample_code = '''
def calculate_sum(numbers):
    # Calculate the sum
    total = 0
    for num in numbers:
        total += num
    return total
'''
    
    from tempfile import NamedTemporaryFile
    
    for sensitivity in [SensitivityLevel.LOW, SensitivityLevel.MEDIUM, 
                       SensitivityLevel.HIGH, SensitivityLevel.PARANOID]:
        
        config = AIPatternConfig(sensitivity=sensitivity)
        detector = AIDetector(config)
        
        with NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(sample_code)
            temp_file = Path(f.name)
        
        result = detector.detect_file(temp_file)
        
        print(f"\n{sensitivity.value.upper()} sensitivity:")
        print(f"  AI Score: {result.ai_score:.2f}")
        print(f"  Passes: {result.passes}")
        print(f"  Patterns found: {len(result.detected_patterns)}")
        
        temp_file.unlink()
    
    print()


def example_whitelist():
    """Example of using whitelist to exclude certain patterns."""
    print("=" * 60)
    print("Example 3: Whitelist Configuration")
    print("=" * 60)
    
    sample_code = '''
# TODO: Security review needed
# TODO: This needs fixing
def secure_function():
    """Process sensitive data."""
    # SECURITY_CRITICAL: Do not modify
    return encrypt_data()
'''
    
    # Without whitelist
    detector1 = AIDetector()
    
    # With whitelist
    config = AIPatternConfig(
        whitelist_patterns={"TODO: Security review needed", "SECURITY_CRITICAL"}
    )
    detector2 = AIDetector(config)
    
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(sample_code)
        temp_file = Path(f.name)
    
    result1 = detector1.detect_file(temp_file)
    result2 = detector2.detect_file(temp_file)
    
    print("\nWithout whitelist:")
    print(f"  Patterns found: {len(result1.detected_patterns)}")
    for p in result1.detected_patterns:
        print(f"    - {p['category']}: {p['match'][:30]}...")
    
    print("\nWith whitelist:")
    print(f"  Patterns found: {len(result2.detected_patterns)}")
    for p in result2.detected_patterns:
        print(f"    - {p['category']}: {p['match'][:30]}...")
    
    temp_file.unlink()
    print()


def example_directory_scan():
    """Example of scanning an entire directory."""
    print("=" * 60)
    print("Example 4: Directory Scanning")
    print("=" * 60)
    
    # Create temporary directory with sample files
    from tempfile import TemporaryDirectory
    
    with TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Create sample files
        files = {
            "clean.py": '''
def add(a, b):
    return a + b

def multiply(a, b):
    return a * b
''',
            "ai_like.py": '''
# Initialize the system
# TODO: Implement this properly
def process_data_handler():
    """Comprehensive and robust data processing."""
    try:
        # Process the data
        pass
    except Exception:
        pass
''',
            "emoji.py": '''
def celebrate():
    print("🎉 Success! 🚀")
    return "✅ Done"
'''
        }
        
        for filename, content in files.items():
            (tmpdir_path / filename).write_text(content)
        
        # Scan directory
        detector = AIDetector()
        results = detector.detect_directory(tmpdir_path)
        
        print(f"\nScanned {len(results)} files:")
        
        for result in results:
            status = "✓ PASS" if result.passes else "✗ FAIL"
            print(f"\n  {status} {Path(result.file_path).name}")
            print(f"    AI Score: {result.ai_score:.2f}")
            print(f"    Patterns: {len(result.detected_patterns)}")
        
        # Generate report
        report = detector.generate_report(results)
        
        print("\nOverall Report:")
        print(f"  Total files: {report['summary']['total_files']}")
        print(f"  Passed: {report['summary']['passed']}")
        print(f"  Failed: {report['summary']['failed']}")
        print(f"  Average AI Score: {report['summary']['average_ai_score']:.2f}")
        
        print("\nRecommendations:")
        for rec in report['recommendations']:
            print(f"  - {rec}")
    
    print()


def example_integration_with_verification():
    """Example of integration with verification engine."""
    print("=" * 60)
    print("Example 5: Integration with Verification Engine")
    print("=" * 60)
    
    from tempfile import TemporaryDirectory
    
    with TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Create a sample project structure
        src_dir = tmpdir_path / "src"
        src_dir.mkdir()
        
        # Create sample file with AI patterns
        (src_dir / "main.py").write_text('''
# TODO: Replace with actual implementation
def main():
    """Main entry point for the application."""
    print("🎉 Hello World!")
    # Process data
    pass
''')
        
        # Create verification engine with AI detection
        ai_config = AIPatternConfig(
            sensitivity=SensitivityLevel.HIGH,
            emoji_allowed=False
        )
        
        engine = VerificationEngine(str(tmpdir_path), ai_config)
        
        # Run AI detection
        ai_result = engine.run_ai_detection("src")
        
        print("\nAI Detection Results:")
        report = ai_result["ai_detection_report"]
        print(f"  Files checked: {report['summary']['total_files']}")
        print(f"  Failed: {report['summary']['failed']}")
        print(f"  Average AI score: {report['summary']['average_ai_score']:.2f}")
        
        # Check single file
        passes, summary = engine.run_ai_detection_on_file("src/main.py")
        print(f"\nSingle file check:")
        print(f"  {summary}")
    
    print()


def example_custom_patterns():
    """Example of adding custom patterns."""
    print("=" * 60)
    print("Example 6: Custom Pattern Detection")
    print("=" * 60)
    
    # Configure custom patterns
    config = AIPatternConfig(
        custom_patterns=[
            {
                "category": "company_specific",
                "pattern": r"ACME_INTERNAL",
                "severity": "high"
            },
            {
                "category": "deprecated_api",
                "pattern": r"old_api_call\(",
                "severity": "medium"
            }
        ]
    )
    
    detector = AIDetector(config)
    
    sample_code = '''
# ACME_INTERNAL: Do not distribute
def process():
    result = old_api_call()  # Should be updated
    return result
'''
    
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(sample_code)
        temp_file = Path(f.name)
    
    result = detector.detect_file(temp_file)
    
    print(f"\nCustom patterns detected: {len(result.detected_patterns)}")
    for pattern in result.detected_patterns:
        print(f"  - {pattern['category']}: {pattern['match']}")
        print(f"    Severity: {pattern['severity']}")
    
    temp_file.unlink()
    print()


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("AI PATTERN DETECTOR - USAGE EXAMPLES")
    print("=" * 60 + "\n")
    
    example_basic_detection()
    example_sensitivity_levels()
    example_whitelist()
    example_directory_scan()
    example_integration_with_verification()
    example_custom_patterns()
    
    print("=" * 60)
    print("All examples completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()