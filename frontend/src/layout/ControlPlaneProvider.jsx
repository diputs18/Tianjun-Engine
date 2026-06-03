import { createContext, useContext } from "react";
import { useControlPlane } from "../hooks/useControlPlane.js";

const ControlPlaneContext = createContext(null);

export function ControlPlaneProvider({ children }) {
  const value = useControlPlane();
  return (
    <ControlPlaneContext.Provider value={value}>
      {children}
    </ControlPlaneContext.Provider>
  );
}

export function useControlPlaneContext() {
  const context = useContext(ControlPlaneContext);
  if (!context) throw new Error("useControlPlaneContext must be used inside ControlPlaneProvider");
  return context;
}
