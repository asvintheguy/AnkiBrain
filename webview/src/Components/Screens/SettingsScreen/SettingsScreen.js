import { Box, Button, Divider, FormControl, FormLabel, Input, Switch, Text, VStack } from "@chakra-ui/react";
import { useDispatch, useSelector } from "react-redux";
import { useState } from "react";
import { AIConnection } from "../../AIConnection";
import { pyEditSetting } from "../../../api/PythonBridge/senders/pyEditSetting";
import { setLanguage } from "../../../api/redux/slices/language";
import { setShowCardBottomHint } from "../../../api/redux/slices/showCardBottomHint";
import { setAutomaticallyAddCards } from "../../../api/redux/slices/automaticallyAddCards";
import { setDeleteCardsAfterAdding } from "../../../api/redux/slices/deleteCardsAfterAdding";
import { errorToast } from "../../../api/toast";

const languages = "English|Spanish|Albanian|Arabic|Armenian|Azerbaijani|Belarusian|Bengali|Bulgarian|Bosnian|Chinese (Mandarin)|Chinese (Cantonese)|Croatian|Czech|Danish|Dutch|Estonian|Farsi (Persian)|Filipino|Finnish|French|German|Greek|Hindi|Icelandic|Indonesian|Irish (Gaelic)|Italian|Japanese|Kazakh|Khmer|Korean|Kurdish|Hebrew|Hungarian|Malay|Mongolian|Norwegian|Polish|Portuguese|Romanian|Russian|Serbian|Swedish|Thai|Turkish|Ukrainian|Urdu|Vietnamese".split("|");

export function SettingsScreen(props) {
  const dispatch = useDispatch();
  const language = useSelector(state => state.language.value);
  const [draftLanguage, setDraftLanguage] = useState(language);
  const automaticallyAddCards = useSelector(state => state.automaticallyAddCards.value);
  const deleteCardsAfterAdding = useSelector(state => state.deleteCardsAfterAdding.value);
  const showCardBottomHint = useSelector(state => state.showCardBottomHint.value);

  async function save(key, value, action) {
    try {
      await pyEditSetting(key, value);
      dispatch(action(value));
    } catch (error) {
      errorToast("Could not save setting", error.message || String(error));
    }
  }

  return (
    <Box {...props} maxWidth="700px" mx="auto">
      <AIConnection />
      <Divider />
      <VStack align="stretch" spacing={5} p={6}>
        <FormControl>
          <FormLabel htmlFor="ai-language">AI response language</FormLabel>
          <Input id="ai-language" list="ai-languages" value={draftLanguage} maxLength={100} onChange={event => setDraftLanguage(event.target.value)} />
          <datalist id="ai-languages">{languages.map(name => <option value={name} key={name} />)}</datalist>
          <Text fontSize="sm" color="gray.500">Choose or type a language. This changes AI responses, not the interface.</Text>
          <Button mt={2} isDisabled={!draftLanguage.trim() || draftLanguage.trim() === language}
            onClick={() => save("aiLanguage", draftLanguage.trim(), setLanguage)}>Save language</Button>
        </FormControl>
        <FormControl display="flex" alignItems="center">
          <FormLabel htmlFor="auto-add" mb={0}>Automatically add batches of 100 cards to Anki and clear them here</FormLabel>
          <Switch id="auto-add" isChecked={automaticallyAddCards} onChange={event => save("automaticallyAddCards", event.target.checked, setAutomaticallyAddCards)} />
        </FormControl>
        <Text fontSize="sm" color="gray.500">Uses the deck selected in Make Cards. Clearing added cards helps avoid duplicates and large in-memory batches.</Text>
        <FormControl display="flex" alignItems="center">
          <FormLabel htmlFor="clear-added" mb={0}>Clear AnkiBrain cards after I click Add Cards to Anki</FormLabel>
          <Switch id="clear-added" isChecked={deleteCardsAfterAdding} onChange={event => save("deleteCardsAfterAdding", event.target.checked, setDeleteCardsAfterAdding)} />
        </FormControl>
        <FormControl display="flex" alignItems="center">
          <FormLabel htmlFor="review-hint" mb={0}>Show the highlight-to-explain hint while reviewing Anki cards</FormLabel>
          <Switch id="review-hint" isChecked={showCardBottomHint} onChange={event => save("showCardBottomHint", event.target.checked, setShowCardBottomHint)} />
        </FormControl>
        <Button as="a" href="https://github.com/asvintheguy/AnkiBrain/blob/main/AI_PROVIDERS.md">Setup guide</Button>
        <Button as="a" href="https://github.com/asvintheguy/AnkiBrain/issues">Report a bug or request a feature</Button>
      </VStack>
    </Box>
  );
}
