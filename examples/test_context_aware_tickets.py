#!/usr/bin/env python3
"""Test script to verify context-aware ticket generation."""

import os
import sys
import tempfile
from pathlib import Path

# Add hydra to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hydra.ticket_workflow import generate_tickets_md


def test_context_aware_ticket_generation():
    """Test that ticket generation includes context-aware features."""
    
    # Create a test project description that should result in dependent tickets
    project_description = """
    Create a REST API system with the following components:
    1. First, audit and document the existing codebase
    2. Design the API architecture based on the audit findings
    3. Implement the API endpoints using the design
    4. Add authentication using the API structure
    5. Create tests for all endpoints
    """
    
    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        output_path = "tickets.md"
        
        print("🧪 Testing context-aware ticket generation...")
        print(f"📁 Working directory: {tmpdir}")
        print("-" * 60)
        
        # Generate tickets
        result = generate_tickets_md(project_description, output_path)
        
        if result and Path(output_path).exists():
            # Read and analyze the generated tickets
            with open(output_path, 'r') as f:
                content = f.read()
            
            print("✅ Tickets generated successfully!")
            print("\n📋 Checking for context-aware features...")
            
            # Check for required features
            features_found = {
                "Dependencies": "Dependencies:" in content,
                "Required Input Files": "Required Input Files:" in content,
                "Context Requirements": "Context Requirements:" in content,
                "Builds on references": "builds on" in content.lower() or "based on" in content.lower(),
                "File references": "from Ticket" in content,
            }
            
            print("\nFeature check results:")
            for feature, found in features_found.items():
                status = "✅" if found else "❌"
                print(f"  {status} {feature}: {'Found' if found else 'Not found'}")
            
            # Show a sample of the generated content
            print("\n📄 Sample of generated tickets (first 1000 chars):")
            print("-" * 60)
            print(content[:1000])
            print("-" * 60)
            
            # Check if all critical features are present
            if all([
                features_found["Dependencies"],
                features_found["Builds on references"]
            ]):
                print("\n🎉 SUCCESS: Tickets include context-aware features!")
                
                # If Required Input Files or Context Requirements are found, that's even better
                if features_found["Required Input Files"] or features_found["Context Requirements"]:
                    print("🌟 EXCELLENT: Advanced context features detected!")
                return True
            else:
                print("\n⚠️  WARNING: Some context features may be missing")
                print("This could be because:")
                print("  1. The generated tickets don't have dependencies")
                print("  2. The prompt needs adjustment")
                return False
        else:
            print("❌ Failed to generate tickets")
            return False


if __name__ == "__main__":
    try:
        success = test_context_aware_ticket_generation()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)