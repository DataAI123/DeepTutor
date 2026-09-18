import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ServerEvent } from "@/contracts/generated/turn-protocol";
import type { TurnRuntimeClientOptions } from "@/features/chat/transport/TurnRuntimeClient";
import { UnifiedTurnClient } from "@/features/chat/transport/UnifiedTurnClient";

const transport = vi.hoisted(() => ({ emit: (_event: ServerEvent) => {} }));
vi.mock("@/features/chat/transport/TurnRuntimeClient", () => ({
  TurnRuntimeClient: class {
    constructor(options: TurnRuntimeClientOptions) { transport.emit = options.onEvent; }
  },
}));

describe("protocol errors at the chat adapter boundary", () => {
  const receive = vi.fn();
  beforeEach(() => { new UnifiedTurnClient(receive); });

  it("turns a scoped regenerate rejection into a recoverable UI error", () => {
    transport.emit({ type: "protocol_error", error_code: "regenerate_rejected",
      message: "Cannot regenerate", session_id: "s1", turn_id: "", retryable: true,
      protocol_version: "2.0" });
    expect(receive).toHaveBeenCalledWith(expect.objectContaining({
      type: "error", session_id: "s1", content: "Cannot regenerate",
      metadata: expect.objectContaining({ turn_terminal: true, reason: "regenerate_rejected" }),
    }));
  });

  it("does not terminate a turn for an unrelated protocol error", () => {
    transport.emit({ type: "protocol_error", error_code: "invalid_command",
      message: "Invalid command", session_id: "", turn_id: "", retryable: false,
      protocol_version: "2.0" });
    expect(receive).toHaveBeenCalledWith(expect.objectContaining({
      type: "error", metadata: expect.objectContaining({ turn_terminal: false }),
    }));
  });
});
