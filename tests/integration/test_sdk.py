from hydra.agents.base import CodeAgent


def test_code_generation():
    agent = CodeAgent("test_agent")
    result = agent.generate_code("Generate a Hello World function in Python")
    assert result is not None
    assert "def" in result or "print" in result
