import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import App from "./App";
import ClientLandingPage from "./landing/ClientLandingPage";
import AdminLandingPage from "./landing/AdminLandingPage";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <BrowserRouter>
    <Routes>
      <Route path="/cliente/:proyectoParam" element={<ClientLandingPage mode="client" />} />
      <Route path="/admin/informe/:proyectoParam" element={<AdminLandingPage />} />
      <Route path="/*" element={<App />} />
    </Routes>
  </BrowserRouter>
);
