from typing import Any, Dict, List, Optional

from langchain.llms.base import LLM

from AIProviders import load_config, run_provider


class ProviderLLM(LLM):
    @property
    def _llm_type(self) -> str:
        return 'ankibrain-provider'

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        config = load_config()
        provider = config['provider']
        return {'provider': provider, 'model': config['providers'][provider]['model']}

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager=None,
        **kwargs: Any,
    ) -> str:
        return run_provider(prompt, stop=stop)
