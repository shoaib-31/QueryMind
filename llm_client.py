"""
LLM Client wrapper for LiteLLM with native Gemini SDK fallback.
Provides a simple interface for making LLM calls.
"""

from typing import Optional, Dict, Any
import litellm
from config import get_settings
import logging
import os

logger = logging.getLogger(__name__)

# Completely suppress internal OpenAI client logs (LiteLLM uses OpenAI client internally)
logging.getLogger("openai").setLevel(logging.CRITICAL)
logging.getLogger("openai._base_client").setLevel(logging.CRITICAL)
logging.getLogger("httpx").setLevel(logging.CRITICAL)

# Configure LiteLLM to use custom proxy with fast retries
litellm.num_retries = 0  # Disable LiteLLM's retry - we'll handle it ourselves
litellm.request_timeout = 30
litellm.drop_params = True  # Drop unsupported params instead of erroring

# Monkey patch sleep to cap retry delays at 3 seconds globally
import time
_original_sleep = time.sleep

def _fast_sleep(seconds):
    """Cap all sleep durations at 3 seconds"""
    if seconds > 3:
        _original_sleep(3)
    else:
        _original_sleep(seconds)

time.sleep = _fast_sleep

logger.info("LLM Client configured: Custom proxy + Gemini fallback (3s retry delay)")

# Import Gemini SDK for fallback (lazy import to avoid startup issues)
_gemini_client = None

def _get_gemini_client():
    """Lazy load Gemini client."""
    global _gemini_client
    if _gemini_client is None:
        try:
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                _gemini_client = genai.Client(api_key=api_key)
                logger.debug("Gemini SDK client initialized")
        except ImportError:
            logger.warning("google-genai package not installed. Gemini fallback unavailable.")
        except Exception as e:
            logger.warning(f"Failed to initialize Gemini client: {e}")
    return _gemini_client


class LLMClient:
    """Wrapper for LLM API calls using LiteLLM with Gemini fallback."""
    
    def __init__(self):
        """Initialize LLM client with settings."""
        settings = get_settings()
        
        # Configure primary LLM
        api_key = settings.litellm_api_key or settings.openai_api_key
        
        if not api_key and not settings.gemini_api_key:
            raise ValueError(
                "No API key found. Please set LITELLM_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY in .env file"
            )
        
        # Set API key
        if api_key:
            litellm.api_key = api_key
        
        # Configure custom base URL if using LiteLLM proxy
        self.api_base = None
        if settings.litellm_base_url:
            self.api_base = settings.litellm_base_url
            os.environ["LITELLM_BASE_URL"] = settings.litellm_base_url
            logger.info(f"Using custom LiteLLM base URL: {self.api_base}")
        elif settings.litellm_api_key and not settings.openai_api_key:
            logger.warning(
                "LITELLM_API_KEY is set but LITELLM_BASE_URL is not. "
                "If you're using a LiteLLM proxy, set LITELLM_BASE_URL in .env"
            )
        
        # Gemini fallback configuration (native SDK)
        self.gemini_api_key = settings.gemini_api_key
        self.fallback_model = settings.llm_fallback_model
        if self.gemini_api_key:
            os.environ["GEMINI_API_KEY"] = self.gemini_api_key
            # Extract model name (remove 'gemini/' prefix if present)
            self.fallback_model_name = self.fallback_model.replace("gemini/", "")
            logger.info(f"Gemini fallback configured: {self.fallback_model_name} (native SDK)")
        else:
            self.fallback_model_name = None
        
        self.model = settings.llm_model
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens
        self.timeout = settings.llm_timeout
        
        logger.info(f"LLM Client initialized with model: {self.model}")
    
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False
    ) -> str:
        """
        Generate a response from the LLM with automatic Gemini fallback.
        
        Args:
            system_prompt: System/instruction prompt
            user_prompt: User query/prompt
            temperature: Override default temperature
            max_tokens: Override default max tokens
            json_mode: Whether to request JSON output
            
        Returns:
            Generated text response
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # Try primary model first
        try:
            return self._call_llm(
                messages=messages,
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
                use_custom_base=True
            )
        except Exception as primary_error:
            logger.warning(f"Primary LLM failed: {primary_error}")
            
            # Fall back to Gemini if available (using native SDK)
            if self.gemini_api_key and self.fallback_model_name:
                logger.info(f"Falling back to Gemini ({self.fallback_model_name}) via native SDK...")
                try:
                    return self._call_gemini_native(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                except Exception as fallback_error:
                    logger.error(f"Gemini fallback also failed: {fallback_error}")
                    raise RuntimeError(
                        f"Both primary and fallback LLM failed. "
                        f"Primary: {str(primary_error)}, Fallback: {str(fallback_error)}"
                    )
            else:
                # No fallback available
                raise RuntimeError(f"LLM call failed: {str(primary_error)}")
    
    def _call_llm(
        self,
        messages: list,
        model: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        use_custom_base: bool = True
    ) -> str:
        """
        Internal method to call LLM.
        
        Args:
            messages: Chat messages
            model: Model name
            temperature: Temperature setting
            max_tokens: Max tokens
            json_mode: JSON output mode
            use_custom_base: Whether to use custom base URL
            
        Returns:
            Generated text response
        """
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature or self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
            "timeout": 30,
            "num_retries": 0,  # No auto-retry, we handle manually
        }
        
        # Add custom base URL if configured and requested
        if use_custom_base and self.api_base:
            kwargs["api_base"] = self.api_base
            kwargs["custom_llm_provider"] = "openai"
        
        # Enable JSON mode if requested (for supported models)
        if json_mode and ("gpt" in model.lower() or "gemini" in model.lower()):
            kwargs["response_format"] = {"type": "json_object"}
        
        endpoint = self.api_base if (use_custom_base and self.api_base) else "gemini-direct"
        logger.debug(f"LLM request to {endpoint} ({model}): {messages[-1]['content'][:100]}...")
        
        # Manual retry logic with 3 second delay
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = litellm.completion(**kwargs)
                break  # Success, exit retry loop
            except Exception as e:
                if attempt < max_attempts - 1:
                    error_msg = str(e)
                    if "429" in error_msg or "rate" in error_msg.lower():
                        logger.warning(f"Rate limited on attempt {attempt + 1}/{max_attempts}, retrying in 3s...")
                        import time
                        time.sleep(3)
                        continue
                # Last attempt or non-retryable error, raise it
                raise
        
        try:
            pass  # Response assigned above
            
            # Log raw response for debugging
            logger.debug(f"Raw LLM response type: {type(response)}")
            logger.debug(f"Raw LLM response: {response}")
            
            # Safely extract content with error handling
            if not response:
                raise RuntimeError("LLM returned empty response")
            
            if not hasattr(response, 'choices') or not response.choices:
                logger.error(f"Response object attributes: {dir(response)}")
                raise RuntimeError(f"LLM response missing 'choices': {response}")
            
            logger.debug(f"Choices count: {len(response.choices)}")
            
            if not response.choices[0]:
                raise RuntimeError("LLM response choices[0] is None")
            
            if not hasattr(response.choices[0], 'message'):
                logger.error(f"Choice[0] attributes: {dir(response.choices[0])}")
                raise RuntimeError(f"LLM response missing 'message': {response.choices[0]}")
            
            content = response.choices[0].message.content
            
            logger.debug(f"Content type: {type(content)}, Content value: {content}")
            
            if content is None or content == "":
                logger.error(f"Full response object: {response}")
                logger.error(f"Response dict: {response.model_dump() if hasattr(response, 'model_dump') else 'N/A'}")
                raise RuntimeError("LLM returned None or empty content")
            
            logger.debug(f"LLM response: {content[:100]}...")
            
            return content
            
        except AttributeError as e:
            logger.error(f"LLM response structure error: {e}")
            logger.error(f"Response object: {response if 'response' in locals() else 'No response'}")
            raise RuntimeError(f"Failed to parse LLM response structure: {str(e)}")
    
    def _call_gemini_native(
        self,
        messages: list,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Call Gemini using native Google GenAI SDK (not LiteLLM).
        This avoids Vertex AI and uses the direct Gemini API.
        
        Args:
            messages: Chat messages
            temperature: Temperature setting
            max_tokens: Max tokens
            
        Returns:
            Generated text response
        """
        client = _get_gemini_client()
        if client is None:
            raise RuntimeError("Gemini client not available. Check GEMINI_API_KEY and google-genai installation.")
        
        # Convert messages to single prompt
        # Gemini's generate_content expects a single string or list of parts
        prompt_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt_parts.append(f"Instructions: {content}")
            else:
                prompt_parts.append(content)
        
        combined_prompt = "\n\n".join(prompt_parts)
        
        logger.debug(f"Gemini native request ({self.fallback_model_name}): {combined_prompt[:100]}...")
        
        # Configure generation
        config = {}
        if temperature is not None:
            config['temperature'] = temperature
        elif self.temperature is not None:
            config['temperature'] = self.temperature
        
        if max_tokens is not None:
            config['max_output_tokens'] = max_tokens
        elif self.max_tokens is not None:
            config['max_output_tokens'] = self.max_tokens
        
        # Call Gemini API
        try:
            response = client.models.generate_content(
                model=self.fallback_model_name,
                contents=combined_prompt,
                config=config if config else None
            )
            
            # Log raw response for debugging
            logger.debug(f"Raw Gemini response type: {type(response)}")
            logger.debug(f"Gemini response attributes: {dir(response)}")
            
            if not response:
                raise RuntimeError("Gemini returned empty response")
            
            # Try to extract text with multiple methods
            content = None
            
            # Method 1: Direct text attribute
            if hasattr(response, 'text') and response.text:
                content = response.text
                logger.debug(f"Extracted via .text: {content[:100] if content else 'None'}")
            
            # Method 2: Through candidates
            elif hasattr(response, 'candidates') and response.candidates:
                logger.debug(f"Candidates count: {len(response.candidates)}")
                if response.candidates[0].content.parts:
                    content = response.candidates[0].content.parts[0].text
                    logger.debug(f"Extracted via candidates: {content[:100] if content else 'None'}")
            
            # Method 3: Log what we have if nothing worked
            if content is None or content == "":
                logger.error(f"Gemini response structure:")
                logger.error(f"  - hasattr 'text': {hasattr(response, 'text')}")
                logger.error(f"  - hasattr 'candidates': {hasattr(response, 'candidates')}")
                if hasattr(response, 'candidates'):
                    logger.error(f"  - candidates: {response.candidates}")
                logger.error(f"Full response: {response}")
                raise RuntimeError(f"Gemini returned None or empty content. Response: {response}")
            
            logger.debug(f"Gemini native response: {content[:100]}...")
            
            return content
            
        except AttributeError as e:
            logger.error(f"Gemini response structure error: {e}")
            logger.error(f"Response object: {response if 'response' in locals() else 'No response'}")
            raise RuntimeError(f"Failed to parse Gemini response structure: {str(e)}")
    
    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Generate a structured JSON response from the LLM.
        Note: JSON mode may not work with Gemini fallback.
        
        Args:
            system_prompt: System/instruction prompt
            user_prompt: User query/prompt
            temperature: Override default temperature
            
        Returns:
            Parsed JSON dictionary
        """
        import json
        
        # For JSON, we'll try without json_mode since Gemini SDK doesn't support it
        response = self.generate(
            system_prompt=system_prompt + "\n\nIMPORTANT: Return ONLY valid JSON, no other text.",
            user_prompt=user_prompt,
            temperature=temperature,
            json_mode=False  # Gemini SDK doesn't support JSON mode
        )
        
        try:
            # Clean up response if needed
            response = response.strip()
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]
            
            return json.loads(response)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {e}")
            logger.error(f"Response was: {response}")
            raise ValueError(f"LLM returned invalid JSON: {str(e)}")

