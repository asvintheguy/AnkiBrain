import { addMessage, clearMessages as clear } from "./redux/slices/messagesSlice";
import { setCurrentChatInput, store } from "./redux";
import { pyClearConversation } from "./PythonBridge/senders/pyClearConversation";
import { pyAskAIConversation } from "./PythonBridge/senders/pyAskAIConversation";
import { setChatLoading } from "./redux/slices/chatLoading";

export function addAIMessageToStore(text, sourceSnippets = [], model, temperature, dispatch = store.dispatch) {
  dispatch(addMessage({ type: "ai", text, sourceSnippets, model, temperature }));
}

export function addUserMessageToStore(text, dispatch = store.dispatch) {
  dispatch(addMessage({ type: "user", text }));
}

export async function sendUserMessage(text, useDocuments = false, dispatch = store.dispatch) {
  dispatch(setChatLoading(true));
  dispatch(setCurrentChatInput(""));
  pyAskAIConversation(text, useDocuments);
  addUserMessageToStore(text, dispatch);
}

export async function clearMessages(dispatch = store.dispatch) {
  await pyClearConversation();
  dispatch(clear());
}
