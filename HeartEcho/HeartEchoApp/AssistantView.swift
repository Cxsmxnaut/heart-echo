import SwiftUI
import UIKit

#if DEBUG
extension ScreeningResult {
    static let preview = ScreeningResult(recording: HeartRecording(
        title: "Illustrative recording", source: "Design preview", seconds: 20, bpm: nil,
        signalStatus: "Not measured", murmur: MurmurReading(finding: .unsure, probabilities: [0, 0, 1], windows: 5, seconds: 20)))
}
#endif

/// The Care tab, new results, and saved results all open this same conversation.
struct AssistantView: View {
    let requestedResult: ScreeningResult?
    private let previewConversation: Bool
    @EnvironmentObject private var care: CareService
    @Environment(\.colorScheme) private var colorScheme
    @State private var showConnection = false
    @State private var showRecordingDetails = false
    @State private var draft = ""
    @FocusState private var composerFocused: Bool

    init(result: ScreeningResult? = nil, previewConversation: Bool = false) {
        requestedResult = result
        self.previewConversation = previewConversation
    }

    private var result: ScreeningResult? { care.chatRecording.map(ScreeningResult.init(recording:)) }
    private var waitingForResult: Bool {
        guard let requestedResult else { return false }
        return care.chatRecording?.id != requestedResult.recording.id
    }
    private var chatBackground: Color { Color(uiColor: .systemBackground) }
    private var surface: Color { Color(uiColor: .secondarySystemBackground) }
    private var actionColor: Color {
        colorScheme == .dark ? Color(red: 1, green: 0.38, blue: 0.51) : Color(red: 0.78, green: 0.10, blue: 0.24)
    }

    var body: some View {
        Group {
            if waitingForResult {
                VStack(spacing: 16) {
                    if care.busy || care.error == nil { ProgressView("Opening your result…") }
                    if let error = care.error {
                        Text(error).foregroundStyle(.red).accessibilityIdentifier("assistant-network-error")
                        Button("Try again") { Task { await care.prepareChat(for: requestedResult?.recording) } }
                    }
                }.padding()
            } else {
                conversation
            }
        }
        .task(id: requestedResult?.recording.id) { await care.prepareChat(for: requestedResult?.recording) }
        .background(chatBackground)
        .navigationTitle("Heart Echo AI")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(chatBackground, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                Button { Task { await care.clear() } } label: { Image(systemName: "square.and.pencil") }
                    .disabled(care.busy).accessibilityLabel("New care chat")
                Menu {
                    if result != nil { Button("Recording details", systemImage: "waveform") { showRecordingDetails = true } }
                    Button("Connect care AI", systemImage: "network") { showConnection = true }
                } label: { Image(systemName: "ellipsis") }
                .accessibilityLabel("Chat options")
            }
        }
        .sheet(isPresented: $showConnection) { CareConnectionView() }
        .sheet(isPresented: $showRecordingDetails) { recordingDetails }
    }

    private var conversation: some View {
        ScrollViewReader { scroll in
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Color.clear.frame(height: 1).id("conversation-start")
                    if let result {
                        recordingAttachment(result)
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Your result · on this iPhone").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                            ChatReplyText(text: "**\(result.resultTitle)**\n\n\(result.explanation)\n\n\(result.recording.isExample ? "This is a public example, not your recording. " : "")Heart Echo can be wrong. A clinician can review the result.")
                                .accessibilityIdentifier("actual-result-explanation")
                        }
                    } else {
                        ChatReplyText(text: "I can help you find care and prepare questions for a clinician. You can start with your five-digit US ZIP code.")
                            .accessibilityIdentifier("care-chat-welcome")
                        if care.chatMessages.isEmpty {
                            Button {
                                composerFocused = true
                            } label: {
                                Label("Find care by ZIP", systemImage: "location.magnifyingglass")
                                    .font(.subheadline.weight(.semibold))
                                    .frame(minHeight: 32)
                            }
                            .buttonStyle(.bordered)
                            .tint(actionColor)
                            .accessibilityIdentifier("assistant-zip-quick-start")
                            .accessibilityHint("Enter a five-digit US ZIP code in the message field. No care-service pairing is needed.")
                        }
                    }
                    if previewConversation {
                        PreviewMessageBubble(text: "What should I ask a provider?", isUser: true)
                        PreviewMessageBubble(text: Self.providerQuestions, isUser: false)
                    }
                    ForEach(care.chatMessages) { message in
                        PreviewMessageBubble(text: message.text, isUser: message.isUser)
                            .id(message.id)
                    }
                    if care.busy { ProgressView("Checking your request…") }
                    if let error = care.error {
                        Text(error).foregroundStyle(.red).accessibilityIdentifier("assistant-network-error")
                        if let last = care.chatMessages.last(where: { $0.isUser }), let request = directSearchRequest(last.text) {
                            Button("Search public directories instead") {
                                Task {
                                    await care.searchDirect(zip: request.zip, specialty: request.specialty, affordable: request.affordable)
                                    if let reply = care.reply { care.appendChatMessage(reply.message, isUser: false) }
                                }
                            }.accessibilityIdentifier("assistant-direct-search")
                        }
                    }
                    if let reply = care.reply { CareResultsView(reply: reply) }
                    Color.clear.frame(height: 1).id("conversation-bottom")
                }
                .padding(.horizontal, 20).padding(.bottom, 20)
            }
            .scrollDismissesKeyboard(.interactively)
            .onChange(of: care.chatMessages.count, initial: true) { _, _ in
                withAnimation(.easeOut(duration: 0.2)) {
                    if let message = care.chatMessages.last {
                        scroll.scrollTo(message.id, anchor: message.isUser ? .bottom : .top)
                    } else {
                        scroll.scrollTo("conversation-start", anchor: .top)
                    }
                }
            }
            .onChange(of: composerFocused) { _, focused in
                if focused, let message = care.chatMessages.last {
                    withAnimation(.easeOut(duration: 0.2)) { scroll.scrollTo(message.id, anchor: .bottom) }
                }
            }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) { composer }
    }

    private func recordingAttachment(_ result: ScreeningResult) -> some View {
        let bpm = result.recording.bpm.map { bpmText($0) + " BPM" } ?? "BPM unavailable"
        let metadata = "\(Int(result.recording.seconds.rounded())) sec · \(bpm) · \(result.recording.source)"
        return HStack {
            Spacer(minLength: 48)
            Button { showRecordingDetails = true } label: {
                HStack(spacing: 12) {
                    Image(systemName: "waveform").font(.title3).foregroundStyle(actionColor)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Heart-sound recording").font(.subheadline.weight(.medium))
                        Text(metadata).font(.caption).foregroundStyle(.secondary)
                    }
                    Image(systemName: "chevron.down").font(.caption).foregroundStyle(.secondary)
                }
                .padding(12).foregroundStyle(.primary)
                .background(surface, in: RoundedRectangle(cornerRadius: 18))
            }.buttonStyle(.plain).accessibilityLabel("View recording details, \(metadata)")
        }
    }

    private var composer: some View {
        VStack(spacing: 8) {
            if result != nil {
                if care.modelProvider == "gemini" {
                    Text("Your recording and result stay on this iPhone. They aren't sent to Gemini.")
                        .font(.caption2).foregroundStyle(.secondary)
                } else {
                    Toggle("Share this result with care AI", isOn: $care.chatShareSummary)
                        .font(.caption).disabled(!care.canAttemptChat || care.busy)
                        .accessibilityIdentifier("assistant-summary-consent")
                    Text("Shares the finding and available measurements only when enabled. Audio stays on this iPhone.")
                        .font(.caption2).foregroundStyle(.secondary)
                }
            }
            HStack(alignment: .bottom, spacing: 4) {
                Menu {
                    if result != nil { Button("Recording details", systemImage: "waveform") { showRecordingDetails = true } }
                    Button("Connect care AI", systemImage: "network") { showConnection = true }
                    Button("Questions to ask a provider", systemImage: "text.bubble") {
                        draft = "What should I ask a provider?"
                        sendDraft()
                    }
                } label: {
                    Image(systemName: "plus").font(.system(size: 20)).foregroundStyle(.primary).frame(width: 44, height: 44)
                }.accessibilityLabel("Chat options and questions")
                TextField("Message Heart Echo AI", text: $draft, axis: .vertical)
                    .font(.body).lineLimit(1...5).focused($composerFocused).submitLabel(.send)
                    .onSubmit { sendDraft() }.padding(.vertical, 12)
                    .accessibilityIdentifier("assistant-message-input")
                Button(action: sendDraft) {
                    Image(systemName: "arrow.up").font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(canSend ? (colorScheme == .dark ? Color.black : Color.white) : Color.secondary)
                        .frame(width: 36, height: 36)
                        .background(canSend ? actionColor : Color(uiColor: .tertiarySystemFill), in: Circle())
                        .frame(width: 44, height: 44)
                }.buttonStyle(.plain).disabled(!canSend).accessibilityLabel("Send message")
            }
            .padding(4).background(surface, in: RoundedRectangle(cornerRadius: 28))
            .overlay { RoundedRectangle(cornerRadius: 28).strokeBorder(Color.primary.opacity(0.04), lineWidth: 1) }
            Button { showConnection = true } label: { Text(connectionStatus) }
                .accessibilityIdentifier("assistant-connection-status")
            Text(care.modelProvider == "gemini" ? "General chat goes to Google. Free-tier messages may be used to improve its products. Don’t enter personal or health details." : "Messages go to your chosen care service when connected.")
                .font(.caption2).foregroundStyle(.secondary)
        }
        .padding(.horizontal, 16).padding(.vertical, 8).background(chatBackground)
    }

    private var connectionStatus: String {
        if let reply = care.reply {
            if reply.model.mode == "native_directories" { return "Public directories · No recording sent" }
            if reply.model.used_this_turn == true { return reply.model.provider == "gemini" ? "Gemini care · Chat goes to Google" : "Gemma-assisted care · Audio stays here" }
            if reply.model.mode == "guided_fallback" { return "Guided help · AI unavailable" }
            return "Care service · Guided response"
        }
        if care.connected { return "Care service connected" }
        if care.hasSavedPairing { return "Saved care service · Send to reconnect" }
        return "Connect to use care AI"
    }

    @ViewBuilder private var recordingDetails: some View {
        NavigationStack {
            if let result {
                List {
                    Section("Recording") {
                        LabeledContent("Duration", value: "\(Int(result.recording.seconds.rounded())) seconds")
                        LabeledContent("Estimated heart rate", value: result.recording.bpm.map { bpmText($0) + " BPM" } ?? "Unavailable")
                        LabeledContent("BPM signal", value: result.recording.signalStatus)
                        LabeledContent("Source", value: result.recording.source)
                        LabeledContent("Sound result", value: result.resultTitle)
                    }
                    Section { Text("Heart Echo can be wrong. This is not a diagnosis.") }
                }
                .navigationTitle("Recording details").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { showRecordingDetails = false } } }
            }
        }.tint(actionColor)
    }

    private var canSend: Bool { !care.busy && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    private static let providerQuestions = """
    **Questions to ask your provider**

    1. Can you review this recording?
    2. What does the finding mean?
    3. Would any follow-up be useful?
    """

    private func sendDraft() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !care.busy else { return }
        draft = ""; composerFocused = false
        care.appendChatMessage(text, isUser: true)
        if care.canAttemptChat {
            let include = care.chatShareSummary
            let record = include ? care.chatRecording : nil
            Task {
                if let reply = await care.send(message: text, record: record, consent: include) {
                    care.appendChatMessage(reply.message, isUser: false)
                } else if let request = directSearchRequest(text) {
                    care.connectionNote = "The saved care service is unavailable. Searching public directories directly."
                    await care.searchDirect(zip: request.zip, specialty: request.specialty, affordable: request.affordable)
                    if let reply = care.reply { care.appendChatMessage(reply.message, isUser: false) }
                }
            }
            return
        }
        let query = text.lowercased()
        if let request = directSearchRequest(text) {
            Task {
                await care.search(zip: request.zip, specialty: request.specialty, affordable: request.affordable,
                                  record: nil, consent: false)
                if let reply = care.reply { care.appendChatMessage(reply.message, isUser: false) }
            }
        } else if let result, ["murmur", "result", "mean"].contains(where: query.contains) {
            care.appendChatMessage("From your saved result: " + result.explanation + "\n\nThis explanation is on your iPhone. Connect the care service to chat with the AI.", isUser: false)
        } else {
            care.appendChatMessage("Connect the care service to chat with the AI. You can also ask to find care with a five-digit US ZIP code for a direct directory search.", isUser: false)
        }
    }

    private func directSearchRequest(_ text: String) -> CareSearchIntent? {
        CareSearchIntent.parse(text)
    }

}

private struct PreviewMessageBubble: View {
    let text: String
    let isUser: Bool
    var body: some View {
        HStack {
            if isUser { Spacer(minLength: 56) }
            VStack(alignment: .leading, spacing: 8) {
                if isUser { Text(text).font(.body).lineSpacing(3).fixedSize(horizontal: false, vertical: true) }
                else { ChatReplyText(text: text); CopyReplyButton(text: text) }
            }
            .padding(isUser ? 12 : 0)
            .background { if isUser { RoundedRectangle(cornerRadius: 20).fill(Color(uiColor: .secondarySystemBackground)) } }
            .accessibilityElement(children: .contain)
            if !isUser { Spacer(minLength: 0) }
        }
    }
}

private struct ChatReplyText: View {
    let text: String
    var body: some View {
        Text((try? AttributedString(markdown: text, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(text))
            .font(.body).lineSpacing(5).frame(maxWidth: .infinity, alignment: .leading).fixedSize(horizontal: false, vertical: true)
    }
}

private struct CopyReplyButton: View {
    let text: String
    @State private var copied = false
    var body: some View {
        Button { UIPasteboard.general.string = text; copied = true } label: {
            Image(systemName: copied ? "checkmark" : "doc.on.doc").font(.system(size: 16)).foregroundStyle(.secondary)
                .frame(width: 44, height: 44, alignment: .leading)
        }
        .buttonStyle(.plain).accessibilityLabel(copied ? "Response copied" : "Copy response")
    }
}
