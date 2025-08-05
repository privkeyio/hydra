def venice_call(prompt):
    try:
        import venice
        client = venice.Client()
        return client.generate(prompt)
    except ImportError:
        raise ImportError("Venice client not available")