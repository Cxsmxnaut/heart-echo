import Foundation

struct SampleProvider: Identifiable {
    let id: Int
    let name: String
    let specialty: String
    let symbol: String
    let detail: String

    static let all: [SampleProvider] = [
        .init(id: 1, name: "Community Health Center", specialty: "Primary care", symbol: "cross.case.fill", detail: "Ask about sliding-scale fees"),
        .init(id: 2, name: "Heart & Vascular Clinic", specialty: "Cardiology", symbol: "heart.fill", detail: "Ask about referrals and coverage"),
        .init(id: 3, name: "Family Care Practice", specialty: "Primary care", symbol: "stethoscope", detail: "Ask about new-patient appointments")
    ]
}
