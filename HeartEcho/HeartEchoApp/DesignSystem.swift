import SwiftUI

enum AppStyle {
    static let accent = Color(red: 0.91, green: 0.19, blue: 0.34)
    static let background = Color(uiColor: .systemGroupedBackground)
    static let card = Color(uiColor: .secondarySystemGroupedBackground)
    static let muted = Color(uiColor: .secondaryLabel)
}

struct HealthCard<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 16) { content }
            .padding(20)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(AppStyle.card, in: RoundedRectangle(cornerRadius: 20))
    }
}

struct CardLabel: View {
    let title: String
    let symbol: String
    var color: Color = AppStyle.accent

    var body: some View {
        Label(title, systemImage: symbol)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(color)
    }
}

struct SectionHeading: View {
    let title: String
    var body: some View {
        Text(title)
            .font(.title2.bold())
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, 10)
    }
}

struct PrimaryButton: View {
    let title: String
    var symbol: String? = nil
    let action: () -> Void
    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        Button(action: action) {
            HStack(spacing: 9) {
                if let symbol { Image(systemName: symbol) }
                Text(title)
            }
            .font(.body.weight(.semibold))
            .frame(maxWidth: .infinity, minHeight: 54)
            .foregroundStyle(isEnabled ? Color.white : Color.secondary)
            .background(isEnabled ? Color(red: 0.78, green: 0.10, blue: 0.24) : Color.secondary.opacity(0.16), in: RoundedRectangle(cornerRadius: 15))
        }
        .buttonStyle(.plain)
    }
}

struct SoundWave: View {
    var color: Color = AppStyle.accent
    var progress: Double = 1
    var bars = 61

    var body: some View {
        GeometryReader { geometry in
            HStack(spacing: 3) {
                ForEach(0..<bars, id: \.self) { index in
                    let t = Double(index) / Double(bars - 1)
                    let pulse = pow(abs(sin(t * .pi * 4)), 9)
                    let echo = pow(abs(sin(t * .pi * 4 + 0.7)), 18) * 0.44
                    let detail = abs(sin(Double(index) * 2.7)) * 0.12
                    Capsule()
                        .fill(color.opacity(t <= progress ? 1 : 0.15))
                        .frame(height: max(4, (pulse * 0.72 + echo + detail) * geometry.size.height))
                }
            }
            .frame(height: geometry.size.height)
        }
        .accessibilityLabel("Illustrative heart sound waveform")
    }
}

struct Footnote: View {
    var text = "This project is a prototype and is not medical advice."
    var body: some View {
        Text(text)
            .font(.footnote)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 4)
            .padding(.bottom, 16)
    }
}

struct DetailRow: View {
    let symbol: String
    let title: String
    let subtitle: String
    var color: Color = AppStyle.accent

    var body: some View {
        HStack(alignment: .top, spacing: 15) {
            Image(systemName: symbol)
                .font(.title3)
                .foregroundStyle(color)
                .frame(width: 30, height: 30)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 5) {
                Text(title).font(.body.weight(.semibold))
                Text(subtitle).font(.subheadline).foregroundStyle(.secondary)
            }
        }
    }
}
