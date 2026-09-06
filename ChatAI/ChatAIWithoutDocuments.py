from typing import Tuple

from langchain import ConversationChain
from ProviderLLM import ProviderLLM
from langchain.memory import ConversationBufferMemory

from ChatInterface import ChatInterface


class ChatAIWithoutDocuments(ChatInterface):
    def __init__(self, verbose=False):
        self.llm = ProviderLLM()
        self.memory = ConversationBufferMemory()
        self.conversationChain = ConversationChain(llm=self.llm, memory=self.memory, verbose=verbose)

    def human_message(self, query: str) -> Tuple[str, None]:
        return self.conversationChain.predict(input=query), None

    def clear_memory(self):
        self.memory.clear()
