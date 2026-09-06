import { createSlice } from "@reduxjs/toolkit";

export const appAlertModal = createSlice({
  name: "appAlertModal",
  initialState: {
    value: {
      show: false,
      header: "header",
      alertText: "alertText",
    },
  },
  reducers: {
    setAppAlertModal: (state, action) => {
      state.value = action.payload;
    },
  },
});

export const { setAppAlertModal } = appAlertModal.actions;
