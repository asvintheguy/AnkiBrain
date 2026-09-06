import {
  AlertDialog,
  AlertDialogBody,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogOverlay,
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Flex,
  Heading,
  Spacer,
  Spinner,
  Tag,
  Text,
  useColorMode,
} from "@chakra-ui/react";
import { useRef, useState } from "react";
import { AddIcon, DeleteIcon } from "@chakra-ui/icons";
import { useDispatch, useSelector } from "react-redux";
import "./ImportScreen.css";
import { deleteAllDocuments, importDocuments } from "../../../api/documents";

export function ImportScreen(props) {
  let importedDocs = useSelector((state) => state.documents.value);
  const [showDeleteAlert, setShowDeleteAlert] = useState(false);
  const deleteAlertCancelRef = useRef();
  const documentsLoading = useSelector((state) => state.documentsLoading.value);
  const dispatch = useDispatch();
  const { colorMode } = useColorMode();

  const DeleteDocumentAlert = (props) => {
    return (
      <AlertDialog
        isOpen={showDeleteAlert}
        leastDestructiveRef={deleteAlertCancelRef}
        onClose={props.onCancel}
      >
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader>Delete Document</AlertDialogHeader>
            <AlertDialogBody>
              Are you sure? This will delete all of documents in AnkiBrain. Your
              originals will NOT be deleted.
            </AlertDialogBody>
            <AlertDialogFooter>
              <Button ref={deleteAlertCancelRef} onClick={props.onCancel}>
                Cancel
              </Button>
              <Button colorScheme={"red"} onClick={props.onOK}>
                Delete
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    );
  };

  return (
    <Box {...props}>
      <Box ms={5}>
        <DeleteDocumentAlert
          onCancel={() => {
            setShowDeleteAlert(false);
          }}
          onOK={async () => {
            await deleteAllDocuments();
            setShowDeleteAlert(false);
          }}
        />

        <Flex mb={5} direction={"column"} p={0}>
          <Flex color={"gray"} fontSize={14} direction={"column"} mb={5}>
            <Text p={0} m={0}>
              Import your documents here for AI analysis.
            </Text>
            <Text fontSize={14} color={"gray"} p={0} m={0}>
              When you check the "Use Documents" option, these documents will be
              used when you chat with the AI or ask for a topic explanation.
            </Text>
            <Text fontSize={12} color={"gray"} mt={1}>
              Documents are indexed on this computer. Relevant excerpts are sent to your selected AI provider when used.
            </Text>
          </Flex>

          <Flex direction={"row"} alignSelf={"center"}>
            <Flex direction={"column"} me={5}>
              <Button
                variant={"accent"}
                onClick={async () => {
                  await importDocuments(dispatch);
                }}
              >
                <AddIcon me={2} fontSize={"sm"} />
                Import Documents
              </Button>
              <Text fontSize={12} color={"gray"}>
                Max 1 GB per file. Supported
                document types: PDF, DOCX, TXT, PPTX, HTML
              </Text>
            </Flex>

            <Button
              me={5}
              onClick={() => {
                setShowDeleteAlert(true);
              }}
              isDisabled={importedDocs.length === 0 || documentsLoading}
            >
              <DeleteIcon fontSize={"sm"} me={2} />
              Delete Documents
            </Button>
          </Flex>
        </Flex>

        {documentsLoading && (
          <Flex justifyContent={"center"} alignItems={"center"}>
            <Spinner color={"accent"} />
          </Flex>
        )}
        {!documentsLoading && (
          <Box maxHeight={1000} overflowY={"scroll"}>
            {importedDocs.map((doc, i) => (
              <Card
                mt={5}
                mb={5}
                me={5}
                p={3}
                backgroundColor={
                  colorMode === "light"
                    ? "rgba(0, 0, 0, 0.05)"
                    : "customPurple.700"
                }
                key={i}
              >
                <CardHeader>
                  <Flex direction={"row"}>
                    <Heading fontSize={"md"}>Document</Heading>
                    <Spacer />
                    <Tag colorScheme={"green"}>ENABLED</Tag>
                  </Flex>
                </CardHeader>

                <CardBody>
                  <Flex direction={"column"} alignItems={"start"}>
                    <Flex direction={"column"} alignItems={"start"}>
                      <Heading fontSize={"sm"}>Name</Heading>
                      <Text>
                        {doc.file_name_with_extension || doc.file_name + (doc.extension || "")}
                      </Text>
                    </Flex>

                    <Flex direction={"column"} alignItems={"start"}>
                      <Heading fontSize={"sm"}>Size</Heading>
                      <Text>{(doc.size / 1024 / 1024).toFixed(2)} MB</Text>
                    </Flex>

                    {doc.path && (
                      <Flex direction={"column"} alignItems={"start"}>
                        <Heading fontSize={"sm"}>Path</Heading>
                        <Text>{doc.path}</Text>
                      </Flex>
                    )}
                  </Flex>
                </CardBody>
              </Card>
            ))}
          </Box>
        )}
      </Box>
    </Box >
  );
}
