import { pyExplainTopic } from "./PythonBridge/senders/pyExplainTopic";
import { store } from "./redux";
import { clearMessages } from "./chat";
import { infoToast, errorToast } from "./toast";
import { setTopicExplanationLoading } from "./redux/slices/topicExplanation";

export async function explainTopic(topic, options = {
  customPrompt: "", levelOfDetail: "EXTREME", levelOfExpertise: "EXPERT",
  useDocuments: false, language: store.getState().language.value,
}, dispatch = store.dispatch) {
  dispatch(setTopicExplanationLoading(true));
  try {
    if (store.getState().messages.value.length > 0) {
      await clearMessages();
      infoToast("Clearing Conversation", "This action clears your active conversation.");
    }
    pyExplainTopic(topic, options);
  } catch (error) {
    dispatch(setTopicExplanationLoading(false));
    errorToast("Could not explain topic", error.message || String(error));
  }
}
