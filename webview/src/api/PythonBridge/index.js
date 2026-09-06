import { handleExplainSelectedText } from "./receivers/handleExplainSelectedText";
import { handleDidExplainTopic } from "./receivers/handleDidExplainTopic";
import { handleTalkSelectedText } from "./receivers/handleTalkSelectedText";
import { addAIMessageToStore } from "../chat";
import { InterprocessCommand as IC } from "./InterprocessCommand";
import { setDocuments } from "../redux/slices/documentsSlice";
import { store } from "../redux";
import { setBoolGlobalLoadingIndicator } from "../redux/slices/bGlobalLoadingIndicator";
import { setChatLoading } from "../redux/slices/chatLoading";
import { setDocumentsLoading } from "../redux/slices/documentsLoadingSlice";
import { errorToast } from "../toast";
import { setPyCommandLock } from "../redux/slices/pyCommandLock";
import { stopAllLoaders } from "../redux/stopAllLoaders";
import { setCurrentVersion } from "../redux/slices/currentVersion";
import { setAIConnection } from "../redux/slices/appSettings";
import { setLoadingText } from "../redux/slices/loadingText";
import { setColorMode } from "../redux/slices/colorMode";
import { setLanguage } from "../redux/slices/language";
import { setCards } from "../redux/slices/cards";
import { setShowCardBottomHint } from "../redux/slices/showCardBottomHint";
import { setAutomaticallyAddCards } from "../redux/slices/automaticallyAddCards";
import { setDeleteCardsAfterAdding } from "../redux/slices/deleteCardsAfterAdding";
import { setAppDidBoot } from "../redux/slices/appDidBoot";
import { setCustomPromptChat, setCustomPromptMakeCards, setCustomPromptTopicExplanation } from "../redux/slices/customPrompts";

export async function handlePythonDataReceived(response, dispatch, navigate) {
  const { cmd, data = {} } = response;
  // Failed DID_* replies have no success payload to render; their caller handles the rejection.
  if (response.error && cmd !== IC.ERROR) return;
  switch (cmd) {
    case "aiSettingsChanged":
      dispatch(setAIConnection(data));
      break;
    case "explainSelectedText":
      handleExplainSelectedText(response.text, dispatch, navigate);
      break;
    case "talkSelectedText":
      handleTalkSelectedText(response.text, dispatch, navigate);
      break;
    case IC.DID_EXPLAIN_TOPIC:
      handleDidExplainTopic(data.explanation, dispatch, navigate);
      break;
    case IC.DID_ASK_CONVERSATION_NO_DOCUMENTS:
    case IC.DID_ASK_CONVERSATION_DOCUMENTS: {
      const sources = data.source_documents ? JSON.parse(data.source_documents).map(doc => doc.page_content) : [];
      const { llmModel, temperature } = store.getState().appSettings.ai;
      addAIMessageToStore(data.response, sources, llmModel, temperature, dispatch);
      dispatch(setChatLoading(false));
      break;
    }
    case IC.DID_CLOSE_DOCUMENT_BROWSER_NO_SELECTIONS:
      dispatch(setDocumentsLoading(false));
      break;
    case IC.DID_LOAD_SETTINGS: {
      // Explicit fields only: never restore old server accounts, mode, billing, or tokens.
      const actions = {
        aiLanguage: setLanguage, automaticallyAddCards: setAutomaticallyAddCards,
        deleteCardsAfterAdding: setDeleteCardsAfterAdding, currentVersion: setCurrentVersion,
        customPromptChat: setCustomPromptChat, customPromptMakeCards: setCustomPromptMakeCards,
        customPromptTopicExplanation: setCustomPromptTopicExplanation, colorMode: setColorMode,
        documents_saved: setDocuments, showCardBottomHint: setShowCardBottomHint,
      };
      for (const [key, action] of Object.entries(actions)) {
        if (data[key] !== undefined && data[key] !== null) dispatch(action(data[key]));
      }
      if (data.tempCards) dispatch(setCards(typeof data.tempCards === "string" ? JSON.parse(data.tempCards) : data.tempCards));
      break;
    }
    case IC.DID_FINISH_STARTUP:
      dispatch(setBoolGlobalLoadingIndicator(false));
      dispatch(setAppDidBoot(true));
      break;
    case IC.SET_WEBAPP_LOADING:
      dispatch(setBoolGlobalLoadingIndicator(data.value));
      break;
    case IC.SET_WEBAPP_LOADING_TEXT:
      dispatch(setLoadingText(data.text));
      break;
    case IC.STOP_LOADERS:
      stopAllLoaders(dispatch);
      break;
    case IC.ERROR:
      errorToast("Error", data.message || response.error);
      stopAllLoaders(dispatch);
      dispatch(setPyCommandLock(false));
      break;
    default:
      break;
  }
}

const commandResolvers = new Map();
let commandIdCounter = 0;

export function initPythonBridge(window, dispatch, navigate) {
  window.receiveFromPython = (response) => {
    const failed = Boolean(response.error) || response.cmd === IC.ERROR;
    if (response.cmd.startsWith("DID_") || failed) {
      dispatch(setPyCommandLock(false));
      const pending = commandResolvers.get(response.commandId);
      if (pending) {
        commandResolvers.delete(response.commandId);
        if (failed) {
          pending.reject(new Error(response.error || response.data?.message || "AnkiBrain request failed."));
        } else {
          try {
            pending.resolve(typeof response.data === "string" ? JSON.parse(response.data) : response.data || {});
          } catch (error) {
            pending.reject(error);
          }
        }
      }
    }
    handlePythonDataReceived(response, dispatch, navigate);
  };
}

function _sendToPython(data) {
  // Qt's console-message transport, not a diagnostic log. Do not send credentials here.
  console.log(`DATA_FROM_REACT: ${JSON.stringify(data)}`);
}

export function sendPythonCommand(cmd, params = {}) {
  if (process.env.REACT_APP_ENV === "STANDALONE") return true;
  if (store.getState().pyCommandLock.value) {
    errorToast("Busy", "Please wait for the current action to complete.");
    return false;
  }
  store.dispatch(setPyCommandLock(true));
  _sendToPython({ cmd, ...params });
  return true;
}

export async function asendPythonCommand(cmd, params = {}) {
  if (process.env.REACT_APP_ENV === "STANDALONE") return {};
  return new Promise((resolve, reject) => {
    const commandId = ++commandIdCounter;
    commandResolvers.set(commandId, { resolve, reject });
    _sendToPython({ cmd, commandId, ...params });
  });
}
