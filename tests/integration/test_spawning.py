#!/usr/bin/env python3

from hydra.agents.base import CodeAgent
import json

def test_boss_spawning():
    boss = CodeAgent("boss", depth=0)
    
    subtask1 = "Calculate the sum of numbers 1 to 10"
    subtask2 = "Calculate the factorial of 5"
    
    print("Testing boss spawning 2 employees for parallel tasks...")
    
    result1 = boss.create_employee(subtask1)
    result2 = boss.create_employee(subtask2)
    
    print(f"Boss has {len(boss.employees)} employees")
    
    print(f"Employee 1 result: {result1['success']}")
    if result1['success']:
        print(f"Employee 1 output: {result1['result']}")
    else:
        print(f"Employee 1 error: {result1.get('error', 'Unknown error')}")
    
    print(f"Employee 2 result: {result2['success']}")
    if result2['success']:
        print(f"Employee 2 output: {result2['result']}")
    else:
        print(f"Employee 2 error: {result2.get('error', 'Unknown error')}")
    
    results = [result1, result2]
    aggregated = {
        "total_employees": len(boss.employees),
        "successful_tasks": sum(1 for r in results if r['success']),
        "results": [r['result'] if r['success'] else r.get('error') for r in results]
    }
    
    print(f"Aggregated results: {json.dumps(aggregated, indent=2)}")
    
    return aggregated

if __name__ == "__main__":
    test_boss_spawning()