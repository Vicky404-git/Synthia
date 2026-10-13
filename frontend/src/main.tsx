import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { BackendProvider } from "./state/BackendContext";
import { HistoryProvider } from "./state/HistoryContext";
import { SettingsProvider } from "./state/SettingsContext";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <SettingsProvider>
      <HistoryProvider>
        <BackendProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </BackendProvider>
      </HistoryProvider>
    </SettingsProvider>
  </React.StrictMode>,
);
