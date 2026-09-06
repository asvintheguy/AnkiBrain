import { store } from "./redux";
import { addDocuments as addDocumentsToStore, deleteAllDocuments as del } from "./redux/slices/documentsSlice";
import { pyOpenDocumentBrowser } from "./PythonBridge/senders/pyOpenDocumentBrowser";
import { setDocumentsLoading } from "./redux/slices/documentsLoadingSlice";
import { setUseDocuments as set } from "./redux/slices/useDocuments";
import { setAppAlertModal } from "./redux/slices/appAlertModal";
import { clearMessages } from "./chat";
import { errorToast, infoToast, successToast } from "./toast";
import { asendPythonCommand } from "./PythonBridge";
import { InterprocessCommand as IC } from "./PythonBridge/InterprocessCommand";

export async function splitDocument(dispatch = store.dispatch) {
  try {
    const { documents = [] } = await pyOpenDocumentBrowser();
    if (!documents.length) return;
    if (documents.length > 1) infoToast("Multiple Documents", "Only the first selected document will be used.");
    const document = documents[0];
    if (document.size > 1024 ** 3) {
      infoToast("Document Too Large", "The maximum file size is 1 GB.");
      return;
    }
    infoToast("Processing Document", "Large documents may take a while to process.");
    const result = await asendPythonCommand(IC.SPLIT_DOCUMENT, { path: document.path });
    return result.chunks;
  } catch (error) {
    errorToast("Could not process document", error.message || String(error));
  }
}

export async function importDocuments(dispatch = store.dispatch) {
  if (process.env.REACT_APP_ENV === "STANDALONE") return;
  dispatch(setDocumentsLoading(true));
  try {
    const { documents = [] } = await pyOpenDocumentBrowser();
    if (!documents.length) return;
    if (documents.some(document => document.size > 1024 ** 3)) {
      infoToast("Document Too Large", "The maximum file size is 1 GB per document.");
      return;
    }
    infoToast("Adding Documents", "Indexing happens on this computer and may take several minutes.");
    const result = await asendPythonCommand(IC.ADD_DOCUMENTS, { documents });
    dispatch(addDocumentsToStore(result.documents_added));
    successToast("Documents Added", `${result.documents_added.length} document(s) indexed locally.`);
  } catch (error) {
    errorToast("Could not import documents", error.message || String(error));
  } finally {
    dispatch(setDocumentsLoading(false));
  }
}

export async function deleteAllDocuments(dispatch = store.dispatch) {
  try {
    await asendPythonCommand(IC.DELETE_ALL_DOCUMENTS);
    dispatch(del());
    dispatch(set(false));
  } catch (error) {
    errorToast("Could not delete documents", error.message || String(error));
  }
}

export async function setUseDocuments(useDocuments = false, dispatch = store.dispatch) {
  if (useDocuments && !store.getState().documents.value.length) {
    dispatch(setAppAlertModal({ header: "No documents", alertText: "Import at least one document before using this option.", show: true }));
    return;
  }
  try {
    if (store.getState().messages.value.length > 0) {
      await clearMessages();
      infoToast("Clearing Conversation", "Changing document sources clears your current conversation.");
    }
    dispatch(set(useDocuments));
  } catch (error) {
    errorToast("Could not change document sources", error.message || String(error));
  }
}
