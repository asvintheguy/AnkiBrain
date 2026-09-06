import { createSlice } from "@reduxjs/toolkit";

export const appSettings = createSlice({
  name: "appSettings",
  initialState: {
    ai: {
      llmModel: "",
      temperature: "Provider default",
      provider: "chatgpt",
      signedIn: false,
      configured: false,
      engineReady: false,
      error: "",
    },
  },
  reducers: {
    setAIConnection: (state, { payload }) => {
      const { provider, model, temperature, signedIn, configured, engineReady, error } = payload;
      Object.assign(state.ai, { provider, llmModel: model, temperature: temperature ?? "Provider default",
        signedIn, configured, engineReady, error });
    },
    setLLMModel: (state, action) => {
      state.ai.llmModel = action.payload;
    },
    setTemperature: (state, action) => {
      state.ai.temperature = action.payload;
    },
  },
});

export const { setLLMModel, setTemperature, setAIConnection } = appSettings.actions;
