import { Box, Button, Heading, Text, VStack } from "@chakra-ui/react";
import { useSelector } from "react-redux";
import { asendPythonCommand } from "../api/PythonBridge";
import { InterprocessCommand as IC } from "../api/PythonBridge/InterprocessCommand";
import { errorToast, infoToast } from "../api/toast";

export async function openAIConnection(signIn = false) {
  if (process.env.REACT_APP_ENV === "STANDALONE") {
    infoToast("Desktop sign-in", "Open AnkiBrain in Anki Desktop to connect your account.");
    return;
  }
  try {
    await asendPythonCommand(IC.OPEN_AI_SETTINGS, { signIn });
  } catch (error) {
    errorToast("Could not open AI settings", error.message);
  }
}

export function AIConnection({ welcome = false }) {
  const ai = useSelector(state => state.appSettings.ai);
  const needsSignIn = ai.provider === "chatgpt" && !ai.signedIn;
  return (
    <Box p={6} maxWidth="650px" mx="auto">
      <VStack align="stretch" spacing={4}>
        <Heading size="md">{welcome ? "Welcome to AnkiBrain" : "Your AI connection"}</Heading>
        <Text>{needsSignIn ? "Connect ChatGPT to explain topics, make flashcards, and study your documents." :
          `${ai.provider === "chatgpt" ? "ChatGPT" : "API provider"} · ${ai.llmModel || "Choose a model"}`}</Text>
        {needsSignIn && <Text fontSize="sm">Use your ChatGPT account. No AnkiBrain account, balance top-up, API key, or provider CLI needed.</Text>}
        {ai.error && <Text role="alert" color="orange.400">{ai.error}</Text>}
        <Button variant="accent" onClick={() => openAIConnection(needsSignIn)}>
          {needsSignIn ? "Sign in with ChatGPT" : "AI connection settings"}
        </Button>
        {needsSignIn && <Button variant="ghost" onClick={() => openAIConnection()}>Use an API provider instead</Button>}
        <Text fontSize="sm" color="gray.500">
          Experimental ChatGPT-backed Codex connection; plan/model limits apply.
          Prompts and document excerpts go to your chosen provider. API providers may charge separately.
        </Text>
        {!ai.engineReady && <Text fontSize="sm">First installation? Use AnkiBrain → Set Up / Repair Study Engine to finish the one-time Python setup. You can sign in now.</Text>}
      </VStack>
    </Box>
  );
}
