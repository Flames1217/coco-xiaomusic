import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import CocoXiaoMusic from "./components/CocoXiaoMusic";
import "./styles/globals.css";

createRoot(document.getElementById("app")!).render(
  <StrictMode>
    <CocoXiaoMusic />
  </StrictMode>
);
