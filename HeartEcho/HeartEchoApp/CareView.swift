import SwiftUI

struct CareView: View {
    @EnvironmentObject private var care: CareService
    var record: HeartRecording? = nil
    @State private var specialty = "family_medicine"
    @State private var zip = ""
    @State private var affordable = true
    @State private var shareSummary = false
    @State private var showConnection = false
    @State private var searched = false
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HealthCard {
                    CardLabel(title: "Care, Within Reach", symbol: "cross.case.fill", color: .blue)
                    Text("Find your\nnext step.").font(.system(.largeTitle, design: .rounded, weight: .bold))
                    Text("Find a clinician or a community health center. Any result, including unsure, can lead to a conversation.").foregroundStyle(.secondary)
                    TextField("Five-digit US ZIP code", text: $zip).keyboardType(.numberPad).textFieldStyle(.roundedBorder).accessibilityIdentifier("care-zip")
                        .onChange(of: zip) { _, value in zip = String(value.filter { $0.isASCII && $0.isNumber }.prefix(5)) }
                    Toggle("Community health centers first", isOn: $affordable).accessibilityIdentifier("care-affordable")
                    if !affordable {
                        Picker("Care category", selection: $specialty) {
                            Text("Primary care").tag("family_medicine"); Text("Internal medicine").tag("internal_medicine"); Text("Cardiology").tag("cardiology")
                        }
                    }
                    if let record, care.connected {
                        Text(record.finding).font(.headline)
                        Toggle("Send this result summary", isOn: $shareSummary).accessibilityIdentifier("care-summary-consent")
                        Text("Optional: finding, model version, source, time, duration and available BPM go to the care service. Audio and waveform stay on this iPhone. You can search with this off.").font(.caption).foregroundStyle(.secondary)
                    }
                    PrimaryButton(title: care.busy ? "Checking official sources…" : "Find Care", symbol: "magnifyingglass") {
                        searched = true
                        Task { await care.search(zip: zip, specialty: specialty, affordable: affordable, record: shareSummary ? record : nil, consent: shareSummary) }
                    }.disabled(zip.count != 5 || care.busy).accessibilityIdentifier("care-search")
                    Text(care.connected ? "Search uses your paired care service. A result summary is sent only when you turn sharing on." : "Search works directly on your iPhone. Your ZIP goes to public directories; no recording is sent.").font(.caption).foregroundStyle(.secondary)
                    Button("Optional: connect care assistant") { showConnection = true }.accessibilityIdentifier("care-connect")
                }
                if care.busy { ProgressView("Searching directories. This may take a moment.") }
                if let error = care.error {
                    HealthCard { Text(error).foregroundStyle(.red); Text("You can retry, reconnect, or use the official directory below.").font(.caption) }.accessibilityIdentifier("care-error")
                }
                if searched, !care.busy, let reply = care.reply {
                    HealthCard {
                        Text(reply.message).accessibilityIdentifier("care-live-message")
                        if shareSummary && reply.model.mode != "native_directories" { Text(reply.scan_explanation).font(.subheadline).accessibilityIdentifier("care-shared-explanation") }
                        Text(reply.model.mode == "native_directories" ? "Public directories · searched from this iPhone" : reply.model.used_this_turn == true ? "Gemma assisted this request" : "Directory service · guided response").font(.caption).foregroundStyle(.secondary)
                        if reply.model.mode == "guided_fallback" { Text("AI was unavailable or its output failed validation. The service completed the directory request.").font(.caption) }
                    }
                    CareResultsView(reply: reply)
                    Button("Clear conversation and results", role: .destructive) { Task { await care.clear() } }
                }
                HealthCard {
                    DetailRow(symbol: "dollarsign.circle", title: "Ask about cost", subtitle: "Health centers may adjust fees based on income and family size. Confirm eligibility, services and appointments directly.", color: .green)
                    Link("HRSA: Find a Health Center", destination: URL(string: "https://findahealthcenter.hrsa.gov/")!)
                    Link("NPI Registry", destination: URL(string: "https://npiregistry.cms.hhs.gov/")!)
                }
                Footnote(text: "US directories only. Results match an exact ZIP, not distance. Listings do not verify insurance, appointment availability or price. This project is a prototype and is not medical advice.")
            }.padding(20)
        }.background(AppStyle.background).navigationTitle("Care")
            .sheet(isPresented: $showConnection) { CareConnectionView() }
    }
}

struct CareResultsView: View {
    let reply: CareResponse
    var body: some View {
        ForEach(reply.results.keys.sorted(), id: \.self) { key in
            if let group = reply.results[key] {
                SectionHeading(title: key == "search_affordable_clinics" ? "Community health centers" : key == "search_providers" ? "Practices" : "Plan directory")
                if group.status == "error" { Text("This source is unavailable. Try again or use the official directory.").foregroundStyle(.secondary) }
                let cards = key == "lookup_plan_network" ? (group.providers ?? []) : (group.items ?? [])
                if key == "lookup_plan_network" { Text("Plan-directory evidence is limited. Confirm your exact plan and practice directly; a care-category match is not established.").font(.caption).foregroundStyle(.secondary) }
                if cards.isEmpty && group.status != "error" { Text("No listings returned for this exact ZIP. That does not mean no care exists.").foregroundStyle(.secondary) }
                ForEach(cards) { card in
                    HealthCard {
                        Text(card.name).font(.headline)
                        if let specialty = card.specialty { Text(specialty).font(.caption).foregroundStyle(.blue) }
                        if let address = card.address { Text(address).font(.subheadline) }
                        if let reason = card.reason { Text(reason).font(.caption).foregroundStyle(.secondary) }
                        if let url = card.phoneURL { Link(card.phone ?? "Call", destination: url) }
                        if let url = CareListing.safeWebURL(card.source_url) { Link(card.source ?? "Directory source", destination: url) }
                        if let url = CareListing.safeWebURL(card.website) { Link("Website", destination: url) }
                        if let url = CareListing.safeWebURL(card.directions_url) { Link("Directions", destination: url) }
                        if let date = card.retrieved_at { Text("Retrieved: " + date).font(.caption2).foregroundStyle(.secondary) }
                        Text("Contact the clinic to confirm services, cost and availability.").font(.caption2).foregroundStyle(.secondary)
                    }.accessibilityIdentifier("live-care-listing")
                }
                ForEach(group.fallbacks ?? [], id: \.url) { fallback in
                    if let url = CareListing.safeWebURL(fallback.url) { Link(fallback.label, destination: url) }
                }
            }
        }
    }
}

struct CareConnectionView: View {
    @EnvironmentObject private var care: CareService
    @Environment(\.dismiss) private var dismiss
    @State private var code = ""
    var body: some View {
        NavigationStack {
            Form {
                Section("Local demo service") {
                    Text("The sound analysis runs on your iPhone. Care chat connects through the demo Mac and uses public directories. Both devices need the same trusted Wi-Fi.")
                    TextField("Service address", text: $care.endpoint).textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL).accessibilityIdentifier("care-endpoint")
                    if let endpoint = care.discovered { Button("Use discovered Heart Echo service") { care.endpoint = endpoint } }
                    Button("Find service on Wi-Fi") { care.discover() }
                    SecureField("Six-digit pairing code", text: $code).keyboardType(.numberPad).accessibilityIdentifier("care-pair-code")
                        .onChange(of: code) { _, value in code = String(value.filter { $0.isASCII && $0.isNumber }.prefix(6)) }
                    Button(care.busy ? "Connecting…" : "Pair with service") { Task { await care.pair(code: code); code = "" } }.disabled(care.busy || code.count != 6).accessibilityIdentifier("care-pair")
                    if care.connected { Label("Care service connected", systemImage: "checkmark.circle.fill").foregroundStyle(.green) }
                    if let note = care.connectionNote { Text(note).font(.caption).foregroundStyle(.secondary) }
                    if let error = care.error { Text(error).foregroundStyle(.red) }
                }
                Section("What is shared") {
                    Text(care.modelProvider == "gemini" ? "General chat is sent to Google Gemini. Google may use free-tier messages to improve its products, so do not enter personal or health details. Your recording and result are not sent to Gemini. Care search sends your ZIP and chosen preferences to public directories." : "Care search sends the ZIP and care preferences you choose. Chat sends your typed message. A recording summary is sent only when you allow it. Raw audio, waveforms, Watch data and diagnostic logs are never sent.")
                    Text("Local HTTP travels over your Wi-Fi without transport encryption. Use a trusted network for this demo and HTTPS for remote hosting. Pairing credentials are stored in this iPhone's Keychain.")
                    Text("Conversations expire after 30 minutes of inactivity. Clear conversation requests deletion from the service.")
                    Button("Clear conversation", role: .destructive) { Task { await care.clear() } }.disabled(care.busy)
                }
            }.navigationTitle("Connect Care").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
                .onAppear { care.discover() }
        }
    }
}
