import "./SideBar.css";
import { useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useColorMode } from "@chakra-ui/react";
import { MdDarkMode } from "react-icons/md";
import { BsSunFill } from "react-icons/bs";
import { pyEditSetting } from "../../api/PythonBridge/senders/pyEditSetting";
import { setColorMode } from "../../api/redux/slices/colorMode";
import { openAIConnection } from "../AIConnection";

export function SideBar() {
  const { colorMode, toggleColorMode } = useColorMode();
  const dispatch = useDispatch();
  const ai = useSelector(state => state.appSettings.ai);
  const language = useSelector(state => state.language.value);
  const version = useSelector(state => state.currentVersion.value);
  const savedColorMode = useSelector(state => state.colorMode.value);
  useEffect(() => {
    if (savedColorMode && savedColorMode !== colorMode) toggleColorMode();
  }, [savedColorMode, colorMode, toggleColorMode]);
  const needsSignIn = ai.provider === "chatgpt" && !ai.signedIn;
  return (
    <header className="TopHeader">
      <div className="TopHeader-left">
        <span className="TopHeader-brand" title={`AnkiBrain ${version}`}>AnkiBrain</span>
        <span className="TopHeader-language">{language}</span>
        <button className="TopHeader-colorToggle" aria-label="Toggle light and dark theme" onClick={async () => {
          const next = colorMode === "dark" ? "light" : "dark";
          dispatch(setColorMode(next));
          await pyEditSetting("colorMode", next);
        }}>
          {colorMode === "light" ? <MdDarkMode size={16} /> : <BsSunFill size={16} />}
        </button>
      </div>
      <div className="TopHeader-right">
        <button className="TopHeader-actionBtn" title={ai.llmModel || "Connect your AI provider"} onClick={() => openAIConnection(needsSignIn)}>
          {needsSignIn ? "Connect ChatGPT" : ai.provider === "chatgpt" ? "ChatGPT · Settings" : "API · Settings"}
        </button>
      </div>
    </header>
  );
}
