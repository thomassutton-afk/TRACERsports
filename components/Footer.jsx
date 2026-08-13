/**
 * Shared site footer. Content ported from the old site's AboutPage.jsx
 * "Who makes this?" section — same email/X/Instagram links, just pulled
 * out into its own component so every page can use it instead of each
 * page needing its own copy.
 */

export default function Footer() {
  return (
    <footer
      style={{
        borderTop: "1px solid var(--border)",
        background: "var(--surface)",
        padding: "2rem",
        marginTop: "2rem",
      }}
    >
      <div
        style={{
          maxWidth: 1200,
          margin: "0 auto",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 12,
        }}
      >
        <div
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 15,
            fontWeight: 900,
            letterSpacing: -0.3,
          }}
        >
          <span style={{ color: "var(--acc)" }}>TR</span>
          <span style={{ color: "var(--ut)" }}>AC</span>
          <span style={{ color: "var(--uo)" }}>ER</span>
        </div>

        <div
          style={{
            display: "flex",
            gap: 18,
            fontFamily: "var(--font-mono)",
            fontSize: 12,
          }}
        >
          <a href="mailto:tracersports4@gmail.com" style={footerLinkStyle}>
            Email
          </a>
          <a
            href="https://twitter.com/tracersports"
            target="_blank"
            rel="noopener noreferrer"
            style={footerLinkStyle}
          >
            X
          </a>
          <a
            href="https://instagram.com/tracersports"
            target="_blank"
            rel="noopener noreferrer"
            style={footerLinkStyle}
          >
            Instagram
          </a>
        </div>
      </div>
    </footer>
  );
}

const footerLinkStyle = {
  color: "var(--text2)",
  textDecoration: "none",
};
