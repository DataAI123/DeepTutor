import { useEffect } from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { ServerEvent } from "@/contracts/generated/turn-protocol";
import type { TurnRuntimeClientOptions } from "@/features/chat/transport/TurnRuntimeClient";
import { ChatStateAdapterProvider, useChatStateAdapter } from "@/features/chat/ChatStateAdapter";
import { initI18n } from "@/i18n/init";
import { buildVisiblePath } from "@/lib/message-branches";

initI18n("en");
const transport = vi.hoisted(() => ({ emit: (_event: ServerEvent) => {}, sent: [] as string[] }));
vi.mock("@/features/chat/transport/TurnRuntimeClient", () => ({
  TurnRuntimeClient: class {
    constructor(private options: TurnRuntimeClientOptions) { transport.emit = options.onEvent; }
    connect() { this.options.onStateChange?.("connected"); }
    setResumeCursor() {}
    stop() {}
    send(message: { type: string }) { transport.sent.push(message.type); }
  },
}));

function Harness() {
  const chat = useChatStateAdapter();
  useEffect(() => {
    chat.newSession();
    // Initialize once; the provider owns all subsequent state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return <div>
    <span data-testid="streaming">{String(chat.state.isStreaming)}</span>
    <div data-testid="transcript">{buildVisiblePath(chat.state.messages, {}).messages.map(m => m.content).join("\n")}</div>
    <button onClick={() => chat.sendMessage("Read the attachment")}>Start</button>
    <button onClick={() => chat.regenerateLastMessage()}>Regenerate</button>
    <button onClick={() => {
      chat.regenerateLastMessage();
      chat.regenerateLastMessage();
    }}>Regenerate twice</button>
  </div>;
}

it("restores the old answer and stops Thinking after the wire rejects regeneration", async () => {
  const user = userEvent.setup();
  render(<ChatStateAdapterProvider><Harness /></ChatStateAdapterProvider>);
  await user.click(screen.getByText("Start"));
  await act(async () => {
    for (const [index, type] of ["session", "content", "done"].entries()) {
      transport.emit({ type, source: "chat", stage: "responding", session_id: "s1", turn_id: "t1",
        seq: index + 1, timestamp: 1, protocol_version: "2.0",
        content: type === "content" ? "Original answer" : "",
        metadata: type === "done" ? { status: "completed", assistant_message_id: 2 } : {},
      } as ServerEvent);
    }
  });
  await waitFor(() => expect(screen.getByTestId("streaming")).toHaveTextContent("false"));
  expect(screen.getByTestId("transcript")).toHaveTextContent("Original answer");
  const sentBefore = transport.sent.length;
  await user.click(screen.getByText("Regenerate twice"));
  expect(transport.sent.slice(sentBefore)).toEqual(["regenerate"]);
  expect(transport.sent.at(-1)).toBe("regenerate");
  expect(screen.getByTestId("streaming")).toHaveTextContent("true");
  expect(screen.getByTestId("transcript")).not.toHaveTextContent("Original answer");
  const rejection = { type: "protocol_error", error_code: "regenerate_rejected", message: "Please retry",
    turn_id: "", retryable: true, protocol_version: "2.0" } as const;
  await act(async () => { transport.emit({ ...rejection, session_id: "different-session" }); });
  expect(screen.getByTestId("streaming")).toHaveTextContent("true");
  await act(async () => { transport.emit({ ...rejection, session_id: "s1" }); });
  expect(screen.getByTestId("streaming")).toHaveTextContent("false");
  expect(screen.getByTestId("transcript")).toHaveTextContent("Original answer");
  // A rejected request must release the guard so the learner can retry.
  const retryBefore = transport.sent.length;
  await user.click(screen.getByText("Regenerate twice"));
  expect(transport.sent.slice(retryBefore)).toEqual(["regenerate"]);
});
