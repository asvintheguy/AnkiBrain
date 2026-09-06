import { act, fireEvent, render, screen } from "@testing-library/react";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import { store } from "./api/redux";
import { asendPythonCommand } from "./api/PythonBridge";
import { InterprocessCommand as IC } from "./api/PythonBridge/InterprocessCommand";
import { ImportScreen } from "./Components/Screens/ImportScreen/ImportScreen";
import { setDocuments } from "./api/redux/slices/documentsSlice";
import { errorToast } from "./api/toast";

jest.mock("./api/toast", () => ({ errorToast: jest.fn(), infoToast: jest.fn(), successToast: jest.fn() }));

beforeAll(() => {
  window.matchMedia = jest.fn().mockImplementation(query => ({ matches: false, media: query,
    addListener: jest.fn(), removeListener: jest.fn(), addEventListener: jest.fn(), removeEventListener: jest.fn() }));
});

test("native welcome, legacy-account isolation, main settings, and failed IPC recovery", async () => {
  const transport = jest.spyOn(console, "log").mockImplementation(() => {});
  const request = () => JSON.parse(transport.mock.calls.at(-1)[0].replace("DATA_FROM_REACT: ", ""));
  window.fetch = jest.fn(() => { throw new Error("Unexpected server request"); });
  render(<Provider store={store}><MemoryRouter initialEntries={["/settings"]}><App /></MemoryRouter></Provider>);
  await act(async () => {
    window.receiveFromPython({ cmd: IC.DID_LOAD_SETTINGS, data: { user_mode: "SERVER", user: { accessToken: "SECRET" },
      colorMode: "dark", currentVersion: "test", automaticallyAddCards: false, deleteCardsAfterAdding: false, tempCards: [] } });
    window.receiveFromPython({ cmd: IC.DID_FINISH_STARTUP });
  });
  expect(screen.getByRole("heading", { name: "Welcome to AnkiBrain" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Login" })).not.toBeInTheDocument();
  expect(screen.queryByText("Add Balance")).not.toBeInTheDocument();
  expect(store.getState().user).toBeUndefined();
  expect(store.getState().userMode).toBeUndefined();
  expect(document.body).not.toHaveTextContent("SECRET");
  expect(window.fetch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Sign in with ChatGPT" }));
  expect(request()).toMatchObject({ cmd: IC.OPEN_AI_SETTINGS, signIn: true });
  await act(async () => {
    window.receiveFromPython({ cmd: IC.DID_OPEN_AI_SETTINGS, commandId: request().commandId });
    window.receiveFromPython({ cmd: "aiSettingsChanged", data: { provider: "chatgpt", model: "account-model",
      signedIn: true, configured: true, engineReady: true, error: "" } });
  });
  expect(screen.getByRole("heading", { name: "Your AI connection" })).toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: "Advanced" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("AI response language")).toBeInTheDocument();

  // A generic Python ERROR must reject the matching promise, not hang the next AI action.
  const failed = asendPythonCommand(IC.GENERATE_CARDS, { text: "Water" });
  const rejected = expect(failed).rejects.toThrow("No completed answer");
  await act(async () => {
    window.receiveFromPython({ cmd: IC.ERROR, commandId: request().commandId,
      error: "No completed answer", data: { message: "No completed answer" } });
    await rejected;
  });
  expect(store.getState().pyCommandLock.value).toBe(false);
  expect(errorToast).toHaveBeenCalledWith("Error", "No completed answer");
  const retry = asendPythonCommand(IC.GENERATE_CARDS);
  await act(async () => {
    window.receiveFromPython({ cmd: IC.DID_GENERATE_CARDS, commandId: request().commandId,
      data: { cardsRawString: '[{"front":"Q","back":"A"}]' } });
    await expect(retry).resolves.toHaveProperty("cardsRawString");
  });
  transport.mockRestore();
});

test("imported documents display without a legacy server user", () => {
  store.dispatch(setDocuments([{ file_name: "study", extension: ".txt", path: "/study.txt", size: 100 }]));
  render(<Provider store={store}><ImportScreen /></Provider>);
  expect(screen.getByText("study.txt")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Delete Documents" })).toBeEnabled();
});
