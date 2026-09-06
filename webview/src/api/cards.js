import { pyGenerateCards } from "./PythonBridge/senders/pyGenerateCards";
import { store } from "./redux";
import { addCards, setCards } from "./redux/slices/cards";
import { setMakeCardsLoading } from "./redux/slices/makeCardsText";
import { errorToast, infoToast, successToast } from "./toast";
import { addFailedCards } from "./redux/slices/failedCards";
import { pyEditSetting } from "./PythonBridge/senders/pyEditSetting";

function convertAsterisksToCloze(text) {
  let counter = 1;
  let newStr = text.replace(/\*([^*]+)\*/g, function (match, group1) {
    return `{{c${counter++}::${group1}}}`;
  });

  return newStr;
}

async function handleCardsRawString(
  rawString,
  cardType,
  dispatch = store.dispatch
) {
  // Try converting to json
  try {
    let cards = JSON.parse(rawString);
    for (let card of cards) {
      if (!card.type) {
        card.type = cardType;
      }
      if (!card.tags) {
        card.tags = [];
      }

      /*
       * If cloze, we are expecting the text field to have **double asterisks** surrounding
       * important text that gpt wants to be a cloze deletion.
       */
      if (cardType === "cloze") {
        card.text = convertAsterisksToCloze(card.text);
      }
    }

    dispatch(addCards(cards));

    // TODO: needs to be removed, this only adds the currently made cards to temp cards rather than the entire deck in
    //  the redux store.
    await pyEditSetting("tempCards", cards);
    successToast(
      "Made Flashcards",
      `Successfully made ${cards.length} cards.`,
      3000
    );
  } catch (err) {
    dispatch(addFailedCards([rawString]));
    infoToast(
      "Some cards failed",
      "Some of your cards were generated improperly. " +
        "They may require a slight modification to work. " +
        'The malformed JSON strings have been placed in the "Failed Cards" tab.'
    );
  }
}

export async function generateCards(
  text,
  customPrompt = "",
  cardType = "basic",
  language = store.getState().language.value,
  dispatch = store.dispatch
) {
  dispatch(setMakeCardsLoading(true));
  try {
    const res = await pyGenerateCards(text, customPrompt, cardType, language);
    if (!res.cardsRawString) throw new Error("The AI did not return flashcard JSON. Retry or change the model/prompt.");
    await handleCardsRawString(res.cardsRawString, cardType, dispatch);
  } catch (err) {
    errorToast("Error Making Cards", err.message || String(err));
  } finally {
    dispatch(setMakeCardsLoading(false));
  }
}

export function setSampleCards() {
  const sampleCards = [
    {
      text: "This is a {{c1::test}} cloze card",
      type: "cloze",
      tags: ["ankibrain", "cloze"],
    },
    {
      text: "This is a {{c1::test}} cloze card #2",
      type: "cloze",
      tags: ["ankibrain", "cloze"],
    },
    {
      text: "This is a {{c1::test}} cloze card #3",
      type: "cloze",
      tags: ["ankibrain", "cloze"],
    },
    {
      front: "basic card front text",
      back: "basic card back text",
      type: "basic",
      tags: ["ankibrain", "basic"],
    },
    {
      front: "basic card front text #2",
      back: "basic card back text #2",
      type: "basic",
      tags: ["ankibrain", "basic"],
    },
    {
      front: "basic card front text #3",
      back: "basic card back text #3",
      type: "basic",
      tags: ["ankibrain", "basic"],
    },
  ];

  store.dispatch(setCards(sampleCards));
}
