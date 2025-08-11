# Provider Implementation Guide

## Overview

This guide explains how to implement custom LLM providers for Hydra. By following the provider abstraction interface, you can integrate any LLM service or model into the Hydra ecosystem.

## Architecture

The provider system follows a layered architecture:

```
┌─────────────────────────────────────┐
│         Hydra CLI/API Layer         │
├─────────────────────────────────────┤
│       Provider Factory Layer        │
├─────────────────────────────────────┤
│      Provider Registry Layer        │
├─────────────────────────────────────┤
│    BaseProvider Abstract Class      │
├─────────────────────────────────────┤
│   Concrete Provider Implementations │
│  (Claude, Venice, Custom, etc.)     │
└─────────────────────────────────────┘
```

## BaseProvider Interface

All providers must implement the `BaseProvider` abstract class:

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Iterator, Optional
from hydra.providers.base_provider import BaseProvider

class CustomProvider(BaseProvider):
    """Your custom provider implementation."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize provider with configuration."""
        super().__init__(config)
        self.api_key = config.get('api_key')
        self.base_url = config.get('base_url')
        self.model = config.get('default_model')
```

## Required Methods

### 1. Core Generation Methods

```python
def generate(self, prompt: str, **kwargs) -> str:
    """
    Generate text response from the LLM.
    
    Args:
        prompt: The input prompt
        **kwargs: Additional parameters (temperature, max_tokens, etc.)
        
    Returns:
        Generated text response
    """
    # Your implementation
    response = self._call_api(prompt, **kwargs)
    return response.text

def generate_code(self, prompt: str, context: Dict[str, Any], **kwargs) -> str:
    """
    Generate code with context awareness.
    
    Args:
        prompt: The code generation prompt
        context: Context information (files, dependencies, etc.)
        **kwargs: Additional parameters
        
    Returns:
        Generated code as string
    """
    enhanced_prompt = self._build_code_prompt(prompt, context)
    response = self.generate(enhanced_prompt, **kwargs)
    return self._extract_code(response)

def generate_streaming(self, prompt: str, **kwargs) -> Iterator[str]:
    """
    Generate streaming response for real-time output.
    
    Args:
        prompt: The input prompt
        **kwargs: Additional parameters
        
    Yields:
        Chunks of generated text
    """
    stream = self._call_api_streaming(prompt, **kwargs)
    for chunk in stream:
        yield chunk.text
```

### 2. Session Management

```python
def create_session(self, session_id: str, **kwargs) -> Session:
    """
    Create a new provider session.
    
    Args:
        session_id: Unique session identifier
        **kwargs: Session configuration
        
    Returns:
        Session object
    """
    session = Session(
        id=session_id,
        provider=self.name,
        model=self.model,
        created_at=datetime.now(),
        state=SessionState.ACTIVE
    )
    self._sessions[session_id] = session
    return session

def attach_session(self, session_id: str) -> Session:
    """
    Attach to existing session.
    
    Args:
        session_id: Session to attach to
        
    Returns:
        Session object
        
    Raises:
        SessionNotFoundError: If session doesn't exist
    """
    if session_id not in self._sessions:
        raise SessionNotFoundError(f"Session {session_id} not found")
    return self._sessions[session_id]

def list_sessions(self) -> List[Session]:
    """List all active sessions."""
    return list(self._sessions.values())

def kill_session(self, session_id: str) -> bool:
    """
    Terminate a session.
    
    Args:
        session_id: Session to terminate
        
    Returns:
        True if successful
    """
    if session_id in self._sessions:
        self._sessions[session_id].state = SessionState.TERMINATED
        del self._sessions[session_id]
        return True
    return False
```

### 3. Model Management

```python
def list_models(self) -> List[ModelInfo]:
    """
    List available models with metadata.
    
    Returns:
        List of available models
    """
    return [
        ModelInfo(
            identifier="model-1",
            display_name="Model 1",
            category="balanced",
            context_window=8192,
            max_output_tokens=4096,
            supports_streaming=True,
            supports_interactive=False,
            cost_per_token=0.001
        ),
        # Add more models...
    ]

def select_model(self, model_identifier: str) -> bool:
    """
    Select a specific model.
    
    Args:
        model_identifier: Model to select
        
    Returns:
        True if successful
    """
    available_models = [m.identifier for m in self.list_models()]
    if model_identifier in available_models:
        self.model = model_identifier
        return True
    return False

def get_model_mapping(self) -> Dict[str, str]:
    """
    Map generic model names to provider-specific identifiers.
    
    Returns:
        Mapping dictionary
    """
    return {
        "fast": "model-small",
        "balanced": "model-medium",
        "smart": "model-large"
    }
```

### 4. Output Handling

```python
def parse_response(self, response: str) -> ParsedResponse:
    """
    Parse provider-specific response format.
    
    Args:
        response: Raw response from provider
        
    Returns:
        Parsed response object
    """
    code_blocks = self.extract_code_blocks(response)
    return ParsedResponse(
        text=response,
        code_blocks=code_blocks,
        metadata={},
        tokens_used=self._count_tokens(response)
    )

def extract_code_blocks(self, response: str) -> List[CodeBlock]:
    """
    Extract code blocks from response.
    
    Args:
        response: Text containing code blocks
        
    Returns:
        List of extracted code blocks
    """
    import re
    blocks = []
    
    # Match code blocks with optional language
    pattern = r'```(\w+)?\n(.*?)```'
    matches = re.finditer(pattern, response, re.DOTALL)
    
    for match in matches:
        language = match.group(1) or 'text'
        content = match.group(2)
        blocks.append(CodeBlock(
            language=language,
            content=content,
            line_start=response[:match.start()].count('\n'),
            line_end=response[:match.end()].count('\n'),
            executable=language in ['python', 'bash', 'javascript']
        ))
    
    return blocks
```

### 5. Interactive Features

```python
def supports_interactive(self) -> bool:
    """Check if provider supports interactive mode."""
    return False  # Override if your provider supports this

def wait_for_prompt(self, timeout: int = 30) -> bool:
    """
    Wait for interactive prompt if supported.
    
    Args:
        timeout: Maximum wait time in seconds
        
    Returns:
        True if prompt is ready
    """
    if not self.supports_interactive():
        return False
    
    # Implementation for interactive providers
    start_time = time.time()
    while time.time() - start_time < timeout:
        if self._check_prompt_ready():
            return True
        time.sleep(0.1)
    return False
```

### 6. File Operations

```python
def intercept_file_operation(self, operation: FileOperation) -> bool:
    """
    Intercept and validate file operations.
    
    Args:
        operation: File operation to validate
        
    Returns:
        True if operation is allowed
    """
    # Implement safety checks
    if operation.type == "delete" and operation.path.startswith("/"):
        return False  # Don't allow root deletions
    
    if operation.type == "write":
        # Check file size limits, path restrictions, etc.
        if len(operation.content) > 10_000_000:  # 10MB limit
            return False
    
    return True
```

## Complete Example Implementation

Here's a complete example of a custom provider:

```python
import requests
from typing import Dict, Any, List, Iterator, Optional
from datetime import datetime
from hydra.providers.base_provider import (
    BaseProvider, Session, SessionState, ModelInfo,
    ParsedResponse, CodeBlock, FileOperation
)

class OpenAIProvider(BaseProvider):
    """OpenAI API provider implementation."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get('api_key')
        self.base_url = config.get('base_url', 'https://api.openai.com/v1')
        self.model = config.get('default_model', 'gpt-4')
        self.timeout = config.get('timeout', 300)
        self._sessions = {}
        
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text using OpenAI API."""
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': self.model,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': kwargs.get('temperature', 0.7),
            'max_tokens': kwargs.get('max_tokens', 4096)
        }
        
        response = requests.post(
            f'{self.base_url}/chat/completions',
            headers=headers,
            json=data,
            timeout=self.timeout
        )
        response.raise_for_status()
        
        result = response.json()
        return result['choices'][0]['message']['content']
    
    def generate_code(self, prompt: str, context: Dict[str, Any], **kwargs) -> str:
        """Generate code with context."""
        # Build enhanced prompt with context
        enhanced_prompt = f"""
        Generate code for the following request:
        {prompt}
        
        Context:
        - Language: {context.get('language', 'python')}
        - Dependencies: {context.get('dependencies', [])}
        - Style: {context.get('style', 'clean and documented')}
        
        Return only the code without explanation.
        """
        
        response = self.generate(enhanced_prompt, **kwargs)
        return self._extract_code(response)
    
    def generate_streaming(self, prompt: str, **kwargs) -> Iterator[str]:
        """Generate streaming response."""
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': self.model,
            'messages': [{'role': 'user', 'content': prompt}],
            'stream': True,
            'temperature': kwargs.get('temperature', 0.7)
        }
        
        response = requests.post(
            f'{self.base_url}/chat/completions',
            headers=headers,
            json=data,
            stream=True,
            timeout=self.timeout
        )
        response.raise_for_status()
        
        for line in response.iter_lines():
            if line:
                # Parse Server-Sent Events
                if line.startswith(b'data: '):
                    data = line[6:]
                    if data != b'[DONE]':
                        import json
                        chunk = json.loads(data)
                        if 'choices' in chunk:
                            delta = chunk['choices'][0].get('delta', {})
                            if 'content' in delta:
                                yield delta['content']
    
    def list_models(self) -> List[ModelInfo]:
        """List available OpenAI models."""
        return [
            ModelInfo(
                identifier="gpt-4",
                display_name="GPT-4",
                category="smart",
                context_window=8192,
                max_output_tokens=4096,
                supports_streaming=True,
                supports_interactive=False,
                cost_per_token=0.03
            ),
            ModelInfo(
                identifier="gpt-3.5-turbo",
                display_name="GPT-3.5 Turbo",
                category="fast",
                context_window=4096,
                max_output_tokens=4096,
                supports_streaming=True,
                supports_interactive=False,
                cost_per_token=0.002
            )
        ]
    
    def select_model(self, model_identifier: str) -> bool:
        """Select a model."""
        available = [m.identifier for m in self.list_models()]
        if model_identifier in available:
            self.model = model_identifier
            return True
        return False
    
    def get_model_mapping(self) -> Dict[str, str]:
        """Get model mappings."""
        return {
            "fast": "gpt-3.5-turbo",
            "smart": "gpt-4",
            "balanced": "gpt-3.5-turbo-16k"
        }
    
    # Implement remaining required methods...
    
    def _extract_code(self, text: str) -> str:
        """Extract code from response."""
        blocks = self.extract_code_blocks(text)
        if blocks:
            return blocks[0].content
        return text
```

## Registration and Discovery

### Registering Your Provider

```python
# In your provider module
from hydra.providers import ProviderRegistry
from .openai_provider import OpenAIProvider

# Register the provider
ProviderRegistry.register("openai", OpenAIProvider)
```

### Auto-Discovery

Place your provider in the `hydra/providers/` directory with proper naming:

```python
# hydra/providers/openai_provider.py
class OpenAIProvider(BaseProvider):
    # Implementation...

# Export for auto-discovery
__provider_class__ = OpenAIProvider
__provider_name__ = "openai"
```

## Testing Your Provider

### Unit Tests

```python
import pytest
from hydra.providers import ProviderFactory
from your_module import CustomProvider

class TestCustomProvider:
    @pytest.fixture
    def provider(self):
        config = {
            'api_key': 'test_key',
            'model': 'test_model'
        }
        return CustomProvider(config)
    
    def test_generate(self, provider):
        response = provider.generate("Test prompt")
        assert isinstance(response, str)
        assert len(response) > 0
    
    def test_model_selection(self, provider):
        success = provider.select_model("test_model")
        assert success is True
        
        success = provider.select_model("invalid_model")
        assert success is False
    
    def test_code_extraction(self, provider):
        text = "Here's code:\n```python\nprint('hello')\n```"
        blocks = provider.extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0].language == "python"
        assert blocks[0].content == "print('hello')\n"
```

### Integration Tests

```python
def test_provider_integration():
    # Test with real configuration
    from hydra.providers import ProviderFactory
    
    provider = ProviderFactory.from_environment()
    
    # Test generation
    response = provider.generate("Write a hello world function")
    assert "def" in response or "function" in response
    
    # Test streaming
    chunks = []
    for chunk in provider.generate_streaming("Count to 5"):
        chunks.append(chunk)
    assert len(chunks) > 0
    
    # Test session management
    session = provider.create_session("test_session")
    assert session.id == "test_session"
    
    sessions = provider.list_sessions()
    assert len(sessions) == 1
    
    success = provider.kill_session("test_session")
    assert success is True
```

## Error Handling

### Custom Exceptions

```python
class CustomProviderError(Exception):
    """Base exception for custom provider."""
    pass

class AuthenticationError(CustomProviderError):
    """Authentication failed."""
    pass

class ModelNotFoundError(CustomProviderError):
    """Requested model not found."""
    pass

class RateLimitError(CustomProviderError):
    """Rate limit exceeded."""
    pass
```

### Implementing Retry Logic

```python
from tenacity import retry, stop_after_attempt, wait_exponential

class RobustProvider(BaseProvider):
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def generate(self, prompt: str, **kwargs) -> str:
        try:
            return self._call_api(prompt, **kwargs)
        except requests.exceptions.Timeout:
            raise ProviderTimeoutError("Request timed out")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                raise RateLimitError("Rate limit exceeded")
            raise
```

## Performance Optimization

### Connection Pooling

```python
class PooledProvider(BaseProvider):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=3
        )
        self.session.mount('https://', adapter)
```

### Response Caching

```python
from functools import lru_cache
import hashlib

class CachedProvider(BaseProvider):
    @lru_cache(maxsize=100)
    def _cached_generate(self, prompt_hash: str, **kwargs) -> str:
        # Actual API call
        return self._call_api(prompt_hash, **kwargs)
    
    def generate(self, prompt: str, **kwargs) -> str:
        # Create cache key from prompt
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
        
        # Check if caching is enabled
        if kwargs.get('use_cache', True):
            return self._cached_generate(prompt_hash, **kwargs)
        else:
            return self._call_api(prompt, **kwargs)
```

### Async Support

```python
import asyncio
import aiohttp

class AsyncProvider(BaseProvider):
    async def generate_async(self, prompt: str, **kwargs) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f'{self.base_url}/generate',
                json={'prompt': prompt, **kwargs},
                headers={'Authorization': f'Bearer {self.api_key}'}
            ) as response:
                result = await response.json()
                return result['text']
    
    def generate(self, prompt: str, **kwargs) -> str:
        # Synchronous wrapper
        return asyncio.run(self.generate_async(prompt, **kwargs))
```

## Provider Features

### Supporting Interactive Mode

```python
class InteractiveProvider(BaseProvider):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._process = None
        self._interactive = False
    
    def supports_interactive(self) -> bool:
        return True
    
    def start_interactive(self) -> bool:
        """Start interactive session."""
        import subprocess
        self._process = subprocess.Popen(
            ['your-cli-tool'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        self._interactive = True
        return self.wait_for_prompt()
    
    def send_command(self, command: str) -> str:
        """Send command to interactive session."""
        if not self._interactive:
            raise RuntimeError("Not in interactive mode")
        
        self._process.stdin.write(command + '\n')
        self._process.stdin.flush()
        
        # Read response
        response = []
        while True:
            line = self._process.stdout.readline()
            if self._is_prompt(line):
                break
            response.append(line)
        
        return ''.join(response)
```

### Implementing File Safety

```python
class SafeProvider(BaseProvider):
    FORBIDDEN_PATHS = ['/etc', '/sys', '/proc']
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    
    def intercept_file_operation(self, operation: FileOperation) -> bool:
        # Check forbidden paths
        for forbidden in self.FORBIDDEN_PATHS:
            if operation.path.startswith(forbidden):
                self._log_security_event(operation, "Forbidden path")
                return False
        
        # Check file size for writes
        if operation.type == "write":
            if len(operation.content) > self.MAX_FILE_SIZE:
                self._log_security_event(operation, "File too large")
                return False
        
        # Check dangerous operations
        if operation.type == "delete":
            if self._is_system_file(operation.path):
                self._log_security_event(operation, "System file")
                return False
        
        return True
    
    def _is_system_file(self, path: str) -> bool:
        system_patterns = ['.bashrc', '.profile', '.ssh']
        return any(pattern in path for pattern in system_patterns)
    
    def _log_security_event(self, operation: FileOperation, reason: str):
        import logging
        logging.warning(f"Blocked {operation.type} on {operation.path}: {reason}")
```

## Best Practices

1. **Always validate configuration** in `__init__`
2. **Use proper error handling** with meaningful messages
3. **Implement timeouts** for all external calls
4. **Add logging** for debugging and monitoring
5. **Write comprehensive tests** for all methods
6. **Document provider-specific behavior**
7. **Support graceful degradation** when features aren't available
8. **Use connection pooling** for API-based providers
9. **Implement rate limiting** to avoid quota issues
10. **Cache responses** when appropriate

## Debugging

### Enable Debug Logging

```python
import logging

class DebugProvider(BaseProvider):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.logger = logging.getLogger(__name__)
        if config.get('debug', False):
            self.logger.setLevel(logging.DEBUG)
    
    def generate(self, prompt: str, **kwargs) -> str:
        self.logger.debug(f"Generate called with prompt: {prompt[:100]}...")
        self.logger.debug(f"Parameters: {kwargs}")
        
        try:
            response = self._call_api(prompt, **kwargs)
            self.logger.debug(f"Response length: {len(response)}")
            return response
        except Exception as e:
            self.logger.error(f"Generation failed: {e}", exc_info=True)
            raise
```

### Provider Diagnostics

```python
class DiagnosticProvider(BaseProvider):
    def run_diagnostics(self) -> Dict[str, Any]:
        """Run provider diagnostics."""
        results = {
            'connection': self._test_connection(),
            'authentication': self._test_auth(),
            'models': self._test_models(),
            'generation': self._test_generation(),
            'features': self._test_features()
        }
        return results
    
    def _test_connection(self) -> bool:
        """Test network connectivity."""
        try:
            response = requests.get(self.base_url, timeout=5)
            return response.status_code < 500
        except:
            return False
    
    def _test_auth(self) -> bool:
        """Test authentication."""
        try:
            self.generate("test", max_tokens=1)
            return True
        except AuthenticationError:
            return False
    
    def _test_features(self) -> Dict[str, bool]:
        """Test feature support."""
        return {
            'streaming': self._test_streaming(),
            'interactive': self.supports_interactive(),
            'sessions': self._test_sessions()
        }
```

## Next Steps

- Review the [BaseProvider API Reference](../api/providers.md)
- See [Provider Configuration Guide](configuration.md) for setup
- Check [Provider Testing Guide](testing.md) for test strategies
- Browse [Example Providers](https://github.com/hydra/providers) for reference implementations