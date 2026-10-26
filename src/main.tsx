import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { TooltipProvider } from "@radix-ui/react-tooltip";
import App from "./App";
import "./styles.css";
import "./studio.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <TooltipProvider delayDuration={300}>
      <App />
    </TooltipProvider>
  </StrictMode>,
);

