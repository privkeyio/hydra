import os
from openai import OpenAI


def venice_call(prompt):
    """
    Make a call to Venice API using OpenAI-compatible interface.
    Venice API is compatible with OpenAI's client library.
    """
    api_key = os.getenv("VENICE_API_KEY")
    if not api_key:
        raise ValueError("VENICE_API_KEY not found in environment variables")
    
    # Venice API endpoint
    base_url = "https://api.venice.ai/api/v1"
    
    # Create OpenAI client pointing to Venice
    client = OpenAI(
        api_key=api_key,
        base_url=base_url
    )
    
    try:
        # Use a coding-optimized model
        response = client.chat.completions.create(
            model="qwen-2.5-coder-32b",  # Venice's coding-optimized model
            messages=[
                {"role": "system", "content": "You are an expert Python programmer. Always respond with clean, well-structured code."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2048,
            temperature=0.2  # Lower temperature for more consistent code generation
        )
        
        return response.choices[0].message.content
    except Exception as e:
        raise Exception(f"Venice API error: {str(e)}")