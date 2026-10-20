import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { blockchainService } from "../context/BlockchainService";

const BlockchainContext = createContext(null);

export function BlockchainProvider({ children }) {
  const [state, setState] = useState({
    status: "disconnected", // connecting | connected | error | disconnected
    error: null,
    network: null,
    account: null,
    demo: blockchainService.demo,
  });

  const connect = useCallback(async () => {
    try {
      await blockchainService.connect();
      setState({
        status: blockchainService.status,
        error: blockchainService.error,
        network: blockchainService.network,
        account: blockchainService.account,
        demo: blockchainService.demo,
      });
    } catch (err) {
      setState({
        status: "error",
        error: err.message || String(err),
        network: null,
        account: null,
        demo: blockchainService.demo,
      });
    }
  }, []);

  const disconnect = useCallback(() => {
    blockchainService.disconnect();
    setState({
      status: "disconnected",
      error: null,
      network: null,
      account: null,
      demo: blockchainService.demo,
    });
  }, []);

  // Connect before child pages attempt to read contract data.
  useEffect(() => {
    connect();
  }, [connect]);

  const value = {
    ...state,
    connect,
    disconnect,
    service: blockchainService,
  };

  return (
    <BlockchainContext.Provider value={value}>
      {children}
    </BlockchainContext.Provider>
  );
}

export function useBlockchain() {
  const ctx = useContext(BlockchainContext);
  if (!ctx) {
    throw new Error("useBlockchain must be used within a BlockchainProvider");
  }
  return ctx;
}
