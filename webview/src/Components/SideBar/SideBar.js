import "./SideBar.css";
import { useNavigate } from "react-router-dom";
import React, { useEffect, useState } from "react";
import { Dropdown } from "bootstrap";
import { useDispatch, useSelector } from "react-redux";
import { setShowLoginModal, store, updateUser } from "../../api/redux";
import {
  Button,
  Flex,
  Text,
  useColorMode,
} from "@chakra-ui/react";
import { isLocalMode, logout } from "../../api/user";
import { errorToast, infoToast } from "../../api/toast";
import { postCreateCheckoutSession } from "../../api/server-api/networking/checkout";
import { setAppAlertModal } from "../../api/redux/slices/appAlertModal";
import { getAPIEndpoints } from "../../api/server-api/networking";
import { MdDarkMode } from "react-icons/md";
import { BsSunFill } from "react-icons/bs";
import { FaStripe } from "react-icons/fa";
import { pyEditSetting } from "../../api/PythonBridge/senders/pyEditSetting";
import { setColorMode } from "../../api/redux/slices/colorMode";
import { getUser } from "../../api/server-api/networking/user";

export function SideBar(props) {
  const navigate = useNavigate();
  const user = useSelector((state) => state.user.value);
  const cost = useSelector((state) => state.cost);
  const userMode = useSelector((state) => state.userMode.value);
  const { colorMode, toggleColorMode } = useColorMode();
  const language = useSelector((state) => state.language.value);
  const dispatch = useDispatch();

  const storeColorMode = useSelector((state) => state.colorMode.value);
  useEffect(() => {
    if (!storeColorMode) return;
    if (storeColorMode !== colorMode) {
      toggleColorMode();
    }
  }, [storeColorMode, colorMode, toggleColorMode]);

  const currentVersion = useSelector((state) => state.currentVersion.value);

  let loggedIn = !!user;

  async function handleAddBalanceClick() {
    let res = await postCreateCheckoutSession(user.accessToken);
    if (res.status === "success") {
      let url = res.data.url;
      dispatch(
        setAppAlertModal({
          show: true,
          header: "Add Balance",
          alertText: (
            <Flex
              width={"100%"}
              height={"100%"}
              justifyContent={"center"}
              alignSelf={"center"}
              direction={"column"}
            >
              <Text fontSize={18} fontWeight={"bold"}>Pricing Information</Text>
              <Text fontSize={12}>
                AnkiBrain Server Mode uses "pay as you go" pricing.
              </Text>
              <Text fontSize={12}>
                GPT 3.5 Turbo can generate <b>1000 flashcards</b> for about <b>$0.39</b>.
                GPT 4 costs about $0.015 per flashcard.
              </Text>
              <Text fontSize={12}>
                $1.00 embeds <b>3,000 pages</b> of documents.
              </Text>
              <Text fontSize={12}>
                $1.00 stores <b>2,850 pages</b> for one month.
              </Text>
              <Text fontSize={10} color={"gray"}>
                Files stored in a vector database. See{" "}
                <a href={getAPIEndpoints().PRIVACY_POLICY} style={{ color: "blue" }}>
                  Privacy Policy
                </a>
              </Text>
              <Button variant={"accent"} mt={3}>
                <a
                  href={url}
                  style={{
                    width: "100%",
                    height: "100%",
                    display: "flex",
                    justifyContent: "center",
                    alignItems: "center",
                  }}
                >
                  <FaStripe size={48} style={{ marginRight: 7.5 }} />
                  Add Balance
                </a>
              </Button>
            </Flex>
          ),
          onClose: async () => {
            let res = await getUser(store.getState().user.value.accessToken);
            if (res.status === "success") {
              infoToast(
                "Refreshing User Information...",
                "Refreshing your user information to reflect any added balance.",
                1000
              );
              dispatch(updateUser(res.data.user));
            }
          },
        })
      );
    }
  }

  return (
    <div className="TopHeader">
      <div className="TopHeader-left">
        <span className="TopHeader-brand">AnkiBrain</span>
        <span className="TopHeader-meta">v{currentVersion}{currentVersion < "1" ? " Beta" : ""}</span>
        {process.env.REACT_APP_ENV === "DEV" && (
          <span className="TopHeader-meta">Dev</span>
        )}
        <span className="TopHeader-language">{language}</span>
        <button
          className="TopHeader-colorToggle"
          onClick={async (e) => {
            dispatch(setColorMode(colorMode === "dark" ? "light" : "dark"));
            e.currentTarget.blur();
            await pyEditSetting(
              "colorMode",
              colorMode === "dark" ? "light" : "dark"
            );
          }}
        >
          {colorMode === "light" ? (
            <MdDarkMode size={16} />
          ) : (
            <BsSunFill size={16} />
          )}
        </button>
      </div>

      <div className="TopHeader-right">
        {!loggedIn && userMode === "SERVER" && (
          <button
            className="TopHeader-loginBtn"
            onClick={() => dispatch(setShowLoginModal(true))}
          >
            Login
          </button>
        )}

        {loggedIn && userMode === "SERVER" && (
          <>
            <div className="TopHeader-userInfo">
              <span className="TopHeader-userEmail">{user.email}</span>
              <span className="TopHeader-userBalance">${user.balance.toFixed(2)}</span>
              <span className="TopHeader-userStorage">S: ${user.monthlyStorageCharge.toFixed(2)}</span>
            </div>
            <button
              className="TopHeader-actionBtn"
              onClick={async () => {
                try {
                  if (store.getState().lockCheckoutSession.value) {
                    infoToast("Busy...", "Please finish what you are doing before adding balance!");
                  } else {
                    await handleAddBalanceClick();
                  }
                } catch (err) {
                  errorToast("Error", err.message);
                }
              }}
            >
              Add
            </button>
            <div className="TopHeader-profile" id="ProfileDropdown">
              <i
                className="bi bi-person-circle"
                onClick={() => {
                  const dropdown = new Dropdown(
                    document.getElementById("ProfileDropdown")
                  );
                  dropdown.toggle();
                }}
              />
              <div className="dropdown-menu dropdown-menu-end">
                <div
                  className="dropdown-item"
                  onClick={async () => {
                    const dropdown = new Dropdown(
                      document.getElementById("ProfileDropdown")
                    );
                    dropdown.toggle();
                    await logout();
                  }}
                >
                  Logout
                </div>
              </div>
            </div>
          </>
        )}

        {userMode === "LOCAL" && (
          <span className="TopHeader-cost">${cost.session.toFixed(2)}</span>
        )}

        {isLocalMode() && (
          <a
            className="TopHeader-actionBtn"
            href={"https://donate.stripe.com/7sI16Z1jYdo698I9AC"}
          >
            Donate
          </a>
        )}
      </div>
    </div>
  );
}
