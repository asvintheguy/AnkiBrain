import { configureStore, createSlice } from "@reduxjs/toolkit";
import { requestedTopicSlice } from "./slices/requestedTopic";
import { topicExplanationSlice } from "./slices/topicExplanation";
import { messagesSlice } from "./slices/messagesSlice";
import { documentsSlice } from "./slices/documentsSlice";
import { bGlobalLoadingIndicatorSlice } from "./slices/bGlobalLoadingIndicator";
import { chatLoadingSlice } from "./slices/chatLoading";
import { documentsLoadingSlice } from "./slices/documentsLoadingSlice";
import { cardsSlice } from "./slices/cards";
import { bShowCardsJsonEditor } from "./slices/bShowCardsJsonEditor";
import { useDocuments } from "./slices/useDocuments";
import { makeCardsSettings } from "./slices/makeCardsSettings";
import { appAlertModal } from "./slices/appAlertModal";
import { pyCommandLock } from "./slices/pyCommandLock";
import { makeCardsText } from "./slices/makeCardsText";
import { currentVersionSlice } from "./slices/currentVersion";
import { appSettings } from "./slices/appSettings";
import { loadingText } from "./slices/loadingText";
import { colorMode } from "./slices/colorMode";
import { failedCards } from "./slices/failedCards";
import { languageSlice } from "./slices/language";
import { showCardBottomHint } from "./slices/showCardBottomHint";
import { automaticallyAddCards } from "./slices/automaticallyAddCards";
import { deleteCardsAfterAdding } from "./slices/deleteCardsAfterAdding";
import { appDidBoot } from "./slices/appDidBoot";
import { customPrompts } from "./slices/customPrompts";

const currentChatInputSlice = createSlice({
  name: "currentChatInput",
  initialState: { value: "" },
  reducers: {
    setCurrentChatInput: (state, action) => {
      state.value = action.payload;
    },
  },
});

export const { setCurrentChatInput } = currentChatInputSlice.actions;

export const store = configureStore({
  reducer: {
    appAlertModal: appAlertModal.reducer,
    appDidBoot: appDidBoot.reducer,
    appSettings: appSettings.reducer,
    automaticallyAddCards: automaticallyAddCards.reducer,
    bGlobalLoadingIndicator: bGlobalLoadingIndicatorSlice.reducer,
    bShowCardsJsonEditor: bShowCardsJsonEditor.reducer,
    cards: cardsSlice.reducer,
    chatLoading: chatLoadingSlice.reducer,
    colorMode: colorMode.reducer,
    currentChatInput: currentChatInputSlice.reducer,
    currentVersion: currentVersionSlice.reducer,
    customPrompts: customPrompts.reducer,
    deleteCardsAfterAdding: deleteCardsAfterAdding.reducer,
    documents: documentsSlice.reducer,
    documentsLoading: documentsLoadingSlice.reducer,
    failedCards: failedCards.reducer,
    language: languageSlice.reducer,
    loadingText: loadingText.reducer,
    makeCardsSettings: makeCardsSettings.reducer,
    makeCardsText: makeCardsText.reducer,
    messages: messagesSlice.reducer,
    pyCommandLock: pyCommandLock.reducer,
    requestedTopic: requestedTopicSlice.reducer,
    showCardBottomHint: showCardBottomHint.reducer,
    topicExplanation: topicExplanationSlice.reducer,
    useDocuments: useDocuments.reducer,
  },
});
