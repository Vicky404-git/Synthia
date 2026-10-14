import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Assistant } from "./pages/Assistant";
import { Command } from "./pages/Command";
import { History } from "./pages/History";
import { Resources } from "./pages/Resources";
import { Settings } from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Assistant />} />
        <Route path="commands" element={<Command />} />
        <Route path="history" element={<History />} />
        <Route path="resources" element={<Resources />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
